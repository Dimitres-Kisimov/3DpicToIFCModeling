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


def _rembg_foreground(image_path):
    """rembg (U^2-Net) salient-object cutout -> RGBA PIL image."""
    import rembg
    from io import BytesIO
    from PIL import Image as _Image
    cut_bytes = rembg.remove(open(image_path, "rb").read())
    # rembg returns PNG-encoded bytes; downstream resize_foreground() wants PIL RGBA
    return _Image.open(BytesIO(cut_bytes)).convert("RGBA")


def _segment_foreground(image_path):
    """Foreground segmentation. SCS_TRIPOSR_SEGMENTER selects the engine:
    'rembg' (default — deterministic U2-Net, the April-proven cutout) or
    'sam2' (opt-in; auto-prompting is unstable on product photos)."""
    if os.environ.get("SCS_TRIPOSR_SEGMENTER", "rembg").lower() == "rembg":
        log("Segmenter: rembg (default)", "info")
        return _rembg_foreground(image_path)
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
        return _rembg_foreground(image_path)


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

        # ── Centralised post-processing ──────────────────────────────────────
        # Relaxed component filter (keeps vertical thin legs) + mirror symmetry
        # across X = 0 (no per-leg drift) + vertex merge + Humphrey smoothing.
        # All steps live in _triposr_postprocess.py so the cascade fallback in
        # run_detect_and_place.py uses the same logic.
        from _triposr_postprocess import clean_triposr_mesh
        mesh = clean_triposr_mesh(mesh)
        log(f"Post-processed: {len(mesh.faces)} faces", "info")

        # CLIP classification (needs only the photo) — moved up so the repair
        # pack below can pick its archetype from the detected label.
        from inference_base import classify_object_clip, estimate_metric_scale
        clip_result = classify_object_clip(image_path)

        # Archetype repair packs — proven on the 170-item internet-photo
        # benchmark (faces 9.2x lighter, 48 bases rebuilt, 91% watertight).
        # Kill-switch: SCS_REPAIR_PACKS=0 restores the pre-pack pipeline.
        if os.environ.get("SCS_REPAIR_PACKS", "1") != "0":
            try:
                from repair_packs import repair_mesh
                mesh, rep = repair_mesh(mesh, label=clip_result.get("label"),
                                        category=clip_result.get("category"))
                log(f"Repair pack '{rep.get('archetype')}': "
                    f"{rep.get('faces_in')} -> {len(mesh.faces)} faces", "info")
            except Exception as rpe:
                log(f"Repair packs skipped: {rpe}", "warn")

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

        # Improvement 3: metric scale estimation (classification already done above)
        scale = estimate_metric_scale(image_path, mask_rgba=img_rgba,
                                      category=clip_result.get("label"))

        # Scale the mesh to estimated real-world dimensions
        try:
            extents = mesh.bounding_box.extents
            if extents.max() > 0:
                scale_factor = scale["height_m"] / extents.max()
                mesh.apply_scale(scale_factor)
                mesh.export(output_path)  # re-export with scaled mesh
                log(f"Mesh scaled to {scale['height_m']}m (factor {scale_factor:.4f})", "info")
        except Exception as se:
            log(f"Scale application skipped: {se}", "warn")

        return {
            "model": "triposr",
            "image_path": image_path,
            "output_path": output_path,
            "glb_size_bytes": size,
            "device": device,
            "method": "triposr-real+clip+depth-scale",
            "faces": len(mesh.faces),
            "ifc_class": clip_result["ifc_class"],
            "ifc_category": clip_result["category"],
            "object_label": clip_result["label"],
            "clip_confidence": clip_result["score"],
            "estimated_dimensions_m": scale,
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
