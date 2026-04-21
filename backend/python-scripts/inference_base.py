"""
Inference base module - shared utilities for AI models
"""

import json
import sys
import traceback
from pathlib import Path


def log(message, level="info"):
    """Log message to stderr for Node.js to capture"""
    print(f"[{level.upper()}] {message}", file=sys.stderr)


def error_exit(message, code=1):
    """Print error as JSON and exit"""
    error_obj = {
        "success": False,
        "error": {"message": message},
    }
    print(json.dumps(error_obj))
    sys.exit(code)


def success_exit(data):
    """Print success result as JSON and exit"""
    result = {
        "success": True,
        "data": data,
    }
    print(json.dumps(result))
    sys.exit(0)


def load_image(image_path):
    """Load image from file path"""
    try:
        from PIL import Image
        img = Image.open(image_path)
        return img
    except ImportError:
        error_exit("Pillow library required for image loading")
    except Exception as e:
        error_exit(f"Failed to load image: {str(e)}")


def generate_depth_mesh(image_path, resolution=64, model_name="Intel/dpt-hybrid-midas"):
    """
    Generate a colored 3D mesh from a single image using depth estimation.
    Uses DPT to estimate per-pixel depth, then builds a textured height-map mesh.
    Returns raw GLB bytes.
    """
    from PIL import Image
    from scipy.ndimage import zoom as scipy_zoom
    import numpy as np
    import trimesh
    import tempfile
    import os

    log(f"Loading depth model: {model_name}", "info")
    from transformers import pipeline as hf_pipeline

    img = Image.open(image_path).convert("RGB")
    log(f"Image size: {img.size}", "info")

    # Run depth estimation - model auto-downloads to HuggingFace cache on first use
    depth_pipe = hf_pipeline("depth-estimation", model=model_name)
    log("Running depth inference...", "info")
    result = depth_pipe(img)

    # Extract depth tensor (shape may be [1,H,W] or [H,W])
    if "predicted_depth" in result:
        depth = result["predicted_depth"]
        if hasattr(depth, "numpy"):
            depth = depth.squeeze().numpy()
        else:
            depth = np.array(depth).squeeze()
    else:
        depth = np.array(result["depth"], dtype=np.float32)

    depth = depth.astype(np.float32)
    log(f"Raw depth shape: {depth.shape}", "info")

    # Resize to target resolution
    sh = resolution / depth.shape[0]
    sw = resolution / depth.shape[1]
    depth = scipy_zoom(depth, (sh, sw), order=1)

    # Normalize depth to [0, 1]
    d_min, d_max = depth.min(), depth.max()
    depth = (depth - d_min) / (d_max - d_min + 1e-8)

    # Vertex colors from the original image
    img_small = img.resize((resolution, resolution), Image.BILINEAR)
    img_arr = np.array(img_small, dtype=np.uint8)

    H, W = depth.shape
    x = np.linspace(-1.0, 1.0, W)
    y = np.linspace(-1.0, 1.0, H)
    xx, yy = np.meshgrid(x, y)
    zz = depth * 0.7  # scale depth into Z axis

    # Build vertex array: x=image-x, y=image-y (flipped up), z=depth
    vertices = np.column_stack([
        xx.ravel().astype(np.float64),
        (-yy.ravel()).astype(np.float64),
        zz.ravel().astype(np.float64),
    ])

    # Build quad-mesh faces
    faces = []
    for i in range(H - 1):
        for j in range(W - 1):
            tl = i * W + j
            tr = tl + 1
            bl = tl + W
            br = bl + 1
            faces.append([tl, tr, bl])
            faces.append([tr, br, bl])
    faces = np.array(faces, dtype=np.int64)

    # Attach image colors as vertex colors
    vc = img_arr.reshape(-1, 3)
    alpha = np.full((len(vc), 1), 255, dtype=np.uint8)
    vertex_colors = np.hstack([vc, alpha])

    mesh = trimesh.Trimesh(
        vertices=vertices,
        faces=faces,
        vertex_colors=vertex_colors,
        process=False,
    )

    with tempfile.NamedTemporaryFile(suffix=".glb", delete=False) as f:
        tmp = f.name
    mesh.export(tmp)
    with open(tmp, "rb") as f:
        data = f.read()
    os.unlink(tmp)

    log(f"Mesh created: {len(vertices)} vertices, {len(faces)} faces, {len(data)} bytes", "info")
    return data
