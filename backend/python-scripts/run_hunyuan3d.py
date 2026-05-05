"""
Sprint 7 — Hunyuan3D-2 Integration (Tencent/Hunyuan3D-2, Community License)
Pipeline:
  1. rembg background removal
  2. Hunyuan3D-2 multi-view diffusion → 3D reconstruction
  3. PBR texture bake from generated views
  4. Export GLB

License note: Hunyuan3D-2 Community License allows commercial use with attribution.
              Verify current license at: https://huggingface.co/tencent/Hunyuan3D-2

Weights (~8 GB): huggingface-cli download tencent/Hunyuan3D-2 --local-dir models/hunyuan3d

Deps: pip install hunyuan3d  (or follow official README)
      pip install diffusers transformers accelerate

Fallback: TRELLIS → TripoSR if weights not found.
"""

import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from inference_base import log, error_exit, success_exit

MODELS_DIR     = Path(__file__).parent.parent.parent / "models"
HY3D_DIR       = MODELS_DIR / "hunyuan3d"
HY3D_CKPT      = HY3D_DIR / "hunyuan3d-2-mv-turbo"    # multi-view turbo model
HY3D_SRC       = HY3D_DIR / "src"


def _run_hunyuan3d(image_path, output_path):
    """
    Run Hunyuan3D-2 pipeline: image → multi-view → 3D mesh → GLB.
    """
    import torch
    from PIL import Image

    if HY3D_SRC.exists():
        sys.path.insert(0, str(HY3D_SRC))

    if not HY3D_CKPT.exists():
        raise FileNotFoundError(
            f"Hunyuan3D-2 weights not found at {HY3D_DIR}.\n"
            "Download: huggingface-cli download tencent/Hunyuan3D-2 "
            f"--local-dir {HY3D_DIR}"
        )

    log("Loading Hunyuan3D-2 pipeline...", "info")

    # Official Hunyuan3D-2 pipeline import
    from hy3dgen.shapegen import Hunyuan3DDiTFlowMatchingPipeline
    from hy3dgen.texgen import Hunyuan3DPaintPipeline

    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype  = torch.float16 if device == "cuda" else torch.float32

    shape_pipe = Hunyuan3DDiTFlowMatchingPipeline.from_pretrained(
        str(HY3D_CKPT), torch_dtype=dtype
    ).to(device)

    img = Image.open(image_path).convert("RGBA").resize((512, 512))
    log(f"Running Hunyuan3D-2 shape gen on {device}...", "info")

    mesh = shape_pipe(
        image=img,
        num_inference_steps=30,
        guidance_scale=5.0,
    ).meshes[0]

    # Texture baking with Hunyuan3DPaintPipeline
    try:
        tex_pipe = Hunyuan3DPaintPipeline.from_pretrained(
            str(HY3D_DIR / "hunyuan3d-2-paint"), torch_dtype=dtype
        ).to(device)
        log("Running texture bake...", "info")
        mesh = tex_pipe(mesh=mesh, image=img).meshes[0]
    except Exception as te:
        log(f"Texture bake skipped: {te}", "warn")

    mesh.export(str(output_path))
    log(f"Hunyuan3D-2 GLB saved: {os.path.getsize(output_path)} bytes", "info")


def generate_mesh_hunyuan3d(image_path, output_path):
    try:
        import rembg
        import numpy as np
        import trimesh
        from PIL import Image
        from io import BytesIO

        # Background removal
        log("Removing background with rembg...", "info")
        with open(image_path, "rb") as f:
            img_bytes = rembg.remove(f.read())
        img_rgba = Image.open(BytesIO(img_bytes)).convert("RGBA")

        hy3d_ok = False
        try:
            _run_hunyuan3d(image_path, output_path)
            hy3d_ok = True
        except FileNotFoundError as e:
            log(str(e), "warn")
            log("Falling back to TRELLIS → TripoSR chain...", "warn")
        except Exception as e:
            log(f"Hunyuan3D-2 failed: {e} — falling back", "warn")

        if not hy3d_ok:
            # Fallback chain: try TRELLIS then TripoSR
            try:
                from run_trellis import generate_mesh_trellis
                result = generate_mesh_trellis(image_path, str(output_path))
                result["model"] = "hunyuan3d-fallback-trellis"
                return result
            except Exception:
                from run_triposr import generate_mesh_triposr
                result = generate_mesh_triposr(image_path, str(output_path))
                result["model"] = "hunyuan3d-fallback-triposr"
                return result

        # Apply PBR color if no texture bake
        try:
            mesh = trimesh.load(str(output_path), force="mesh")
            if not hasattr(mesh.visual, "material") or mesh.visual.material is None:
                arr = np.array(img_rgba)
                mask = arr[:, :, 3] > 64
                avg = arr[:, :, :3][mask].mean(axis=0) if mask.sum() > 0 else [128, 128, 128]
                r, g, b = np.array(avg) / 255.0
                mesh.visual = trimesh.visual.TextureVisuals(
                    material=trimesh.visual.material.PBRMaterial(
                        baseColorFactor=np.array([r, g, b, 1.0]),
                        roughnessFactor=0.5,
                        metallicFactor=0.1,
                    )
                )
                mesh.export(str(output_path))
        except Exception as ce:
            log(f"Color fallback skipped: {ce}", "warn")

        size = os.path.getsize(output_path)
        return {
            "model": "hunyuan3d-2",
            "image_path": image_path,
            "output_path": str(output_path),
            "glb_size_bytes": size,
            "hunyuan3d_used": True,
            "method": "hunyuan3d-2-mv-turbo",
            "license": "Community (commercial with attribution)",
        }

    except Exception as e:
        import traceback
        log(traceback.format_exc(), "error")
        error_exit(f"Hunyuan3D-2 pipeline failed: {str(e)}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        error_exit("Usage: run_hunyuan3d.py <input_image> <output_glb>")
    if not os.path.exists(sys.argv[1]):
        error_exit(f"Input image not found: {sys.argv[1]}")
    success_exit(generate_mesh_hunyuan3d(sys.argv[1], sys.argv[2]))
