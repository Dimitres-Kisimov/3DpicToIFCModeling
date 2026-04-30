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

SAM2_CHECKPOINT = str(Path(__file__).parent.parent.parent / "models" / "sam2" / "sam2.1_hiera_tiny.pt")
SAM2_CONFIG = "configs/sam2.1/sam2.1_hiera_t.yaml"


def _segment_foreground(image_path):
    """SAM2 segmentation with rembg fallback."""
    try:
        import torch
        import numpy as np
        from PIL import Image
        from sam2.build_sam import build_sam2
        from sam2.sam2_image_predictor import SAM2ImagePredictor

        device = "cuda" if torch.cuda.is_available() else "cpu"
        img_np = np.array(Image.open(image_path).convert("RGB"))
        h, w = img_np.shape[:2]

        sam2 = build_sam2(SAM2_CONFIG, SAM2_CHECKPOINT, device=device)
        predictor = SAM2ImagePredictor(sam2)
        predictor.set_image(img_np)

        # Centre-point grid prompt — finds the main object
        cx, cy = w // 2, h // 2
        pts = np.array([[cx, cy], [cx - w//6, cy], [cx + w//6, cy],
                        [cx, cy - h//6], [cx, cy + h//6]])
        labels = np.ones(len(pts), dtype=np.int32)
        masks, scores, _ = predictor.predict(point_coords=pts,
                                              point_labels=labels,
                                              multimask_output=True)
        best = masks[scores.argmax()]
        rgba = np.zeros((h, w, 4), dtype=np.uint8)
        rgba[:, :, :3] = img_np
        rgba[:, :, 3] = (best * 255).astype(np.uint8)

        del sam2, predictor
        if device == "cuda":
            torch.cuda.empty_cache()

        log(f"SAM2 OK — coverage {best.sum() / best.size * 100:.1f}%", "info")
        return Image.fromarray(rgba)

    except Exception as e:
        log(f"SAM2 failed ({e}), using rembg", "warn")
        import rembg
        return rembg.remove(open(image_path, "rb").read())


def generate_mesh_triposr(image_path, output_path):
    try:
        import numpy as np
        import torch
        import trimesh
        from PIL import Image
        from tsr.system import TSR
        from tsr.utils import resize_foreground

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

        # Remove background — SAM2 preferred, rembg fallback
        log("Segmenting foreground...", "info")
        img_rgba = _segment_foreground(image_path)
        img_rgba = resize_foreground(img_rgba, 0.85)
        img_arr = np.array(img_rgba).astype(np.float32) / 255.0
        img_arr = img_arr[:, :, :3] * img_arr[:, :, 3:4] + (1 - img_arr[:, :, 3:4]) * 0.5
        image = Image.fromarray((img_arr * 255.0).astype(np.uint8))
        log("Foreground segmented", "info")

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

        # 4. Humphrey smoothing — preserves volume and sharp edges better than
        #    Laplacian. beta=0.5 pulls each vertex back toward original position
        #    after each smooth pass, preventing shrinkage and corner rounding.
        trimesh.smoothing.filter_humphrey(mesh, iterations=5, beta=0.5)
        log("Mesh smoothed (Humphrey)", "info")

        # 5. Apply PBR material — dominant color via k-means (k=3) on SAM2 mask
        #    More accurate than mean: picks the actual object color, not a
        #    blend that includes background tones leaked by rembg.
        try:
            from scipy.cluster.vq import kmeans, vq
            rgba_arr = np.array(img_rgba)
            alpha_mask = rgba_arr[:, :, 3] > 64
            if alpha_mask.sum() > 0:
                fg_pixels = rgba_arr[:, :, :3][alpha_mask].astype(np.float32)
                k = min(3, len(fg_pixels))
                centroids, _ = kmeans(fg_pixels, k)
                labels, _ = vq(fg_pixels, centroids)
                counts = np.bincount(labels)
                avg_color = centroids[counts.argmax()]
            else:
                avg_color = np.array([120, 120, 120], dtype=np.float32)

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
