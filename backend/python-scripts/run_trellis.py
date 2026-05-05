"""
Sprint 2 — TRELLIS integration (Microsoft/TRELLIS, MIT license)
TRELLIS uses Structured LATent (SLAT) diffusion:
  image → 3D Gaussian splat → mesh (via SLAT decoder)

Weights (~3 GB): huggingface-cli download microsoft/TRELLIS-image-large
Deps:  pip install trellis  (or install from microsoft/TRELLIS GitHub)

Fallback: TripoSR pipeline if TRELLIS weights not found.
"""

import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from inference_base import log, error_exit, success_exit

MODELS_DIR   = Path(__file__).parent.parent.parent / "models"
TRELLIS_DIR  = MODELS_DIR / "trellis"
TRELLIS_CKPT = TRELLIS_DIR / "model.safetensors"

# Also add cloned TRELLIS repo src
TRELLIS_SRC = TRELLIS_DIR / "src"


def _run_trellis(image_path, output_path):
    """
    Full TRELLIS pipeline: image → SLAT → mesh → GLB.
    Requires TRELLIS weights at models/trellis/.
    """
    import torch
    from PIL import Image

    if TRELLIS_SRC.exists():
        sys.path.insert(0, str(TRELLIS_SRC))

    if not TRELLIS_CKPT.exists():
        raise FileNotFoundError(
            f"TRELLIS weights not found at {TRELLIS_DIR}.\n"
            "Download: huggingface-cli download microsoft/TRELLIS-image-large "
            f"--local-dir {TRELLIS_DIR}"
        )

    log("Loading TRELLIS pipeline...", "info")
    from trellis.pipelines import TrellisImageTo3DPipeline

    device = "cuda" if torch.cuda.is_available() else "cpu"
    pipeline = TrellisImageTo3DPipeline.from_pretrained(
        str(TRELLIS_DIR), torch_dtype=torch.float16
    )
    pipeline.to(device)
    log(f"TRELLIS on {device}", "info")

    img = Image.open(image_path).convert("RGB").resize((512, 512))
    log("Running TRELLIS inference...", "info")

    outputs = pipeline.run(
        img,
        seed=42,
        sparse_structure_sampler_params={"steps": 12, "cfg_strength": 7.5},
        slat_sampler_params={"steps": 12, "cfg_strength": 3.0},
    )

    # Export mesh output as GLB
    mesh_output = outputs["mesh"][0]
    mesh_output.export(str(output_path))
    log(f"TRELLIS GLB saved: {os.path.getsize(output_path)} bytes", "info")


def generate_mesh_trellis(image_path, output_path):
    try:
        import numpy as np
        import trimesh
        import rembg
        from PIL import Image
        from io import BytesIO

        # Background removal
        log("Removing background with rembg...", "info")
        with open(image_path, "rb") as f:
            img_bytes = rembg.remove(f.read())
        img_rgba = Image.open(BytesIO(img_bytes)).convert("RGBA")

        trellis_ok = False
        try:
            _run_trellis(image_path, output_path)
            trellis_ok = True
        except FileNotFoundError as e:
            log(str(e), "warn")
            log("Falling back to TripoSR...", "warn")
        except Exception as e:
            log(f"TRELLIS failed: {e} — falling back to TripoSR", "warn")

        if not trellis_ok:
            # Import and run TripoSR as fallback
            from run_triposr import generate_mesh_triposr
            result = generate_mesh_triposr(image_path, str(output_path))
            result["trellis_used"] = False
            result["model"] = "trellis-fallback-triposr"
            return result

        # Apply PBR color
        try:
            mesh = trimesh.load(str(output_path), force="mesh")
            arr = np.array(img_rgba)
            mask = arr[:, :, 3] > 64
            avg = arr[:, :, :3][mask].mean(axis=0) if mask.sum() > 0 else [128, 128, 128]
            r, g, b = np.array(avg) / 255.0
            mesh.visual = trimesh.visual.TextureVisuals(
                material=trimesh.visual.material.PBRMaterial(
                    baseColorFactor=np.array([r, g, b, 1.0]),
                    roughnessFactor=0.55,
                    metallicFactor=0.05,
                )
            )
            mesh.export(str(output_path))
        except Exception as ce:
            log(f"Color step skipped: {ce}", "warn")

        size = os.path.getsize(output_path)
        return {
            "model": "trellis",
            "image_path": image_path,
            "output_path": str(output_path),
            "glb_size_bytes": size,
            "trellis_used": True,
            "method": "trellis-slat-diffusion",
            "license": "MIT",
        }

    except Exception as e:
        import traceback
        log(traceback.format_exc(), "error")
        error_exit(f"TRELLIS pipeline failed: {str(e)}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        error_exit("Usage: run_trellis.py <input_image> <output_glb>")
    if not os.path.exists(sys.argv[1]):
        error_exit(f"Input image not found: {sys.argv[1]}")
    success_exit(generate_mesh_trellis(sys.argv[1], sys.argv[2]))
