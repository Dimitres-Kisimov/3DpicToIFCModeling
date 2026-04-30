"""
TripoSR inference — real single-image 3D reconstruction.
Weights cached after first run. GPU-accelerated when available.
"""

import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "triposr"))

from inference_base import log, error_exit, success_exit


def generate_mesh_triposr(image_path, output_path):
    try:
        import numpy as np
        import torch
        import trimesh
        import rembg
        from PIL import Image
        from tsr.system import TSR
        from tsr.utils import remove_background, resize_foreground

        device = "cuda" if torch.cuda.is_available() else "cpu"
        log(f"Device: {device}", "info")

        log("Loading TripoSR model...", "info")
        model = TSR.from_pretrained(
            "stabilityai/TripoSR",
            config_name="config.yaml",
            weight_name="model.ckpt",
        )
        model.renderer.set_chunk_size(8192 if device == "cuda" else 2048)
        model.to(device)
        log("Model loaded", "info")

        # Remove background and composite onto gray
        log("Removing background...", "info")
        rembg_session = rembg.new_session()
        img_rgba = remove_background(Image.open(image_path), rembg_session)
        img_rgba = resize_foreground(img_rgba, 0.85)
        img_arr = np.array(img_rgba).astype(np.float32) / 255.0
        img_arr = img_arr[:, :, :3] * img_arr[:, :, 3:4] + (1 - img_arr[:, :, 3:4]) * 0.5
        image = Image.fromarray((img_arr * 255.0).astype(np.uint8))
        log("Background removed", "info")

        # Run inference
        log("Running TripoSR inference...", "info")
        with torch.no_grad():
            scene_codes = model([image], device=device)

        mc_resolution = 256 if device == "cuda" else 96
        log(f"Extracting mesh at resolution {mc_resolution}...", "info")
        meshes = model.extract_mesh(scene_codes, True, resolution=mc_resolution)
        mesh = meshes[0]

        # ── Post-processing ──────────────────────────────────────────────────

        # 1. Component filtering — keep significant parts, remove spikes/noise
        components = mesh.split(only_watertight=False)
        if components:
            total_faces = sum(len(c.faces) for c in components)
            kept = []
            for c in components:
                face_ratio = len(c.faces) / total_faces
                if face_ratio < 0.005:
                    continue  # too small — floating debris
                # Reject needle-like spike artifacts by checking aspect ratio
                extents = c.bounding_box.extents
                if extents.max() > 0:
                    compactness = extents.min() / extents.max()
                    if compactness < 0.04 and face_ratio < 0.05:
                        continue  # spike with low mass — artifact
                kept.append(c)

            if kept:
                mesh = trimesh.util.concatenate(kept)
                log(f"Kept {len(kept)}/{len(components)} components, {len(mesh.faces)} faces", "info")

        # 2. Center mesh at origin
        mesh.apply_translation(-mesh.bounding_box.centroid)

        # 3. Orientation fix — TripoSR sometimes outputs upside-down
        #    Heuristic: if vertex mass is above Y=0 (heavy top = upside down), flip
        centroid_y = mesh.vertices[:, 1].mean()
        if centroid_y > 0.05:
            R = trimesh.transformations.rotation_matrix(np.pi, [1, 0, 0])
            mesh.apply_transform(R)
            log("Applied orientation correction (flipped)", "info")

        # 4. Laplacian smoothing — reduce faceted look while preserving structure
        trimesh.smoothing.filter_laplacian(mesh, iterations=5)
        log("Mesh smoothed", "info")

        # 5. Apply PBR material color so xeokit renders it correctly
        #    Average foreground color from rembg alpha mask
        try:
            rgba_arr = np.array(img_rgba)
            alpha_mask = rgba_arr[:, :, 3] > 64
            if alpha_mask.sum() > 0:
                fg_pixels = rgba_arr[:, :, :3][alpha_mask]
                avg_color = fg_pixels.mean(axis=0)
            else:
                avg_color = np.array([120, 120, 120], dtype=np.float64)

            r, g, b = avg_color[0] / 255.0, avg_color[1] / 255.0, avg_color[2] / 255.0
            log(f"Applying PBR color: rgb({int(avg_color[0])}, {int(avg_color[1])}, {int(avg_color[2])})", "info")

            mesh.visual = trimesh.visual.TextureVisuals(
                material=trimesh.visual.material.PBRMaterial(
                    baseColorFactor=np.array([r, g, b, 1.0]),
                    roughnessFactor=0.7,
                    metallicFactor=0.0,
                )
            )
        except Exception as ce:
            log(f"Coloring skipped: {ce}", "warn")

        # Export
        mesh.export(output_path)
        size = os.path.getsize(output_path)
        log(f"GLB saved: {size} bytes", "info")

        return {
            "model": "triposr",
            "image_path": image_path,
            "output_path": output_path,
            "glb_size_bytes": size,
            "device": device,
            "method": "triposr-real",
            "faces": len(mesh.faces),
        }

    except Exception as e:
        import traceback
        log(traceback.format_exc(), "error")
        error_exit(f"TripoSR inference failed: {str(e)}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        error_exit("Usage: run_triposr.py <input_image> <output_glb>")
    if not os.path.exists(sys.argv[1]):
        error_exit(f"Input image not found: {sys.argv[1]}")
    success_exit(generate_mesh_triposr(sys.argv[1], sys.argv[2]))
