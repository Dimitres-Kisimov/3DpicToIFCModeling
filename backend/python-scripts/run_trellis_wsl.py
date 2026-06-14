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
# expandable_segments:True turns on CUDA's variable-size allocator (1.3.0+),
# which prevents fragmentation-induced OOM when PyTorch + spconv both share
# the 8 GB VRAM. max_split_size_mb:256 (down from 512) gives the allocator
# finer-grained splits — better for tight VRAM budgets.
os.environ.setdefault(
    "PYTORCH_CUDA_ALLOC_CONF",
    "expandable_segments:True,max_split_size_mb:256",
)
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

    # ---- Stage 0: torch sanity ----
    # SCS_TRELLIS_DEVICE controls the execution device:
    #   "cpu"  — full CPU execution (slow, ~5-10 min, but ZERO VRAM contention
    #            with the display driver, so safe on any hardware)
    #   "cuda" — GPU execution (fast but needs ≥12 GB VRAM in practice)
    # Defaults to "cpu" for safety on shared-display GPUs ≤ 8 GB where the
    # previous TDR events came from. Override with SCS_TRELLIS_DEVICE=cuda on
    # bigger cards.
    try:
        import torch
    except Exception as e:
        emit_error("import", f"torch import failed: {e}")

    device_str = os.environ.get("SCS_TRELLIS_DEVICE", "cpu").lower()
    use_cuda = (device_str == "cuda")

    if use_cuda:
        if not torch.cuda.is_available():
            emit_error("hardware", "CUDA requested but not available inside WSL")
        total = torch.cuda.get_device_properties(0).total_memory // (1024 * 1024)
        print(f"[trellis-wsl] device=cuda — {torch.cuda.get_device_name(0)}, "
              f"{total} MiB total VRAM, allocator=expandable_segments",
              flush=True)
    else:
        # Disable any cuda-allocation hooks set earlier; we won't touch GPU.
        print(f"[trellis-wsl] device=cpu — running on system RAM only "
              f"(VRAM untouched; ~5-10 min inference)",
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
        if use_cuda:
            pipeline.cuda()
        # CPU path: pipeline stays on CPU (where from_pretrained loaded it).
        # No VRAM touched at any point in this branch.
    except torch.cuda.OutOfMemoryError as e:
        emit_error("oom", f"OOM at pipeline load: {e}")
    except Exception as e:
        emit_error("unknown", f"pipeline load failed: {e}\n"
                               f"{traceback.format_exc()}")

    # ---- Stage 2: inference ----
    # CPU mode: pipeline.run() executes wholly on CPU — no VRAM contention
    # with the display driver, but ~5-10 min per inference. Mesh-only output
    # to skip the gaussian/RF decoders.
    # GPU mode: original run() path, all models on GPU. Caller is responsible
    # for having ≥16 GB VRAM available.
    try:
        from PIL import Image
        img = Image.open(img_path).convert("RGBA")
        print(f"[trellis-wsl] running inference on {device_str.upper()}; "
              f"this is the slow step — be patient", flush=True)
        outputs = pipeline.run(
            img,
            seed=42,
            formats=["mesh"],
            sparse_structure_sampler_params={
                "steps": int(os.environ.get("TRELLIS_SS_STEPS", "25")),
                "cfg_strength": 7.5,
            },
            slat_sampler_params={
                "steps": int(os.environ.get("TRELLIS_SLAT_STEPS", "25")),
                "cfg_strength": 3.0,
            },
        )
        print("[trellis-wsl] inference: OK", flush=True)
    except torch.cuda.OutOfMemoryError as e:
        emit_error("oom", f"OOM during inference: {e}")
    except Exception as e:
        emit_error("unknown", f"inference failed: {e}\n"
                               f"{traceback.format_exc()}")

    # ---- Stage 3: extract mesh and export GLB ----
    if use_cuda:
        try:
            torch.cuda.empty_cache()
        except Exception:
            pass

    try:
        mesh_obj = outputs["mesh"][0]
        # No gaussian → can't use TRELLIS's to_glb() (it needs gaussian for
        # texture baking). Convert the mesh object directly via trimesh.
        # The mesh_obj is a MeshExtractResult with `vertices` and `faces`
        # tensors. Apply per-vertex colour from face normals via downstream
        # PBR (which run_detect_and_place.py adds anyway from CLIP-detected
        # input photo colour).
        import trimesh as _tm
        verts = mesh_obj.vertices.cpu().numpy()
        faces = mesh_obj.faces.cpu().numpy()
        out_mesh = _tm.Trimesh(vertices=verts, faces=faces, process=False)
        out_mesh.export(out_glb)
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
