"""
Detection + depth + retrieval-or-primitive pipeline.

Stages on each request:
  1. DETR ResNet-50 detection on the input image
  2. Depth Anything V2 Metric (indoor, small) depth map for metric H x W
  3. (optional) DINOv2 + FAISS retrieval against a local mesh library, if the
     index exists under data/mesh_library/index.faiss. Falls back to the
     category-keyed primitive mesh library when no index is present.
  4. Sample dominant colour from the photo bbox crop and apply as PBR base colour
  5. Export GLB with proper PBR material
  6. Return rich metadata for the UI, including ifcClass that the IFC writer
     uses to set the correct entity type (IfcChair vs IfcTable vs IfcFurniture...)

This is the empirically-validated working replacement for the broken TripoSR
adapter.  Once the ABO retrieval index is built, retrieval takes over from
the primitive library with no other code changes.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import torch
import trimesh
from PIL import Image


REPO_ROOT = Path(__file__).resolve().parents[2]
MESH_LIBRARY_DIR = REPO_ROOT / "data" / "mesh_library"
MESH_INDEX_PATH = MESH_LIBRARY_DIR / "index.faiss"
MESH_MANIFEST_PATH = MESH_LIBRARY_DIR / "manifest.json"


# ---------------------------------------------------------------------------
# Category and IFC4 entity-class map
# ---------------------------------------------------------------------------
# COCO label -> (SCS category, IFC4 entity class, default H x W x D fallback in m)
COCO_TO_IFC = {
    "chair":           ("office_chair",    "IfcChair",                  (0.95, 0.55, 0.55)),
    "couch":           ("sofa",            "IfcFurniture",              (0.85, 2.00, 0.90)),
    "bench":           ("bench",           "IfcFurniture",              (0.45, 1.50, 0.40)),
    "dining table":    ("table",           "IfcTable",                  (0.74, 1.80, 0.90)),
    "tv":              ("monitor",         "IfcAudioVisualAppliance",   (0.55, 1.00, 0.10)),
    "laptop":          ("laptop",          "IfcCommunicationsAppliance", (0.02, 0.36, 0.25)),
    "keyboard":        ("keyboard",        "IfcInputDevice",            (0.03, 0.45, 0.15)),
    "mouse":           ("mouse",           "IfcInputDevice",            (0.04, 0.12, 0.07)),
    "book":            ("book",            "IfcFurniture",              (0.30, 0.22, 0.03)),
    "vase":            ("vase",            "IfcFurniture",              (0.30, 0.15, 0.15)),
    "bottle":          ("bottle",          "IfcFurniture",              (0.25, 0.07, 0.07)),
    "cup":             ("cup",             "IfcFurniture",              (0.10, 0.08, 0.08)),
    "potted plant":    ("plant",           "IfcFurniture",              (0.50, 0.30, 0.30)),
    "refrigerator":    ("appliance",       "IfcElectricAppliance",      (1.70, 0.65, 0.65)),
    "microwave":       ("appliance",       "IfcElectricAppliance",      (0.30, 0.55, 0.40)),
    "oven":            ("appliance",       "IfcElectricAppliance",      (0.85, 0.60, 0.60)),
    "toaster":         ("appliance",       "IfcElectricAppliance",      (0.20, 0.30, 0.20)),
    "sink":            ("sink",            "IfcSanitaryTerminal",       (0.20, 0.60, 0.50)),
    "clock":           ("clock",           "IfcFurniture",              (0.30, 0.30, 0.05)),
}

DEFAULT_MAPPING = ("furniture", "IfcFurnishingElement", (0.80, 0.60, 0.60))


# ---------------------------------------------------------------------------
# Category-specific primitive mesh library
# ---------------------------------------------------------------------------
def _chair_mesh(h, w, d):
    parts = []
    seat_h = 0.05
    seat = trimesh.creation.box(extents=[w, d, seat_h]); seat.apply_translation([0, 0, h * 0.45]); parts.append(seat)
    back = trimesh.creation.box(extents=[w, 0.05, h * 0.45]); back.apply_translation([0, -d / 2 + 0.025, h * 0.7]); parts.append(back)
    leg_h = h * 0.45
    leg_inset = 0.04
    for x in [-w / 2 + leg_inset, w / 2 - leg_inset]:
        for y in [-d / 2 + leg_inset, d / 2 - leg_inset]:
            leg = trimesh.creation.cylinder(radius=0.025, height=leg_h, sections=16)
            leg.apply_translation([x, y, leg_h / 2]); parts.append(leg)
    return trimesh.util.concatenate(parts)


def _table_mesh(h, w, d):
    parts = []
    top_t = 0.04
    top = trimesh.creation.box(extents=[w, d, top_t]); top.apply_translation([0, 0, h - top_t / 2]); parts.append(top)
    leg_h = h - top_t
    leg_inset = 0.05
    for x in [-w / 2 + leg_inset, w / 2 - leg_inset]:
        for y in [-d / 2 + leg_inset, d / 2 - leg_inset]:
            leg = trimesh.creation.box(extents=[0.04, 0.04, leg_h])
            leg.apply_translation([x, y, leg_h / 2]); parts.append(leg)
    return trimesh.util.concatenate(parts)


def _sofa_mesh(h, w, d):
    parts = []
    base = trimesh.creation.box(extents=[w, d, h * 0.55]); base.apply_translation([0, 0, h * 0.275]); parts.append(base)
    back = trimesh.creation.box(extents=[w, 0.18, h * 0.55]); back.apply_translation([0, -d / 2 + 0.09, h * 0.7]); parts.append(back)
    arm_l = trimesh.creation.box(extents=[0.15, d * 0.6, h * 0.6]); arm_l.apply_translation([-w / 2 + 0.075, 0, h * 0.55]); parts.append(arm_l)
    arm_r = trimesh.creation.box(extents=[0.15, d * 0.6, h * 0.6]); arm_r.apply_translation([w / 2 - 0.075, 0, h * 0.55]); parts.append(arm_r)
    return trimesh.util.concatenate(parts)


def _monitor_mesh(h, w, d):
    parts = []
    screen = trimesh.creation.box(extents=[w, max(d, 0.03), h * 0.7])
    screen.apply_translation([0, 0, h * 0.5 + 0.05]); parts.append(screen)
    stand = trimesh.creation.box(extents=[w * 0.2, max(d, 0.10), 0.04])
    stand.apply_translation([0, 0, 0.02]); parts.append(stand)
    neck = trimesh.creation.cylinder(radius=0.03, height=0.05, sections=12)
    neck.apply_translation([0, 0, 0.05]); parts.append(neck)
    return trimesh.util.concatenate(parts)


def _laptop_mesh(h, w, d):
    base = trimesh.creation.box(extents=[w, d, max(h, 0.02)])
    return base


def _box_mesh(h, w, d):
    return trimesh.creation.box(extents=[w, d, h])


def _cylinder_mesh(h, w, d):
    return trimesh.creation.cylinder(radius=w / 2, height=h, sections=24)


def _plant_mesh(h, w, d):
    parts = []
    pot = trimesh.creation.cylinder(radius=w / 2, height=h * 0.4, sections=20)
    pot.apply_translation([0, 0, h * 0.2]); parts.append(pot)
    foliage = trimesh.creation.icosphere(radius=w * 0.6, subdivisions=2)
    foliage.apply_translation([0, 0, h * 0.7]); parts.append(foliage)
    return trimesh.util.concatenate(parts)


CATEGORY_MESH_BUILDERS = {
    "office_chair": _chair_mesh,
    "table":        _table_mesh,
    "bench":        _table_mesh,
    "sofa":         _sofa_mesh,
    "monitor":      _monitor_mesh,
    "laptop":       _laptop_mesh,
    "keyboard":     _box_mesh,
    "mouse":        _box_mesh,
    "book":         _box_mesh,
    "bottle":       _cylinder_mesh,
    "vase":         _cylinder_mesh,
    "cup":          _cylinder_mesh,
    "plant":        _plant_mesh,
    "appliance":    _box_mesh,
    "sink":         _box_mesh,
    "clock":        _box_mesh,
}


# ---------------------------------------------------------------------------
# Stage 1 — Detection (DETR ResNet-50)
# ---------------------------------------------------------------------------
def _detect_top_object(image: Image.Image):
    from transformers import DetrForObjectDetection, DetrImageProcessor
    device = "cuda" if torch.cuda.is_available() else "cpu"
    processor = DetrImageProcessor.from_pretrained("facebook/detr-resnet-50")
    model = DetrForObjectDetection.from_pretrained("facebook/detr-resnet-50").to(device)
    model.eval()
    inputs = processor(images=image, return_tensors="pt").to(device)
    with torch.no_grad():
        outputs = model(**inputs)
    target_sizes = torch.tensor([image.size[::-1]]).to(device)
    results = processor.post_process_object_detection(
        outputs, target_sizes=target_sizes, threshold=0.3
    )[0]
    del model, processor
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    if len(results["scores"]) == 0:
        return {"ok": False, "label": None, "score": 0.0, "box": None}
    best_idx = int(results["scores"].argmax().item())
    return {
        "ok": True,
        "label": model_id2label_safe(model_config_cache, int(results["labels"][best_idx].item())),
        "score": float(results["scores"][best_idx].item()),
        "box": [float(v) for v in results["boxes"][best_idx].cpu().numpy().tolist()],
    }


# Workaround: DETR's id2label is on the loaded model object, but we delete it.
# Keep a static copy of the COCO mapping by querying it once on import-time.
model_config_cache = None


def _coco_id2label_lazy():
    global model_config_cache
    if model_config_cache is None:
        from transformers import AutoConfig
        cfg = AutoConfig.from_pretrained("facebook/detr-resnet-50")
        model_config_cache = cfg.id2label
    return model_config_cache


def model_id2label_safe(_unused, label_id):
    table = _coco_id2label_lazy()
    return table.get(label_id, str(label_id))


# ---------------------------------------------------------------------------
# Stage 2 — Depth Anything V2 Metric (indoor, small)
# ---------------------------------------------------------------------------
def _estimate_metric_dimensions(image: Image.Image, box_xyxy, image_size):
    """Use Depth Anything V2 Metric-Indoor-Small to compute H x W from photo.

    Returns (h_m, w_m, d_m, depth_meta) where d_m is best-effort (we assume
    the object's depth is similar to its width unless it's a flat thing).
    """
    from transformers import AutoImageProcessor, AutoModelForDepthEstimation

    device = "cuda" if torch.cuda.is_available() else "cpu"
    mid = "depth-anything/Depth-Anything-V2-Metric-Indoor-Small-hf"
    processor = AutoImageProcessor.from_pretrained(mid)
    model = AutoModelForDepthEstimation.from_pretrained(mid).to(device)
    model.eval()

    inputs = processor(images=image, return_tensors="pt").to(device)
    with torch.no_grad():
        outputs = model(**inputs)

    # Resize predicted depth to original image size
    pred = outputs.predicted_depth.squeeze().detach().cpu().numpy()
    # pred is HxW in metres (metric model)
    H_pred, W_pred = pred.shape
    W_img, H_img = image.size

    # Mean depth inside the detection box (use centre 50% of bbox for robustness)
    x0, y0, x1, y1 = box_xyxy
    sx = W_pred / W_img
    sy = H_pred / H_img
    bx0 = max(0, int(x0 * sx)); by0 = max(0, int(y0 * sy))
    bx1 = min(W_pred, int(x1 * sx)); by1 = min(H_pred, int(y1 * sy))
    if bx1 <= bx0 or by1 <= by0:
        bx0, by0, bx1, by1 = 0, 0, W_pred, H_pred
    bw = bx1 - bx0; bh = by1 - by0
    cx0 = bx0 + bw // 4; cx1 = bx1 - bw // 4
    cy0 = by0 + bh // 4; cy1 = by1 - bh // 4
    crop = pred[cy0:cy1, cx0:cx1]
    if crop.size == 0:
        crop = pred[by0:by1, bx0:bx1]
    depth_m = float(np.median(crop))
    if not np.isfinite(depth_m) or depth_m <= 0:
        depth_m = float(np.median(pred))

    # Assume horizontal field of view of 60 degrees (smartphone wide-ish)
    HFOV_RAD = np.deg2rad(60.0)
    focal_px = W_img / (2.0 * np.tan(HFOV_RAD / 2.0))

    bbox_w_px = x1 - x0
    bbox_h_px = y1 - y0

    # Real-world metric: object_size = (bbox_px / focal_px) * depth_m
    w_m = max(0.05, (bbox_w_px / focal_px) * depth_m)
    h_m = max(0.05, (bbox_h_px / focal_px) * depth_m)

    del model, processor
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    return h_m, w_m, depth_m, {
        "depth_m_at_object": round(depth_m, 3),
        "hfov_assumed_deg": 60.0,
        "focal_px_assumed": round(focal_px, 1),
        "bbox_w_px": round(bbox_w_px, 1),
        "bbox_h_px": round(bbox_h_px, 1),
    }


# ---------------------------------------------------------------------------
# Stage 3 — Colour from photo crop (k-means dominant)
# ---------------------------------------------------------------------------
def _dominant_colour_from_crop(image_full_rgba_path_or_image, box_xyxy):
    """Pick the dominant non-background colour from the bbox crop.

    Respects PNG alpha when present (transparent pixels are dropped), and also
    filters near-white studio background and near-black composited background
    so that the dominant chair/wood/upholstery colour rises to the top of the
    k-means clusters."""
    # Accept either a PIL image or an open path
    if isinstance(image_full_rgba_path_or_image, str):
        img = Image.open(image_full_rgba_path_or_image)
    else:
        img = image_full_rgba_path_or_image
    if img.mode != "RGBA":
        img = img.convert("RGBA")

    x0, y0, x1, y1 = [int(v) for v in box_xyxy]
    crop = img.crop((x0, y0, x1, y1))
    arr = np.array(crop)
    if arr.shape[-1] == 4:
        rgb = arr[:, :, :3].astype(np.float32)
        alpha = arr[:, :, 3]
        keep = alpha > 200
    else:
        rgb = arr.astype(np.float32)
        keep = np.ones(rgb.shape[:2], dtype=bool)

    pixels = rgb[keep].reshape(-1, 3)
    if len(pixels) < 100:
        pixels = rgb.reshape(-1, 3)

    # Filter near-white (studio bg) and near-black (transparent composite)
    not_white = ~np.all(pixels > 235, axis=1)
    not_black = ~np.all(pixels < 20, axis=1)
    keep_px = not_white & not_black
    if keep_px.sum() > 100:
        pixels = pixels[keep_px]

    try:
        from scipy.cluster.vq import kmeans, vq
        n_clusters = min(4, max(1, len(pixels) // 1000))
        centroids, _ = kmeans(pixels, n_clusters)
        labels, _ = vq(pixels, centroids)
        counts = np.bincount(labels)
        # Skip clusters that are too saturated white / black
        order = counts.argsort()[::-1]
        chosen = centroids[order[0]]
        for idx in order:
            c = centroids[idx]
            if not (np.all(c > 235) or np.all(c < 25)):
                chosen = c
                break
        dom = chosen
    except Exception:
        dom = pixels.mean(axis=0)
    return tuple(float(c / 255.0) for c in dom)


# ---------------------------------------------------------------------------
# Stage 4 — Mesh build (primitive library)
# ---------------------------------------------------------------------------
def _build_primitive_mesh(category, h, w, d, colour_rgb):
    builder = CATEGORY_MESH_BUILDERS.get(category, _box_mesh)
    mesh = builder(h, w, d)
    mesh.apply_translation(-mesh.bounding_box.centroid)
    try:
        mesh.visual = trimesh.visual.TextureVisuals(
            material=trimesh.visual.material.PBRMaterial(
                baseColorFactor=np.array([colour_rgb[0], colour_rgb[1], colour_rgb[2], 1.0]),
                roughnessFactor=0.65,
                metallicFactor=0.0,
            )
        )
    except Exception:
        pass
    return mesh


# ---------------------------------------------------------------------------
# Stage 5 — Optional retrieval against local mesh library
# ---------------------------------------------------------------------------
def _try_retrieval(image_crop: Image.Image, category: str):
    """If a DINOv2 + FAISS library exists, return the path to the matching mesh.

    Returns (glb_path, metadata) or (None, None) if no library / no match.
    """
    if not MESH_INDEX_PATH.exists() or not MESH_MANIFEST_PATH.exists():
        return None, None

    try:
        import faiss
        from transformers import AutoImageProcessor, AutoModel

        manifest = json.loads(MESH_MANIFEST_PATH.read_text(encoding="utf-8"))
        cat_indices = [i for i, m in enumerate(manifest) if m.get("category") == category]

        device = "cuda" if torch.cuda.is_available() else "cpu"
        mid = "facebook/dinov2-base"
        processor = AutoImageProcessor.from_pretrained(mid)
        model = AutoModel.from_pretrained(mid).to(device).eval()
        inputs = processor(images=image_crop, return_tensors="pt").to(device)
        with torch.no_grad():
            outputs = model(**inputs)
        query = outputs.last_hidden_state[:, 0, :].cpu().numpy().astype(np.float32)
        query /= max(np.linalg.norm(query), 1e-6)
        del model, processor
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        index = faiss.read_index(str(MESH_INDEX_PATH))
        # Search the whole library, then filter to category if any candidates exist
        k = min(len(manifest), 8)
        D, I = index.search(query, k=k)
        best_idx, best_score = None, None
        for rank in range(k):
            cand_idx = int(I[0, rank]); sc = float(D[0, rank])
            if cat_indices and cand_idx not in cat_indices:
                continue
            best_idx, best_score = cand_idx, sc
            break
        # Fall back to overall best if no in-category hit
        if best_idx is None:
            best_idx = int(I[0, 0]); best_score = float(D[0, 0])

        entry = manifest[best_idx]
        glb_path = (MESH_LIBRARY_DIR / entry["glb"]).resolve()
        if not glb_path.exists():
            return None, None
        return str(glb_path), {
            "library_entry": entry.get("id"),
            "library_category": entry.get("category"),
            "similarity": round(best_score, 4),
        }
    except Exception as e:
        return None, {"retrieval_error": str(e)}


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
def run(image_path: str, output_glb: str):
    t0 = time.perf_counter()

    if not os.path.exists(image_path):
        raise SystemExit(json.dumps({
            "success": False,
            "error": {"message": f"image not found: {image_path}"},
        }))

    image_rgba_orig = Image.open(image_path)
    image = image_rgba_orig.convert("RGB")  # detection / depth need RGB
    rgba = image_rgba_orig.convert("RGBA")   # colour extraction respects alpha

    # ---- Stage 1: detection ----
    detection = _detect_top_object(image)
    coco_label = detection["label"] if detection["ok"] else None
    scs_category, ifc_class, fallback_hwd = COCO_TO_IFC.get(coco_label or "", DEFAULT_MAPPING)
    box_xyxy = detection["box"] if detection["ok"] else [0, 0, image.size[0], image.size[1]]

    # ---- Stage 2: metric dimensions from photo via Depth Anything V2 Metric ----
    depth_meta = {}
    try:
        h_m, w_m, depth_m, depth_meta = _estimate_metric_dimensions(image, box_xyxy, image.size)
        # Aspect-ratio depth assumption: for typical furniture, depth ≈ height/2 floor
        # but for monitors / books / paintings, depth is much smaller.
        if scs_category in ("monitor", "book", "clock", "keyboard"):
            d_m = max(0.03, w_m * 0.1)
        elif scs_category in ("table", "bench"):
            d_m = max(0.30, w_m * 0.5)
        elif scs_category in ("laptop", "mouse"):
            d_m = max(0.05, w_m * 0.7)
        else:
            d_m = max(0.20, min(w_m * 0.95, h_m * 0.95))
        dim_source = "depth_anything_v2_metric"
    except Exception as e:
        h_m, w_m, d_m = fallback_hwd
        dim_source = f"fallback ({e})"

    # ---- Stage 3: dominant colour from photo crop (alpha-aware) ----
    try:
        colour_rgb = _dominant_colour_from_crop(rgba, box_xyxy)
    except Exception:
        colour_rgb = (0.70, 0.70, 0.72)

    # ---- Stage 4 or 5: retrieval or primitive ----
    bx0, by0, bx1, by1 = [int(v) for v in box_xyxy]
    crop = image.crop((bx0, by0, bx1, by1))
    retrieved_glb, retrieval_meta = _try_retrieval(crop, scs_category)

    if retrieved_glb:
        # Use the retrieved library mesh, scaled to the measured dimensions
        mesh = trimesh.load(retrieved_glb, force="mesh")
        if isinstance(mesh, trimesh.Scene):
            mesh = trimesh.util.concatenate([g for g in mesh.geometry.values()
                                              if isinstance(g, trimesh.Trimesh)])
        ext = mesh.bounding_box.extents
        if ext.max() > 0:
            target = max(h_m, w_m, d_m)
            mesh.apply_scale(target / ext.max())
        mesh.apply_translation(-mesh.bounding_box.centroid)
        try:
            mesh.visual = trimesh.visual.TextureVisuals(
                material=trimesh.visual.material.PBRMaterial(
                    baseColorFactor=np.array([colour_rgb[0], colour_rgb[1], colour_rgb[2], 1.0]),
                    roughnessFactor=0.65,
                    metallicFactor=0.0,
                )
            )
        except Exception:
            pass
        mesh_source = "retrieval"
    else:
        mesh = _build_primitive_mesh(scs_category, h_m, w_m, d_m, colour_rgb)
        mesh_source = "primitive-library"

    os.makedirs(os.path.dirname(output_glb) or ".", exist_ok=True)
    mesh.export(output_glb)
    glb_size = os.path.getsize(output_glb)

    # Save the texture crop alongside (useful for future texture-projection work)
    try:
        crop_path = Path(output_glb).with_suffix(".texture.png")
        crop.save(str(crop_path))
    except Exception:
        pass

    elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)

    return {
        "success": True,
        "image_path": image_path,
        "output_path": output_glb,
        "glb_size_bytes": glb_size,
        "detection": {
            "coco_label": coco_label,
            "confidence": round(detection["score"], 3) if detection["ok"] else 0.0,
            "box_xyxy": box_xyxy,
            "image_size": list(image.size),
        },
        "category": scs_category,
        "ifc_class": ifc_class,
        "dimensions_m": {
            "height": round(h_m, 3), "width": round(w_m, 3), "depth": round(d_m, 3),
        },
        "dimension_source": dim_source,
        "depth": depth_meta,
        "colour_rgb": [round(c, 3) for c in colour_rgb],
        "mesh_source": mesh_source,
        "retrieval": retrieval_meta,
        "faces": len(mesh.faces),
        "method": "detr-r50 + depth-anything-v2-metric + dominant-colour + (retrieval-or-primitive)",
        "latency_ms": elapsed_ms,
        "device": "cuda" if torch.cuda.is_available() else "cpu",
    }


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(json.dumps({"success": False, "error": {"message": "Usage: run_detect_and_place.py <input_image> <output_glb>"}}))
        sys.exit(1)
    try:
        result = run(sys.argv[1], sys.argv[2])
        print(json.dumps(result))
    except Exception as e:
        import traceback
        print(json.dumps({
            "success": False,
            "error": {"message": str(e), "traceback": traceback.format_exc()},
        }))
        sys.exit(1)
