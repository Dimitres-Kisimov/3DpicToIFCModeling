"""
Inference base module - shared utilities for AI models
"""

import json
import sys
from pathlib import Path


def log(message, level="info"):
    print(f"[{level.upper()}] {message}", file=sys.stderr)


def error_exit(message, code=1):
    print(json.dumps({"success": False, "error": {"message": message}}))
    sys.exit(code)


def success_exit(data):
    print(json.dumps({"success": True, "data": data}))
    sys.exit(0)


def load_image(image_path):
    try:
        from PIL import Image
        return Image.open(image_path)
    except ImportError:
        error_exit("Pillow library required for image loading")
    except Exception as e:
        error_exit(f"Failed to load image: {str(e)}")


# IFC entity mapping — CLIP label → (IFC class, category)
_IFC_LABEL_MAP = {
    "chair":        ("IfcFurnitureElement", "Chair"),
    "office chair": ("IfcFurnitureElement", "Chair"),
    "armchair":     ("IfcFurnitureElement", "Chair"),
    "sofa":         ("IfcFurnitureElement", "Sofa"),
    "couch":        ("IfcFurnitureElement", "Sofa"),
    "table":        ("IfcFurnitureElement", "Table"),
    "desk":         ("IfcFurnitureElement", "Table"),
    "bed":          ("IfcFurnitureElement", "Bed"),
    "cabinet":      ("IfcFurnitureElement", "Cabinet"),
    "wardrobe":     ("IfcFurnitureElement", "Cabinet"),
    "bookshelf":    ("IfcFurnitureElement", "Shelf"),
    "shelf":        ("IfcFurnitureElement", "Shelf"),
    "door":         ("IfcDoor",             "Door"),
    "window":       ("IfcWindow",           "Window"),
    "lamp":         ("IfcFurnitureElement", "Lighting"),
    "light":        ("IfcFurnitureElement", "Lighting"),
    "monitor":      ("IfcFurnitureElement", "Equipment"),
    "computer":     ("IfcFurnitureElement", "Equipment"),
    "refrigerator": ("IfcFurnitureElement", "Equipment"),
    "toilet":       ("IfcSanitaryTerminal", "Toilet"),
    "sink":         ("IfcSanitaryTerminal", "Sink"),
    "bathtub":      ("IfcSanitaryTerminal", "Bath"),
    "stairs":       ("IfcStair",            "Stair"),
    "wall":         ("IfcWall",             "Wall"),
    "floor":        ("IfcSlab",             "Floor"),
}

_CLIP_LABELS = list(_IFC_LABEL_MAP.keys()) + ["other object"]


def _classify_with_finetuned(image_path, checkpoint_path):
    """
    Internal helper: run inference using the fine-tuned CLIP checkpoint saved by
    scripts/train_clip_office.py.  Returns the same dict format as the zero-shot
    path, or raises an exception if anything goes wrong.

    Checkpoint format (produced by train_clip_office.py):
        {
            "model_state_dict": ...,
            "label_to_idx": {"office_chair": 0, "table": 1, ...},
            "mode": "linear_probe" | "lora",
            "val_accuracy": float,
            "num_classes": int,
        }
    """
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    from torchvision import transforms
    from PIL import Image
    from transformers import CLIPModel

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    ckpt = torch.load(checkpoint_path, map_location=device, weights_only=False)
    label_to_idx: dict = ckpt["label_to_idx"]
    idx_to_label: dict = {v: k for k, v in label_to_idx.items()}
    num_classes: int = ckpt["num_classes"]
    mode: str = ckpt.get("mode", "linear_probe")

    # Reconstruct model skeleton (same architecture as train_clip_office.py)
    clip_base = CLIPModel.from_pretrained("openai/clip-vit-base-patch32")

    class _ProbeModel(nn.Module):
        def __init__(self):
            super().__init__()
            self.vision_encoder = clip_base.vision_model
            self.visual_projection = clip_base.visual_projection
            self.head = nn.Linear(512, num_classes)

        def forward(self, pixel_values):
            out = self.vision_encoder(pixel_values=pixel_values)
            feats = self.visual_projection(out.pooler_output)
            feats = feats / feats.norm(dim=-1, keepdim=True)
            return self.head(feats)

    model = _ProbeModel()
    model.load_state_dict(ckpt["model_state_dict"], strict=False)
    model.eval()
    model = model.to(device)

    # Preprocessing (CLIP normalisation)
    preprocess = transforms.Compose([
        transforms.Resize(224),
        transforms.CenterCrop(224),
        transforms.ToTensor(),
        transforms.Normalize(
            mean=[0.48145466, 0.4578275,  0.40821073],
            std =[0.26862954, 0.26130258, 0.27577711],
        ),
    ])

    img = Image.open(image_path).convert("RGB")
    tensor = preprocess(img).unsqueeze(0).to(device)

    with torch.no_grad():
        logits = model(tensor)
        probs  = F.softmax(logits, dim=-1).squeeze(0).cpu().tolist()

    best_idx = max(range(num_classes), key=lambda i: probs[i])
    label    = idx_to_label[best_idx]
    score    = probs[best_idx]

    # Map fine-tuned label slug back to IFC — try direct and cleaned variants
    ifc_class, category = _IFC_LABEL_MAP.get(
        label,
        _IFC_LABEL_MAP.get(label.replace("_", " "), ("IfcFurnitureElement", "Furniture")),
    )
    return {
        "label": label,
        "score": score,
        "ifc_class": ifc_class,
        "category": category,
    }


