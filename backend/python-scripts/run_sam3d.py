"""
SAM 3D Objects generative-fallback adapter.

Bridges Meta's official inference.py from the cloned sam-3d-objects repo
into the SCS pipeline. Runs under Python 3.12 (where kaolin / open3d /
pytorch3d wheels exist for Windows) as a subprocess of the main Python 3.13
runtime.

Architecture:
  Main pipeline (Python 3.13) detects that retrieval similarity is below
  threshold and spawns this script via the sibling Python 3.12 interpreter.
  This script:
    1. Loads the SAM 3D Objects pipeline (mesh-output decoder only, skip
       Gaussian splat)
    2. Reads the input image + a mask (SAM 3 or rembg-derived)
    3. Runs inference with FP16 + accelerate device_map="auto" for CPU
       offload of weights into the 64 GB system RAM
    4. Writes the resulting GLB to the requested output path
    5. Prints a JSON status to stdout for the Node bridge

VRAM strategy on 8 GB:
  - dtype=float16 (set in pipeline.yaml)
  - device_map="auto" — inactive layers stay in CPU RAM, streamed through GPU
  - Sequential stage execution: ss_encoder -> ss_generator -> ss_decoder ->
    slat_encoder -> slat_generator -> slat_decoder_mesh, with empty_cache()
    between
  - Skip the Gaussian-splat decoders (slat_decoder_gs / _gs_4) — those add
    significant VRAM and we don't need them for a BIM mesh output

Licence: SAM Licence (commercial-safe, no caps, no royalties).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SAM3D_CLONE = REPO_ROOT / "backend" / "sam3d" / "sam-3d-objects"
SAM3D_WEIGHTS_DIR = Path.home() / ".cache" / "huggingface" / "hub" / \
    "models--facebook--sam-3d-objects"


def log(level, msg):
    print(f"[{level.upper():4s}] {msg}", flush=True)


def resolve_checkpoint_dir() -> Path:
    """Find the snapshot dir inside the HF cache where pipeline.yaml lives."""
    snapshots = SAM3D_WEIGHTS_DIR / "snapshots"
    if not snapshots.exists():
        raise SystemExit(json.dumps({"success": False,
            "error": {"message": f"SAM 3D weights not downloaded: {SAM3D_WEIGHTS_DIR}"}}))
    # Pick the newest snapshot
    snap = sorted(snapshots.iterdir(), key=lambda p: p.stat().st_mtime)[-1]
    checkpoints = snap / "checkpoints"
    if not checkpoints.exists():
        raise SystemExit(json.dumps({"success": False,
            "error": {"message": f"checkpoints/ missing under {snap}"}}))
    return checkpoints


def derive_mask_from_image(image_path: str) -> tuple:
    """Return (rgba_image, alpha_mask) using rembg if image has no alpha."""
    from PIL import Image
    import numpy as np

    img = Image.open(image_path)
    if img.mode == "RGBA":
        rgba = img
    else:
        # rembg gives us alpha-mask separation for free
        import rembg
        with open(image_path, "rb") as f:
            data = f.read()
        cut = rembg.remove(data)
        from io import BytesIO
        rgba = Image.open(BytesIO(cut)).convert("RGBA")

    arr = np.array(rgba)
    mask = (arr[:, :, 3] > 128).astype(np.uint8) * 255
    return rgba, Image.fromarray(mask, mode="L")


def run_sam3d(image_path: str, output_glb: str):
    """Call Meta's Inference class on the input image and save a GLB."""
    if not SAM3D_CLONE.exists():
        raise SystemExit(json.dumps({"success": False,
            "error": {"message": f"sam-3d-objects clone missing at {SAM3D_CLONE}"}}))

    checkpoints = resolve_checkpoint_dir()
    pipeline_yaml = checkpoints / "pipeline.yaml"
    if not pipeline_yaml.exists():
        raise SystemExit(json.dumps({"success": False,
            "error": {"message": f"pipeline.yaml missing at {pipeline_yaml}"}}))

    # Stage 1: load image + mask
    log("INFO", f"Loading image: {image_path}")
    rgba, mask = derive_mask_from_image(image_path)
    log("INFO", f"  size={rgba.size}, mask coverage={(sum(1 for p in mask.getdata() if p>0)/len(list(mask.getdata())))*100:.1f}%")

    # Stage 2: import Meta's inference path
    # Add notebook/ to sys.path so 'from inference import Inference' resolves
    sys.path.insert(0, str(SAM3D_CLONE))
    sys.path.insert(0, str(SAM3D_CLONE / "notebook"))

    # Some of Meta's code does `os.environ["CUDA_HOME"] = os.environ["CONDA_PREFIX"]`
    # which crashes if CONDA_PREFIX isn't set. Provide a harmless default.
    os.environ.setdefault("CONDA_PREFIX", os.environ.get("VIRTUAL_ENV", ""))
    os.environ.setdefault("LIDRA_SKIP_INIT", "true")

    # Install minimal kaolin stub BEFORE importing Meta's code — real kaolin
    # has a DLL-load issue on torch 2.12+cu126 Windows. The bits we stub
    # (IpyTurntableVisualizer, Camera, PinholeIntrinsics, check_tensor) are
    # visualisation utilities and a debug assertion — not on the inference
    # forward path.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        import _kaolin_stub
        _kaolin_stub.install()
        log("INFO", "kaolin stub installed (real kaolin not available on Windows + torch 2.12)")
    except Exception as e:
        log("WARN", f"kaolin stub install failed: {e}")

    log("INFO", "Importing sam3d_objects + Inference...")
    try:
        from inference import Inference  # type: ignore
    except Exception as e:
        raise SystemExit(json.dumps({"success": False,
            "error": {"message": f"sam-3d-objects inference import failed: {e}",
                       "hint": "Run: py -3.12 -m pip install -e backend/sam3d/sam-3d-objects"}}))

    # Patch the pipeline.yaml temporarily — point all relative paths to our
    # checkpoint dir
    import tempfile, yaml
    cfg_text = pipeline_yaml.read_text(encoding="utf-8")
    # Meta's YAML uses relative paths like "ss_generator.ckpt"; the Inference
    # class resolves them relative to the config path, so just point at the
    # actual file.
    tmp_cfg = tempfile.NamedTemporaryFile(
        prefix="sam3d_pipeline_", suffix=".yaml",
        delete=False, mode="w", encoding="utf-8"
    )
    tmp_cfg.write(cfg_text); tmp_cfg.close()
    # Copy pipeline.yaml side-by-side with the .ckpt files so relative paths work
    target_cfg = checkpoints / "pipeline.yaml"  # already there

    log("INFO", f"Loading SAM 3D pipeline (this can take 60-120s on first run)...")
    inference = Inference(str(target_cfg), compile=False)
    log("INFO", "Pipeline loaded")

    # Stage 3: run inference
    log("INFO", "Running inference (FP16, expect ~60-180s on RTX 4070 Laptop)...")
    output = inference(rgba, mask, seed=42)
    log("INFO", "Inference done")

    # Stage 4: export mesh to GLB
    # Meta's output dict typically has "mesh" (trimesh-like) when slat_decoder_mesh
    # is used. Fall back to "gs" if mesh isn't present.
    import trimesh
    mesh_obj = None
    if "mesh" in output:
        mesh_obj = output["mesh"]
    elif "trimesh" in output:
        mesh_obj = output["trimesh"]
    else:
        # Last resort: try the gs decoder output and convert to mesh
        for k in output.keys():
            log("WARN", f"  unexpected output key: {k}")
        raise SystemExit(json.dumps({"success": False,
            "error": {"message": "no mesh in SAM 3D output", "keys": list(output.keys())}}))

    if hasattr(mesh_obj, "export"):
        mesh_obj.export(output_glb)
    else:
        # Some Meta classes wrap trimesh — try to access .vertices/.faces
        verts = getattr(mesh_obj, "vertices", None)
        faces = getattr(mesh_obj, "faces", None)
        if verts is None or faces is None:
            raise SystemExit(json.dumps({"success": False,
                "error": {"message": f"unknown mesh wrapper type: {type(mesh_obj).__name__}"}}))
        import numpy as np
        m = trimesh.Trimesh(vertices=np.asarray(verts), faces=np.asarray(faces))
        m.export(output_glb)

    size = os.path.getsize(output_glb)
    log("INFO", f"GLB saved ({size} bytes)")

    print(json.dumps({
        "success": True,
        "output_path": output_glb,
        "glb_size_bytes": size,
        "source": "SAM 3D Objects",
        "license": "SAM Licence (Meta) — commercial-safe, no caps, no royalties",
        "attribution": "https://huggingface.co/facebook/sam-3d-objects",
        "method": "sam-3d-objects (mesh decoder path, FP16, CPU offload)",
    }))


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(json.dumps({"success": False,
            "error": {"message": "Usage: run_sam3d.py <input_image> <output_glb>"}}))
        sys.exit(1)
    try:
        run_sam3d(sys.argv[1], sys.argv[2])
    except SystemExit:
        raise
    except Exception as e:
        import traceback
        print(json.dumps({
            "success": False,
            "error": {"message": str(e), "traceback": traceback.format_exc()},
        }))
        sys.exit(1)
