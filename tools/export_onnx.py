"""Export Beat This! model to ONNX and verify with ONNX Runtime."""
import argparse
import os
import sys
import time
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


class BeatThisONNXWrapper(torch.nn.Module):
    def __init__(self, model):
        super().__init__()
        self.model = model

    def forward(self, spect):
        out = self.model(spect)
        return out["beat"], out["downbeat"]


def export_beat_this(output_path: Path):
    from beat_this.inference import Audio2Beats

    print("Loading Beat This! PyTorch model...")
    tracker = Audio2Beats(checkpoint_path="final0", device="cpu", dbn=False)
    model = tracker.model.eval()
    wrapper = BeatThisONNXWrapper(model)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    dummy_input = torch.randn(1, 1500, 128, dtype=torch.float32)

    print(f"Exporting to ONNX at {output_path}...")
    t0 = time.time()
    torch.onnx.export(
        wrapper,
        dummy_input,
        str(output_path),
        export_params=True,
        opset_version=17,
        do_constant_folding=True,
        input_names=["spectrogram"],
        output_names=["beat", "downbeat"],
        dynamic_axes={
            "spectrogram": {0: "batch_size", 1: "time_frames"},
            "beat": {0: "batch_size", 1: "time_frames"},
            "downbeat": {0: "batch_size", 1: "time_frames"},
        },
    )
    print(f"Export completed in {time.time() - t0:.2f}s, size: {output_path.stat().st_size / 1024 / 1024:.1f} MB")

    # Verify with onnxruntime
    import onnxruntime as ort

    print("Verifying ONNX model with ONNX Runtime...")
    sess = ort.InferenceSession(str(output_path), providers=["CPUExecutionProvider"])
    test_input = torch.randn(1, 1500, 128, dtype=torch.float32)
    ort_inputs = {"spectrogram": test_input.numpy()}
    ort_outs = sess.run(None, ort_inputs)

    model.eval()
    with torch.no_grad():
        pt_beat, pt_downbeat = wrapper(test_input)

    max_diff_beat = float(np.max(np.abs(ort_outs[0] - pt_beat.numpy())))
    max_diff_downbeat = float(np.max(np.abs(ort_outs[1] - pt_downbeat.numpy())))
    print(f"Verification results: Max diff beat: {max_diff_beat:.6e}, Max diff downbeat: {max_diff_downbeat:.6e}")
    assert max_diff_beat < 1e-4, f"Beat difference too high: {max_diff_beat}"
    assert max_diff_downbeat < 1e-4, f"Downbeat difference too high: {max_diff_downbeat}"
    print("SUCCESS: ONNX model matches PyTorch output within numerical tolerance (< 1e-4)!")
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "models" / "beat_this.onnx")
    args = ap.parse_args()

    export_beat_this(args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