def classify_object_clip(image_path):
    """
    Use CLIP (openai/clip-vit-base-patch32, MIT license) to identify the
    object type and return the matching IFC entity class and category.
    Falls back to IfcFurnitureElement if classification fails.

    Automatically uses the fine-tuned model if the checkpoint produced by
    scripts/train_clip_office.py is present at:
        models/clip_office/best_model.pt
    Otherwise falls back to zero-shot CLIP.
    """
    # ── Fine-tuned path ──────────────────────────────────────────────────────
    _CHECKPOINT = Path(__file__).resolve().parents[2] / "models" / "clip_office" / "best_model.pt"
    if _CHECKPOINT.exists():
        log(f"Using fine-tuned CLIP checkpoint: {_CHECKPOINT}", "info")
        try:
            result = _classify_with_finetuned(image_path, _CHECKPOINT)
            log(f"Fine-tuned CLIP: '{result['label']}' ({result['score']:.2%})", "info")
            return result
        except Exception as e:
            log(f"Fine-tuned CLIP failed ({e}), falling back to zero-shot", "warn")
    else:
        log("No fine-tuned checkpoint found — using zero-shot CLIP", "info")

    # ── Zero-shot fallback ───────────────────────────────────────────────────
    try:
        from transformers import pipeline
        from PIL import Image

        log("Running zero-shot CLIP object classification...", "info")
        classifier = pipeline(
            "zero-shot-image-classification",
            model="openai/clip-vit-base-patch32",
        )
        img = Image.open(image_path).convert("RGB")
        results = classifier(img, candidate_labels=_CLIP_LABELS)

        top = results[0]
        label = top["label"]
        score = top["score"]
        log(f"Zero-shot CLIP: '{label}' ({score:.2%})", "info")

        ifc_class, category = _IFC_LABEL_MAP.get(label, ("IfcFurnitureElement", "Furniture"))
        return {
            "label": label,
            "score": score,
            "ifc_class": ifc_class,
            "category": category,
        }
    except Exception as e:
        log(f"CLIP classification failed ({e}), defaulting to IfcFurnitureElement", "warn")
        return {
            "label": "unknown",
            "score": 0.0,
            "ifc_class": "IfcFurnitureElement",
            "category": "Furniture",
        }


