"""
Sprint 1 — InstantMesh real pipeline (TencentARC/InstantMesh)
Pipeline:
  1. rembg background removal
  2. Zero123++ multi-view synthesis  →  6 orbital views
  3. InstantMesh LRM               →  dense 3D mesh
  4. PBR color from source image
  5. Export GLB

Weights are downloaded on first run (~7 GB):
  - sudo pip install zero123plus  (or from TencentARC/zero123plus HF space)
  - instantmesh weights: TencentARC/InstantMesh

Fallback: if weights aren't present, runs the YOLO+DPT depth mesh
          (same as the original placeholder).
"""

import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from inference_base import log, error_exit, success_exit, generate_segmented_depth_mesh

# ─── Paths ────────────────────────────────────────────────────────────────────
MODELS_DIR       = Path(__file__).parent.parent.parent / "models"
INSTANTMESH_DIR  = MODELS_DIR / "instantmesh"
ZERO123_DIR      = MODELS_DIR / "zero123plus"

INSTANTMESH_CKPT = INSTANTMESH_DIR / "instantmesh-large.ckpt"
INSTANTMESH_CFG  = INSTANTMESH_DIR / "config.yaml"


# ─── Multi-view synthesis via Zero123++ ───────────────────────────────────────

def _synthesize_multiview(image_pil, num_views=6):
    """
    Generate `num_views` orbital renderings with Zero123++.
    Returns list of PIL Images.
    """
    try:
        import torch
        from diffusers import DiffusionPipeline, EulerAncestralDiscreteScheduler

        log("Loading Zero123++ pipeline...", "info")
        pipe = DiffusionPipeline.from_pretrained(
            "sudo-ai/zero123plus-v1.2",
            custom_pipeline="sudo-ai/zero123plus-pipeline",
            torch_dtype=torch.float16,
            cache_dir=str(ZERO123_DIR),
        )
        pipe.scheduler = EulerAncestralDiscreteScheduler.from_config(
            pipe.scheduler.config, timestep_spacing="trailing"
        )
        device = "cuda" if torch.cuda.is_available() else "cpu"
        pipe.to(device)
        log(f"Zero123++ on {device}", "info")

        result = pipe(image_pil, num_inference_steps=36).images[0]

        # Zero123++ returns a 2×3 grid of 320×320 tiles
        W, H = result.size           # 960×640
        tile_w, tile_h = W // 3, H // 2
        views = []
        for row in range(2):
            for col in range(3):
                box = (col * tile_w, row * tile_h,
                       (col + 1) * tile_w, (row + 1) * tile_h)
                views.append(result.crop(box))

        log(f"Generated {len(views)} views", "info")
        return views

    except Exception as e:
        log(f"Zero123++ failed ({e}) — using single view", "warn")
        return [image_pil]


# ─── LRM reconstruction ───────────────────────────────────────────────────────

def _reconstruct_lrm(views, output_path):
    """
    Run InstantMesh LRM on a list of views and save GLB.
    Requires instantmesh weights at INSTANTMESH_CKPT.
    """
    import torch
    import numpy as np
    import importlib

    if not INSTANTMESH_CKPT.exists():
        raise FileNotFoundError(
            f"InstantMesh weights not found at {INSTANTMESH_CKPT}.\n"
            "Download: huggingface-cli download TencentARC/InstantMesh "
            f"--local-dir {INSTANTMESH_DIR}"
        )

    log("Loading InstantMesh LRM...", "info")
    # Dynamically import the InstantMesh repo if it was cloned to models/instantmesh/src
    src_dir = INSTANTMESH_DIR / "src"
    if src_dir.exists():
        sys.path.insert(0, str(src_dir))

    from instantmesh.models import InstantMesh  # from cloned repo

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = InstantMesh.from_pretrained(str(INSTANTMESH_CKPT))
    model.to(device).eval()

    from torchvision import transforms
    xform = transforms.Compose([
        transforms.Resize((512, 512)),
        transforms.ToTensor(),
    ])

    frames = torch.stack([xform(v.convert("RGB")) for v in views]).unsqueeze(0).to(device)
    log(f"Running LRM on {frames.shape[1]} views...", "info")

    with torch.no_grad():
        mesh = model.forward_mesh(frames)

    mesh.export(str(output_path))
    log(f"LRM GLB saved: {os.path.getsize(output_path)} bytes", "info")


# ─── Full pipeline ────────────────────────────────────────────────────────────

def generate_mesh_instantmesh(image_path, output_path):
    try:
        import rembg
        import numpy as np
        import trimesh
        from PIL import Image

        # Step 1 — background removal
        log("Removing background with rembg...", "info")
        with open(image_path, "rb") as f:
            img_bytes = rembg.remove(f.read())
        from io import BytesIO
        img_rgba = Image.open(BytesIO(img_bytes)).convert("RGBA")

        # Composite onto white for Zero123++
        bg = Image.new("RGB", img_rgba.size, (255, 255, 255))
        bg.paste(img_rgba, mask=img_rgba.split()[3])
        img_rgb = bg.resize((320, 320))

        # Step 2 — multi-view synthesis
        views = _synthesize_multiview(img_rgb)

        # Step 3 — LRM reconstruction (with fallback)
        lrm_ok = False
        try:
            _reconstruct_lrm(views, output_path)
            lrm_ok = True
        except FileNotFoundError as e:
            log(str(e), "warn")
            log("Falling back to YOLO+DPT depth mesh", "warn")
        except Exception as e:
            log(f"LRM failed: {e} — falling back to YOLO+DPT", "warn")

        if not lrm_ok:
            glb_data = generate_segmented_depth_mesh(
                image_path, resolution=128, depth_model="Intel/dpt-hybrid-midas"
            )
            with open(output_path, "wb") as f:
                f.write(glb_data)

        # Step 4 — apply PBR color from source image average
        try:
            mesh = trimesh.load(str(output_path), force="mesh")
            img_arr = np.array(img_rgba)
            alpha_mask = img_arr[:, :, 3] > 64
            if alpha_mask.sum() > 0:
                avg = img_arr[:, :, :3][alpha_mask].mean(axis=0)
            else:
                avg = np.array([128, 128, 128], dtype=float)
            r, g, b = avg / 255.0
            mesh.visual = trimesh.visual.TextureVisuals(
                material=trimesh.visual.material.PBRMaterial(
                    baseColorFactor=np.array([r, g, b, 1.0]),
                    roughnessFactor=0.6,
                    metallicFactor=0.1,
                )
            )
            mesh.export(str(output_path))
            log(f"PBR color applied: rgb({int(avg[0])},{int(avg[1])},{int(avg[2])})", "info")
        except Exception as ce:
            log(f"Color step skipped: {ce}", "warn")

        size = os.path.getsize(output_path)
        return {
            "model": "instantmesh",
            "image_path": image_path,
            "output_path": str(output_path),
            "glb_size_bytes": size,
            "lrm_used": lrm_ok,
            "method": "zero123plus+lrm" if lrm_ok else "yolo-seg+dpt-fallback",
        }

    except Exception as e:
        import traceback
        log(traceback.format_exc(), "error")
        error_exit(f"InstantMesh pipeline failed: {str(e)}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        error_exit("Usage: run_instantmesh.py <input_image> <output_glb>")
    if not os.path.exists(sys.argv[1]):
        error_exit(f"Input image not found: {sys.argv[1]}")
    success_exit(generate_mesh_instantmesh(sys.argv[1], sys.argv[2]))
