"""ONNX Runtime based inference for Beat This! beat tracker.
Runs using onnxruntime (CPU, DirectML, CUDA) without PyTorch model overhead."""
import logging
from pathlib import Path
from typing import Tuple

import numpy as np
import torch

from ..config import DATA_DIR

logger = logging.getLogger("mashloop.onnx")

ONNX_MODEL_PATH = DATA_DIR / "models" / "beat_this.onnx"


class ONNXBeatTracker:
    def __init__(self, model_path: Path = ONNX_MODEL_PATH):
        import onnxruntime as ort
        from beat_this.inference import Audio2Beats

        self.model_path = model_path
        if not self.model_path.exists():
            raise FileNotFoundError(f"ONNX model not found at {self.model_path}. Run tools/export_onnx.py first.")

        providers = ["CPUExecutionProvider"]
        if "DmlExecutionProvider" in ort.get_available_providers():
            providers.insert(0, "DmlExecutionProvider")
        elif "CUDAExecutionProvider" in ort.get_available_providers():
            providers.insert(0, "CUDAExecutionProvider")

        logger.info(f"Loading ONNX Beat Tracker with providers: {providers}")
        self.session = ort.InferenceSession(str(self.model_path), providers=providers)
        # Use Audio2Beats helper functions for feature extraction and post-processing
        self.helper = Audio2Beats(checkpoint_path="final0", device="cpu", dbn=False)

    def __call__(self, signal: np.ndarray, sr: int) -> Tuple[np.ndarray, np.ndarray]:
        """signal: 1D audio array float32 at sr.
        Returns: (beats, downbeats) in seconds."""
        spect = self.helper.signal2spect(signal, sr)
        # spect shape: [T, 128]
        t_len = spect.shape[0]
        chunk_size = 1500
        border_size = 6

        beat_logits = []
        downbeat_logits = []

        cur = 0
        while cur < t_len:
            end = min(t_len, cur + chunk_size)
            chunk = spect[cur:end]
            if len(chunk) < chunk_size:
                pad = torch.zeros(chunk_size - len(chunk), 128, dtype=spect.dtype)
                chunk_padded = torch.cat([chunk, pad], 0)
            else:
                chunk_padded = chunk

            inp = chunk_padded[None].numpy()  # [1, 1500, 128]
            b_out, d_out = self.session.run(None, {"spectrogram": inp})

            valid_len = end - cur
            beat_logits.append(b_out[0, :valid_len])
            downbeat_logits.append(d_out[0, :valid_len])
            cur = end

        full_beat = torch.from_numpy(np.concatenate(beat_logits, axis=0))
        full_downbeat = torch.from_numpy(np.concatenate(downbeat_logits, axis=0))

        beats, downbeats = self.helper.frames2beats(full_beat, full_downbeat)
        return np.asarray(beats, dtype=np.float64), np.asarray(downbeats, dtype=np.float64)