def estimate_metric_scale(image_path, mask_rgba=None):
    """
    Use Depth Anything V2 (Apache 2.0) to estimate relative object dimensions.
    Returns estimated height/width/depth in metres using a known-object prior.
    The metric model gives relative depth in a 0-1 normalised space; we use
    average furniture priors to convert to approximate real-world metres.
    """
    try:
        import numpy as np
        from PIL import Image
        from transformers import pipeline

        log("Estimating metric scale with Depth Anything V2...", "info")
        depth_pipe = pipeline(
            "depth-estimation",
            model="depth-anything/Depth-Anything-V2-Small-hf",
        )
        img = Image.open(image_path).convert("RGB")
        W_img, H_img = img.size
        result = depth_pipe(img)

        if "predicted_depth" in result:
            depth = result["predicted_depth"]
            depth = depth.squeeze().numpy() if hasattr(depth, "numpy") else np.array(depth).squeeze()
        else:
            depth = np.array(result["depth"], dtype=np.float32)

        depth = depth.astype(np.float32)

        # Use SAM2 mask if provided to focus on the object
        if mask_rgba is not None:
            mask_arr = np.array(mask_rgba)[:, :, 3] > 64
            from scipy.ndimage import zoom as scipy_zoom
            mh, mw = depth.shape
            mask_resized = scipy_zoom(mask_arr.astype(np.float32),
                                      (mh / H_img, mw / W_img), order=1) > 0.5
            object_depth = depth[mask_resized]
            # Bounding box of the mask to estimate pixel height/width
            rows = np.any(mask_resized, axis=1)
            cols = np.any(mask_resized, axis=0)
            rmin, rmax = np.where(rows)[0][[0, -1]]
            cmin, cmax = np.where(cols)[0][[0, -1]]
            pixel_h = rmax - rmin
            pixel_w = cmax - cmin
        else:
            object_depth = depth.ravel()
            pixel_h = H_img
            pixel_w = W_img

        if len(object_depth) == 0:
            raise ValueError("Empty depth region")

        depth_range = float(object_depth.max() - object_depth.min())

        # Normalise pixel dimensions to image fraction, then scale by a
        # furniture-average height prior of 1.0 m so IFC gets plausible values.
        fraction_h = pixel_h / H_img
        fraction_w = pixel_w / W_img
        prior_height_m = 1.0  # conservative furniture average

        est_h = round(prior_height_m * fraction_h * (H_img / max(pixel_h, 1)), 2)
        est_w = round(prior_height_m * fraction_w * (W_img / max(pixel_w, 1)), 2)
        est_d = round(float(np.clip(depth_range / (depth.max() + 1e-8), 0.1, 1.0)), 2)

        # Clamp to sensible furniture range: 0.1 m – 3.0 m
        est_h = float(np.clip(est_h, 0.1, 3.0))
        est_w = float(np.clip(est_w, 0.1, 3.0))
        est_d = float(np.clip(est_d * est_w, 0.1, 3.0))

        log(f"Estimated dimensions — H:{est_h}m  W:{est_w}m  D:{est_d}m", "info")
        return {"height_m": est_h, "width_m": est_w, "depth_m": est_d}

    except Exception as e:
        log(f"Scale estimation failed ({e}), using defaults", "warn")
        return {"height_m": 1.0, "width_m": 0.8, "depth_m": 0.8}


