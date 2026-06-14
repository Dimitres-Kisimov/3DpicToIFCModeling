"""Single-shot verify that the TRELLIS env in /opt/conda/envs/trellis is
healthy. Prints each component status; exit 0 if all pass, 1 if any fail."""
import sys
sys.path.insert(0, "/root/TRELLIS")

failures = []

try:
    import torch
    print(f"torch: {torch.__version__}  cuda: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"  device: {torch.cuda.get_device_name(0)}")
        print(f"  VRAM:   {torch.cuda.get_device_properties(0).total_memory // (1024*1024)} MiB")
except Exception as e:
    failures.append(f"torch: {e}")

try:
    import xformers
    print(f"xformers: {xformers.__version__}")
except Exception as e:
    failures.append(f"xformers: {e}")

try:
    import spconv
    print(f"spconv: {spconv.__version__}")
except Exception as e:
    failures.append(f"spconv: {e}")

try:
    import kaolin
    print(f"kaolin: {kaolin.__version__}")
except Exception as e:
    failures.append(f"kaolin: {e}")

try:
    from trellis.pipelines import TrellisImageTo3DPipeline
    print("trellis.pipelines.TrellisImageTo3DPipeline: OK")
except Exception as e:
    failures.append(f"TrellisImageTo3DPipeline: {e}")

print()
if failures:
    print("FAILED:")
    for f in failures:
        print("  ", f)
    sys.exit(1)
print("ALL CHECKS PASSED")
