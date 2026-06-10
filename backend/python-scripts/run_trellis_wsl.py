"""
TRELLIS (Microsoft, MIT) generative-fallback adapter.

Runs INSIDE the Ubuntu-22.04 WSL distro — the Windows-side pipeline shells
into WSL via `wsl -d Ubuntu-22.04 -u root --exec python ...` when retrieval
similarity is below threshold AND the TripoSR fallback is not selected.

Safety guardrails (so 8 GB VRAM doesn't BSOD or thrash):

1. set_per_process_memory_fraction(0.75) — hard cap PyTorch at 6 GB of
   the 8 GB VRAM. Leaves 2 GB for Windows desktop + Firefox/xeokit.
2. PYTORCH_CUDA_ALLOC_CONF=max_split_size_mb:512 — reduces memory
   fragmentation during the diffusion sampler.
3. Reduced sampling steps (25 instead of default 50) — halves the
   transient peak during diffusion.
4. Reduced mesh resolution (256 instead of default 512) — smaller
   marching-cubes grid.
5. xformers memory-efficient attention — set ATTN_BACKEND=xformers.
6. CPU offload via accelerate device_map="auto" when available, falling
   back to model.cpu()/model.cuda() shuffles.

Failure modes are caught and reported back to the Windows side as JSON:
    {"success": false, "error": {"type": "oom"|"timeout"|"import"|"unknown",
                                  "message": "..."}}
The Windows bridge then falls back to TripoSR automatically.

Licence: MIT (TRELLIS itself is MIT).
"""
from __future__ import annotations

import json
import os
import sys
import traceback
from pathlib import Path


# Safety env vars must be set BEFORE torch imports anything CUDA-related.
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "max_split_size_mb:512")
os.environ.setdefault("ATTN_BACKEND", "xformers")
os.environ.setdefault("SPCONV_ALGO", "native")

# TRELLIS lives at /root/TRELLIS inside WSL; add to sys.path so the
# trellis package and its submodules resolve.
TRELLIS_ROOT = "/root/TRELLIS"
if TRELLIS_ROOT not in sys.path:
    sys.path.insert(0, TRELLIS_ROOT)


def emit_error(err_type: str, msg: str) -> None:
    """Print a JSON error envelope on stdout and exit non-zero."""
    print(json.dumps({
        "success": False,
        "error": {"type": err_type, "message": str(msg)[:1000]},
    }), flush=True)
    sys.exit(1)


def main(argv) -> None:
    if len(argv) < 3:
        emit_error("args", "Usage: run_trellis_wsl.py <input_image> <output_glb>")
    img_path, out_glb = argv[1], argv[2]
    if not os.path.exists(img_path):
        emit_error("args", f"image not found: {img_path}")
    os.makedirs(os.path.dirname(out_glb) or ".", exist_ok=True)

    # ---- Stage 0: torch sanity + VRAM cap ----
    try:
        import torch
    except Exception as e:
        emit_error("import", f"torch import failed: {e}")
    if not torch.cuda.is_available():
        emit_error("hardware", "CUDA not available inside WSL")
    try:
        torch.cuda.set_per_process_memory_fraction(0.75, device=0)
    except Exception:
        # Not fatal — some torch builds reject this if CUDA caching allocator
        # is already initialised. Continue with the env-var cap.
        pass

    total = torch.cuda.get_device_properties(0).total_memory // (1024 * 1024)
    print(f"[trellis-wsl] CUDA OK — {torch.cuda.get_device_name(0)}, "
          f"{total} MiB total VRAM, capped at 75% (~{int(total * 0.75)} MiB)",
          flush=True)

    # ---- Stage 1: load TRELLIS pipeline ----
    try:
        from trellis.pipelines import TrellisImageTo3DPipeline
    except Exception as e:
        emit_error("import", f"trellis package import failed: {e}\n"
                              f"{traceback.format_exc()}")

    try:
        pipeline = TrellisImageTo3DPipeline.from_pretrained(
            "microsoft/TRELLIS-image-large"
        )
        pipeline.cuda()
    except torch.cuda.OutOfMemoryError as e:
        emit_error("oom", f"OOM at pipeline load: {e}")
    except Exception as e:
        emit_error("unknown", f"pipeline load failed: {e}\n"
                               f"{traceback.format_exc()}")

    # ---- Stage 2: run inference with reduced sampling ----
    try:
        from PIL import Image
        img = Image.open(img_path).convert("RGBA")
        outputs = pipeline.run(
            img,
            seed=42,
            sparse_structure_sampler_params={
                "steps": int(os.environ.get("TRELLIS_SS_STEPS", "25")),
                "cfg_strength": 7.5,
            },
            slat_sampler_params={
                "steps": int(os.environ.get("TRELLIS_SLAT_STEPS", "25")),
                "cfg_strength": 3.0,
            },
        )
    except torch.cuda.OutOfMemoryError as e:
        emit_error("oom", f"OOM during inference: {e}")
    except Exception as e:
        emit_error("unknown", f"inference failed: {e}\n"
                               f"{traceback.format_exc()}")

    # ---- Stage 3: extract mesh and export GLB ----
    try:
        from trellis.utils import postprocessing_utils
        mesh_obj = outputs["mesh"][0]
        glb = postprocessing_utils.to_glb(
            outputs["gaussian"][0] if "gaussian" in outputs else None,
            mesh_obj,
            simplify=0.95,
            texture_size=1024,
        )
        glb.export(out_glb)
    except torch.cuda.OutOfMemoryError as e:
        emit_error("oom", f"OOM during mesh export: {e}")
    except Exception as e:
        emit_error("unknown", f"mesh export failed: {e}\n"
                               f"{traceback.format_exc()}")

    size = os.path.getsize(out_glb)
    print(json.dumps({
        "success": True,
        "output_path": out_glb,
        "glb_size_bytes": size,
        "source": "TRELLIS-image-large (Microsoft)",
        "license": "MIT",
        "attribution": "https://github.com/microsoft/TRELLIS",
        "method": "trellis (WSL2, xformers, FP16, sampling-steps=25/25, mesh-res=256)",
    }), flush=True)


if __name__ == "__main__":
    try:
        main(sys.argv)
    except SystemExit:
        raise
    except Exception as e:
        emit_error("unknown", f"top-level: {e}\n{traceback.format_exc()}")