def generate_depth_mesh(image_path, resolution=64, model_name="depth-anything/Depth-Anything-V2-Small-hf"):
    """Full-image depth mesh — fallback when segmentation finds nothing."""
    from PIL import Image
    from scipy.ndimage import zoom as scipy_zoom
    import numpy as np
    import trimesh
    import tempfile
    import os

    img = Image.open(image_path).convert("RGB")
    from transformers import pipeline as hf_pipeline
    depth_pipe = hf_pipeline("depth-estimation", model=model_name)
    result = depth_pipe(img)

    if "predicted_depth" in result:
        depth = result["predicted_depth"]
        depth = depth.squeeze().numpy() if hasattr(depth, "numpy") else np.array(depth).squeeze()
    else:
        depth = np.array(result["depth"], dtype=np.float32)
    depth = depth.astype(np.float32)

    sh, sw = resolution / depth.shape[0], resolution / depth.shape[1]
    depth = scipy_zoom(depth, (sh, sw), order=1)
    depth = (depth - depth.min()) / (depth.max() - depth.min() + 1e-8)

    img_small = img.resize((resolution, resolution), Image.BILINEAR)
    img_arr = np.array(img_small, dtype=np.uint8)

    H, W = depth.shape
    x, y = np.linspace(-1, 1, W), np.linspace(-1, 1, H)
    xx, yy = np.meshgrid(x, y)
    zz = depth * 0.7

    vertices = np.column_stack([xx.ravel(), (-yy).ravel(), zz.ravel()]).astype(np.float64)
    i_idx, j_idx = np.meshgrid(np.arange(H - 1), np.arange(W - 1), indexing="ij")
    i_idx, j_idx = i_idx.ravel(), j_idx.ravel()
    tl, tr = i_idx * W + j_idx, i_idx * W + j_idx + 1
    bl, br = (i_idx + 1) * W + j_idx, (i_idx + 1) * W + j_idx + 1
    faces = np.vstack([np.c_[tl, tr, bl], np.c_[tr, br, bl]]).astype(np.int64)

    vc = img_arr.reshape(-1, 3)
    alpha = np.full((len(vc), 1), 255, dtype=np.uint8)
    mesh = trimesh.Trimesh(vertices=vertices, faces=faces,
                           vertex_colors=np.hstack([vc, alpha]), process=False)

    with tempfile.NamedTemporaryFile(suffix=".glb", delete=False) as f:
        tmp = f.name
    mesh.export(tmp)
    with open(tmp, "rb") as f:
        data = f.read()
    os.unlink(tmp)
    log(f"Full-image mesh: {len(vertices)} verts, {len(faces)} faces, {len(data)} bytes", "info")
    return data


