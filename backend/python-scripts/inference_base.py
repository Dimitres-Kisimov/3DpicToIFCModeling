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


# Typical real-world height (m) per object category. Monocular images carry no
# absolute scale, so we anchor on the classified object's typical height and derive
# width from its pixel aspect ratio. Keys are normalised (lowercase, no underscores).
_HEIGHT_PRIORS = {
    "chair": 1.0, "office chair": 1.05, "armchair": 0.95, "stool": 0.45,
    "desk": 0.74, "table": 0.74, "coffee table": 0.45, "side table": 0.55,
    "sofa": 0.85, "couch": 0.85, "bed": 0.6,
    "cabinet": 1.2, "filing cabinet": 1.32, "wardrobe": 2.0,
    "bookshelf": 1.5, "shelf": 1.5,
    "lamp": 1.5, "light": 1.5, "monitor": 0.45, "laptop": 0.25,
    "computer": 0.45, "refrigerator": 1.7, "door": 2.0, "window": 1.2,
    "toilet": 0.4, "planter": 0.6, "mirror": 1.2, "clock": 0.3,
    "picture frame": 0.5, "default": 1.0,
}


def _height_prior(category):
    if not category:
        return _HEIGHT_PRIORS["default"]
    key = str(category).lower().replace("_", " ").strip()
    return _HEIGHT_PRIORS.get(key, _HEIGHT_PRIORS["default"])


def estimate_metric_scale(image_path, mask_rgba=None, category=None):
    """
    Use Depth Anything V2 (Apache 2.0) to estimate object dimensions in metres.
    `category` (e.g. the CLIP label) selects a real-world height prior; width is
    derived from the object's pixel aspect ratio and depth from the relative
    depth extent. Returns {height_m, width_m, depth_m}.
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

        # Use SAM2 mask if provided to focus on the object. The mask may be at a
        # different resolution than the depth map (run_triposr passes the mask
        # AFTER resize_foreground), so resize from the mask's OWN shape to the
        # depth shape — NOT from the original image size (that was the 256-vs-300
        # boolean-index mismatch bug).
        if mask_rgba is not None:
            from scipy.ndimage import zoom as scipy_zoom
            mask_arr = np.array(mask_rgba)[:, :, 3] > 64
            m_h0, m_w0 = mask_arr.shape
            mh, mw = depth.shape
            mask_resized = scipy_zoom(mask_arr.astype(np.float32),
                                      (mh / m_h0, mw / m_w0), order=1) > 0.5
            if not mask_resized.any():
                raise ValueError("Empty mask after resize")
            object_depth = depth[mask_resized]
            rows = np.any(mask_resized, axis=1)
            cols = np.any(mask_resized, axis=0)
            rmin, rmax = np.where(rows)[0][[0, -1]]
            cmin, cmax = np.where(cols)[0][[0, -1]]
            pixel_h = max(int(rmax - rmin), 1)
            pixel_w = max(int(cmax - cmin), 1)
        else:
            object_depth = depth.ravel()
            pixel_h, pixel_w = depth.shape

        if object_depth.size == 0:
            raise ValueError("Empty depth region")

        depth_range = float(object_depth.max() - object_depth.min())

        # Anchor on the category's typical height; derive width from the object's
        # pixel aspect ratio, and depth from the relative depth extent.
        prior_height_m = _height_prior(category)
        aspect = pixel_w / pixel_h                       # width : height in pixels
        est_h = float(np.clip(prior_height_m, 0.1, 3.0))
        est_w = float(np.clip(prior_height_m * aspect, 0.1, 3.0))
        rel_depth = float(np.clip(depth_range / (depth.max() + 1e-8), 0.1, 1.0))
        est_d = float(np.clip(rel_depth * est_w, 0.1, 3.0))

        log(f"Estimated dims (prior '{category or 'default'}'={prior_height_m}m, "
            f"aspect {aspect:.2f}) — H:{est_h:.2f}m W:{est_w:.2f}m D:{est_d:.2f}m", "info")
        return {"height_m": round(est_h, 2), "width_m": round(est_w, 2),
                "depth_m": round(est_d, 2)}

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

    # ── 1. Foreground segmentation (rembg — MIT-licenced, U²-Net) ───────────
    # Replaces the previous AGPL-3.0 YOLOv8 path. rembg ships its own MIT-
    # licensed U²-Net weights and runs on CPU or GPU.  For commercial-grade
    # mask boundaries SAM 2.1 (Apache-2.0) is a drop-in upgrade — see
    # run_detect_and_place.py for the SAM-segmented pipeline used by the
    # production detect-and-place route.
    mask_full = None
    try:
        log("Running rembg (U²-Net) foreground segmentation...", "info")
        import rembg
        with open(image_path, "rb") as f:
            rgba_bytes = rembg.remove(f.read())
        from io import BytesIO
        rgba = np.array(Image.open(BytesIO(rgba_bytes)).convert("RGBA"))
        if rgba.shape[-1] == 4:
            mask_full = (rgba[:, :, 3].astype(np.float32) / 255.0)
            from scipy.ndimage import binary_erosion
            binary = (mask_full > 0.5)
            binary = binary_erosion(binary, iterations=4)
            mask_full = binary.astype(np.float32)
            coverage = mask_full.sum() / mask_full.size * 100
            log(f"Foreground segmented — coverage {coverage:.1f}%", "info")
        else:
            log("rembg returned no alpha channel, using full image", "warn")
    except Exception as e:
        log(f"rembg failed ({e}), using full image", "warn")

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
