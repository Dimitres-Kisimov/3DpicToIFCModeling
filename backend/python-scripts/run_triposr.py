"""
TripoSR inference — real single-image 3D reconstruction.
Improvements: SAM2 segmentation, Poisson refinement, Humphrey smoothing.
Weights cached after first run. GPU-accelerated when available.
"""

import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "triposr"))

from inference_base import log, error_exit, success_exit

# SAM2 checkpoint — downloaded to models/sam2/
SAM2_CHECKPOINT = str(Path(__file__).parent.parent.parent / "models" / "sam2" / "sam2.1_hiera_tiny.pt")
SAM2_CONFIG    = "configs/sam2.1/sam2.1_hiera_t.yaml"


def segment_with_sam2(image_path):
    """
    Use SAM2 to produce a pixel-perfect foreground mask.
    Automatically picks the largest detected object (the furniture piece).
    Falls back to rembg if SAM2 fails.
    Returns: PIL Image in RGBA with clean alpha mask.
    """
    try:
        import torch
        import numpy as np
        from PIL import Image
        from sam2.build_sam import build_sam2
        from sam2.sam2_image_predictor import SAM2ImagePredictor

        device = "cuda" if torch.cuda.is_available() else "cpu"
        img = Image.open(image_path).convert("RGB")
        img_np = np.array(img)

        log("Loading SAM2 model...", "info")
        sam2_model = build_sam2(SAM2_CONFIG, SAM2_CHECKPOINT, device=device)
        predictor = SAM2ImagePredictor(sam2_model)
        predictor.set_image(img_np)

        # Use a grid of points across the image centre to find the main object
        h, w = img_np.shape[:2]
        cx, cy = w // 2, h // 2
        # Prompt with centre + surrounding points — picks up the main object
        point_coords = np.array([
            [cx, cy],
            [cx - w // 6, cy],
            [cx + w // 6, cy],
            [cx, cy - h // 6],
            [cx, cy + h // 6],
        ])
        point_labels = np.ones(len(point_coords), dtype=np.int32)

        masks, scores, _ = predictor.predict(
            point_coords=point_coords,
            point_labels=point_labels,
            multimask_output=True,
        )

        # Pick the mask with highest score
        best_mask = masks[scores.argmax()]

        # Build RGBA image: object pixels keep colour, background becomes transparent
        rgba = np.zeros((h, w, 4), dtype=np.uint8)
        rgba[:, :, :3] = img_np
        rgba[:, :, 3]  = (best_mask * 255).astype(np.uint8)

        log(f"SAM2 segmentation OK — mask coverage: "
            f"{best_mask.sum() / best_mask.size * 100:.1f}%", "info")

        # Free SAM2 from GPU before TripoSR loads
        del sam2_model, predictor
        if device == "cuda":
            torch.cuda.empty_cache()

        return Image.fromarray(rgba)

    except Exception as e:
        log(f"SAM2 failed ({e}), falling back to rembg", "warn")
        import rembg
        rembg_session = rembg.new_session()
        return rembg.remove(Image.open(image_path).convert("RGB"), session=rembg_session)


def poisson_refine(mesh):
    """
    Poisson surface reconstruction via pyvista.
    Produces a cleaner, smoother, fully watertight mesh from the raw
    marching-cubes output. Particularly improves flat surfaces.
    Falls back to the original mesh if pyvista fails.
    """
    try:
        import pyvista as pv
        import numpy as np
        import trimesh

        log("Running Poisson surface reconstruction...", "info")

        # Convert trimesh → pyvista PolyData
        faces_pv = np.hstack([
            np.full((len(mesh.faces), 1), 3, dtype=np.int_),
            mesh.faces
        ])
        cloud = pv.PolyData(mesh.vertices, faces_pv)

        # Compute normals then reconstruct
        cloud_with_normals = cloud.compute_normals(
            cell_normals=False, point_normals=True, consistent_normals=True
        )
        reconstructed = cloud_with_normals.reconstruct_surface(
            nbr_sz=20,         # neighbourhood size
            sample_spacing=None
        )
        triangulated = reconstructed.triangulate()

        # Convert back to trimesh
        verts = np.array(triangulated.points)
        faces_raw = triangulated.faces.reshape(-1, 4)[:, 1:]
        refined = trimesh.Trimesh(vertices=verts, faces=faces_raw, process=True)

        if len(refined.faces) > 100:
            log(f"Poisson refinement OK — {len(refined.faces)} faces", "info")
            return refined
        else:
            log("Poisson produced too-small mesh, keeping original", "warn")
            return mesh

    except Exception as e:
        log(f"Poisson refinement skipped: {e}", "warn")
        return mesh


def generate_mesh_triposr(image_path, output_path):
    try:
        import numpy as np
        import torch
        import trimesh
        from PIL import Image
        from tsr.system import TSR
        from tsr.utils import remove_background, resize_foreground

        device = "cuda" if torch.cuda.is_available() else "cpu"
        log(f"Device: {device}", "info")

        # ── Step 1: SAM2 segmentation ────────────────────────────────────────
        log("Segmenting with SAM2...", "info")
        img_rgba = segment_with_sam2(image_path)

        # Resize foreground to 85% of canvas, composite onto gray background
        from tsr.utils import resize_foreground as _resize_fg
        img_rgba = _resize_fg(img_rgba, 0.85)
        img_arr = np.array(img_rgba).astype(np.float32) / 255.0
        img_arr = img_arr[:, :, :3] * img_arr[:, :, 3:4] + (1 - img_arr[:, :, 3:4]) * 0.5
        image = Image.fromarray((img_arr * 255.0).astype(np.uint8))
        log("Input image prepared", "info")

        # ── Step 2: TripoSR inference ────────────────────────────────────────
        log("Loading TripoSR model...", "info")
        model = TSR.from_pretrained(
            "stabilityai/TripoSR",
            config_name="config.yaml",
            weight_name="model.ckpt",
        )
        model.renderer.set_chunk_size(8192 if device == "cuda" else 2048)
        model.to(device)
        log("Model loaded", "info")

        log("Running TripoSR inference...", "info")
        with torch.no_grad():
            scene_codes = model([image], device=device)

        mc_resolution = 256 if device == "cuda" else 96
        log(f"Extracting mesh at resolution {mc_resolution}...", "info")
        meshes = model.extract_mesh(scene_codes, True, resolution=mc_resolution)
        mesh = meshes[0]

        # Free TripoSR from GPU before Poisson pass
        del model
        if device == "cuda":
            torch.cuda.empty_cache()

        # ── Post-processing ──────────────────────────────────────────────────

        # 3. Component filtering — keep significant parts, remove spikes/noise
        components = mesh.split(only_watertight=False)
        if components:
            total_faces = sum(len(c.faces) for c in components)
            kept = []
            for c in components:
                face_ratio = len(c.faces) / total_faces
                if face_ratio < 0.005:
                    continue
                extents = c.bounding_box.extents
                if extents.max() > 0:
                    compactness = extents.min() / extents.max()
                    if compactness < 0.04 and face_ratio < 0.05:
                        continue
                kept.append(c)
            if kept:
                mesh = trimesh.util.concatenate(kept)
                log(f"Kept {len(kept)}/{len(components)} components, {len(mesh.faces)} faces", "info")

        # 4. Center at origin
        mesh.apply_translation(-mesh.bounding_box.centroid)

        # 5. Orientation fix — face normal area vote
        face_normals = mesh.face_normals
        face_areas   = mesh.area_faces
        up_area   = face_areas[face_normals[:, 1] >  0.5].sum()
        down_area = face_areas[face_normals[:, 1] < -0.5].sum()
        if down_area > up_area:
            R = trimesh.transformations.rotation_matrix(np.pi, [1, 0, 0])
            mesh.apply_transform(R)
            log("Orientation corrected (flipped)", "info")
        else:
            log("Orientation OK", "info")

        # 6. Poisson surface reconstruction — smoother, watertight mesh
        mesh = poisson_refine(mesh)

        # 7. Humphrey smoothing — preserves volume and sharp edges better than Laplacian
        trimesh.smoothing.filter_humphrey(mesh, iterations=5, beta=0.5)
        log("Humphrey smoothing applied", "info")

        # 8. PBR material — dominant color cluster from SAM2 mask
        try:
            rgba_arr = np.array(img_rgba)
            alpha_mask = rgba_arr[:, :, 3] > 64
            if alpha_mask.sum() > 0:
                fg_pixels = rgba_arr[:, :, :3][alpha_mask].astype(np.float32)
                # K-means with k=3, pick the largest cluster as dominant color
                from scipy.cluster.vq import kmeans, vq
                k = min(3, len(fg_pixels))
                centroids, _ = kmeans(fg_pixels, k)
                labels, _ = vq(fg_pixels, centroids)
                counts = np.bincount(labels)
                dominant = centroids[counts.argmax()]
                avg_color = dominant
            else:
                avg_color = np.array([120, 120, 120], dtype=np.float32)

            r, g, b = avg_color[0] / 255.0, avg_color[1] / 255.0, avg_color[2] / 255.0
            log(f"Dominant color: rgb({int(avg_color[0])}, {int(avg_color[1])}, {int(avg_color[2])})", "info")

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
            "method": "triposr-sam2-poisson-humphrey",
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