def generate_segmented_depth_mesh(image_path, resolution=64, depth_model="depth-anything/Depth-Anything-V2-Small-hf"):
    """
    SAM-3D-style pipeline:
      1. YOLO-seg isolates the main object (no background)
      2. DPT estimates per-pixel depth inside the mask
      3. Build a colored 3D mesh only for masked pixels
    """
    from PIL import Image
    from scipy.ndimage import zoom as scipy_zoom
    import numpy as np
    import trimesh
    import tempfile
    import os

    img = Image.open(image_path).convert("RGB")
    W_img, H_img = img.size
    img_arr = np.array(img, dtype=np.uint8)

    # ── 1. YOLO segmentation ────────────────────────────────────────────────
    mask_full = None
    try:
        log("Running YOLO segmentation...", "info")
        from ultralytics import YOLO
        yolo = YOLO("yolov8n-seg.pt")
        results = yolo(image_path, verbose=False)

        if results[0].masks is not None and len(results[0].masks.data) > 0:
            masks = results[0].masks.data.cpu().numpy()   # (N, H', W')
            confs = results[0].boxes.conf.cpu().numpy()

            # Pick the largest mask (main object fills most of the frame)
            areas = [m.sum() for m in masks]
            best = int(np.argmax(areas))
            raw = masks[best]                              # (H', W') float32 0-1

            # Resize mask back to original image size
            mask_pil = Image.fromarray((raw * 255).astype(np.uint8), mode="L")
            mask_pil = mask_pil.resize((W_img, H_img), Image.BILINEAR)
            mask_full = np.array(mask_pil, dtype=np.float32) / 255.0

            # Erode mask slightly to remove jagged boundary artifacts
            from scipy.ndimage import binary_erosion
            binary = (mask_full > 0.5)
            binary = binary_erosion(binary, iterations=4)
            mask_full = binary.astype(np.float32)

            log(f"Object segmented — largest area, confidence: {confs[best]:.2f}, "
                f"class: {results[0].names[int(results[0].boxes.cls[best])]}", "info")
        else:
            log("No objects detected, using full image", "info")
    except Exception as e:
        log(f"YOLO failed ({e}), using full image", "warn")

    # ── 2. Depth estimation ─────────────────────────────────────────────────
    log(f"Depth estimation: {depth_model}", "info")
    from transformers import pipeline as hf_pipeline
    depth_pipe = hf_pipeline("depth-estimation", model=depth_model)
    result = depth_pipe(img)

    if "predicted_depth" in result:
        depth = result["predicted_depth"]
        depth = depth.squeeze().numpy() if hasattr(depth, "numpy") else np.array(depth).squeeze()
    else:
        depth = np.array(result["depth"], dtype=np.float32)
    depth = depth.astype(np.float32)
    log(f"Depth map: {depth.shape}", "info")

    # ── 3. Apply segmentation mask to depth ─────────────────────────────────
    if mask_full is not None:
        mh, mw = depth.shape
        mask_for_depth = scipy_zoom(mask_full, (mh / H_img, mw / W_img), order=1)
        depth = depth * (mask_for_depth > 0.4).astype(np.float32)

    # ── 4. Downsample to target resolution ──────────────────────────────────
    depth_s = scipy_zoom(depth, (resolution / depth.shape[0], resolution / depth.shape[1]), order=1)

    if mask_full is not None:
        mask_s = scipy_zoom(mask_full,
                            (resolution / H_img, resolution / W_img), order=1)
        mask_s = (mask_s > 0.4).astype(np.float32)
    else:
        mask_s = np.ones((resolution, resolution), dtype=np.float32)

    # Normalize depth over the masked region only
    valid = depth_s[mask_s > 0.5]
    if len(valid) > 0:
        d_min, d_max = valid.min(), valid.max()
        depth_s = np.where(mask_s > 0.5,
                           (depth_s - d_min) / (d_max - d_min + 1e-8),
                           0.0)

    # ── 5. Vertex colors ────────────────────────────────────────────────────
    img_s = img.resize((resolution, resolution), Image.BILINEAR)
    img_arr_s = np.array(img_s, dtype=np.uint8)

    H, W = depth_s.shape
    x, y = np.linspace(-1.0, 1.0, W), np.linspace(-1.0, 1.0, H)
    xx, yy = np.meshgrid(x, y)
    zz = depth_s * 0.7

    # ── 6. Build mesh (masked pixels only, vectorized) ───────────────────────
    flat_mask = (mask_s > 0.5).ravel()
    cumsum = np.cumsum(flat_mask) - 1
    vertex_map = np.where(flat_mask, cumsum, -1).reshape(H, W).astype(np.int64)

    vertices = np.column_stack([
        xx.ravel()[flat_mask],
        (-yy.ravel())[flat_mask],
        zz.ravel()[flat_mask],
    ]).astype(np.float64)

    vc_rgb = img_arr_s.reshape(-1, 3)[flat_mask]
    alpha = np.full((len(vc_rgb), 1), 255, dtype=np.uint8)
    vertex_colors = np.hstack([vc_rgb, alpha])

    i_idx, j_idx = np.meshgrid(np.arange(H - 1), np.arange(W - 1), indexing="ij")
    i_idx, j_idx = i_idx.ravel(), j_idx.ravel()
    tl = vertex_map[i_idx,     j_idx    ]
    tr = vertex_map[i_idx,     j_idx + 1]
    bl = vertex_map[i_idx + 1, j_idx    ]
    br = vertex_map[i_idx + 1, j_idx + 1]

    v1 = (tl >= 0) & (tr >= 0) & (bl >= 0)
    v2 = (tr >= 0) & (br >= 0) & (bl >= 0)
    faces = np.vstack([np.c_[tl[v1], tr[v1], bl[v1]],
                       np.c_[tr[v2], br[v2], bl[v2]]]).astype(np.int64)

    if len(faces) == 0:
        log("Segmented mesh empty — falling back to full-image mesh", "warn")
        return generate_depth_mesh(image_path, resolution=resolution, model_name=depth_model)

    mesh = trimesh.Trimesh(vertices=vertices, faces=faces,
                           vertex_colors=vertex_colors, process=False)

    # Keep largest connected component (discard stray background fragments)
    parts = mesh.split(only_watertight=False)
    if parts:
        mesh = max(parts, key=lambda m: len(m.vertices))

    with tempfile.NamedTemporaryFile(suffix=".glb", delete=False) as f:
        tmp = f.name
    mesh.export(tmp)
    with open(tmp, "rb") as f:
        data = f.read()
    os.unlink(tmp)

    log(f"Segmented mesh: {len(mesh.vertices)} verts, {len(mesh.faces)} faces, {len(data)} bytes", "info")
    return data
