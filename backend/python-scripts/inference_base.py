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


def generate_depth_mesh(image_path, resolution=64, model_name="Intel/dpt-hybrid-midas"):
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


def generate_segmented_depth_mesh(image_path, resolution=64, depth_model="Intel/dpt-hybrid-midas"):
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
