"""Lazily loaded neural models, kept resident between tracks. Each worker process
analyses one track at a time and holds its own copy; several processes share
the GPU. When the GPU is out of memory (it is shared with other services), a
track is separated on the CPU instead: slower, same result."""
import threading
import warnings

import numpy as np
import torch

from ..config import DEVICE, SAMPLE_RATE

_local = threading.local()


def device() -> str:
    return DEVICE if DEVICE != "cuda" or torch.cuda.is_available() else "cpu"


def beat_tracker():
    tracker = getattr(_local, "beat_tracker", None)
    if tracker is None:
        from ..config import DATA_DIR, MODELS_DIR
        onnx_path = MODELS_DIR / "beat_this.onnx"
        if onnx_path.exists():
            try:
                from .onnx_tracker import ONNXBeatTracker
                tracker = ONNXBeatTracker(onnx_path)
                _local.beat_tracker = tracker
                return tracker
            except Exception:
                pass
        from beat_this.inference import Audio2Beats
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            tracker = Audio2Beats(checkpoint_path="final0", device=device(), dbn=False)
        _local.beat_tracker = tracker
    return tracker


def separator():
    model = getattr(_local, "separator", None)
    if model is None:
        from demucs.pretrained import get_model
        model = get_model("htdemucs")
        model.to(device()).eval()
        _local.separator = model
    return model


def separate(y: np.ndarray, keep_stereo: tuple[str, ...] = ()) -> tuple[np.ndarray, list[str], dict]:
    """y: (frames, 2) float32 at SAMPLE_RATE. Returns stems (4, frames) mono,
    their names, and the stems named in keep_stereo as (frames, 2) arrays,
    sample-aligned with y (the player mixes them against the full track)."""
    import gc
    from demucs.apply import apply_model
    model = separator()
    assert model.samplerate == SAMPLE_RATE
    wav = torch.from_numpy(np.ascontiguousarray(y.T))
    ref = wav.mean(0)
    mean, std = ref.mean(), ref.std() + 1e-8
    dev = device()
    norm_wav = ((wav - mean) / std)[None]  # Keep on CPU; Demucs chunking transfers each window to device
    del wav, ref
    try:
        with torch.no_grad():
            out = apply_model(model, norm_wav, device=dev,
                              split=True, overlap=0.1, shifts=0, progress=False)[0]
    except Exception as e:
        is_oom = isinstance(e, torch.cuda.OutOfMemoryError) or "out of memory" in str(e).lower() or "cuda" in str(e).lower()
        if not is_oom:
            raise
        if dev == "cuda":
            torch.cuda.empty_cache()
        with torch.no_grad():
            out = apply_model(model.cpu(), norm_wav, device="cpu",
                              split=True, overlap=0.1, shifts=0, progress=False)[0]
        try:
            model.to(dev)
        except Exception:
            pass
    finally:
        del norm_wav
    full = (out * std + mean).cpu().numpy()  # (sources, channels, frames)
    del out
    names = list(model.sources)
    stereo = {s: np.ascontiguousarray(full[names.index(s)].T.astype(np.float32)) for s in keep_stereo}
    res = full.mean(1)
    del full
    if dev == "cuda":
        torch.cuda.empty_cache()
    gc.collect()
    return res, names, stereo
