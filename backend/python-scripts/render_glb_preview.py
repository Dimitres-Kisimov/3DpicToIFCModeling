"""
render_glb_preview.py — render a GLB to a PNG server-side (no WebGL / no GPU).

Used so the web app can show a generated mesh even when the browser's WebGL is
unavailable (degraded context / hardware-accel off / context-limit). Matplotlib
software rendering, decimated for speed.

Usage:  python render_glb_preview.py <input.glb> <output.png> [--az -60] [--el 22]
Prints JSON: {"success": true, "png": "...", "faces": N}
"""
from __future__ import annotations
import sys, json
from pathlib import Path

import numpy as np
import trimesh
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

PREVIEW_FACES = 9000   # decimation target (quadric) — solid + fast


def _basecolor(mesh):
    try:
        mat = getattr(mesh.visual, "material", None)
        bcf = getattr(mat, "baseColorFactor", None)
        if bcf is not None:
            c = np.asarray(bcf, dtype=float)[:3]
            return tuple(np.clip(c, 0, 1))
    except Exception:
        pass
    return (0.45, 0.5, 0.62)


def _decimate(mesh):
    """Quadric-decimate to a low-poly SOLID for fast software rendering
    (fast_simplification backend). Falls back to the raw mesh on error."""
    if len(mesh.faces) <= PREVIEW_FACES:
        return mesh
    try:
        d = mesh.simplify_quadric_decimation(face_count=PREVIEW_FACES)
        if d is not None and len(d.faces) > 0:
            return d
    except Exception:
        pass
    return mesh


def render(glb_path: str, png_path: str, az: float = -60.0, el: float = 22.0) -> dict:
    mesh = trimesh.load(glb_path, force="mesh")
    full_faces = len(mesh.faces)
    rgb = np.asarray(_basecolor(mesh))
    mesh = _decimate(mesh)

    # mirror render_scene.meshrender (the proven path): per-face shading +
    # Y-up axis swap so glTF (Y-up) meshes render upright.
    tris = mesh.triangles[:, :, [0, 2, 1]]                  # (n,3,3), plot (x,z,y)
    light = np.array([0.4, 0.85, 0.5]); light /= np.linalg.norm(light)
    shade = np.clip(mesh.face_normals @ light, 0, 1) * 0.6 + 0.4
    colors = np.clip(rgb[None, :] * shade[:, None], 0, 1)

    fig = plt.figure(figsize=(6, 6), facecolor="white")
    ax = fig.add_subplot(111, projection="3d")
    ax.add_collection3d(Poly3DCollection(tris, facecolors=colors, edgecolor="none"))

    v = tris.reshape(-1, 3)
    ax.set_xlim(v[:, 0].min(), v[:, 0].max())
    ax.set_ylim(v[:, 1].min(), v[:, 1].max())
    ax.set_zlim(v[:, 2].min(), v[:, 2].max())
    ax.set_box_aspect(np.ptp(v, axis=0) + 1e-6)
    ax.view_init(elev=el, azim=az)
    ax.set_axis_off()
    fig.savefig(png_path, dpi=120, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return {"success": True, "png": png_path, "faces": full_faces,
            "preview_faces": len(mesh.faces)}


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(json.dumps({"success": False, "error": "usage: render_glb_preview.py <in.glb> <out.png>"}))
        sys.exit(1)
    az, el = -60.0, 22.0
    a = sys.argv[3:]
    for i, t in enumerate(a):
        if t == "--az" and i + 1 < len(a): az = float(a[i + 1])
        if t == "--el" and i + 1 < len(a): el = float(a[i + 1])
    try:
        print(json.dumps(render(sys.argv[1], sys.argv[2], az, el)))
    except Exception as e:
        import traceback; traceback.print_exc()
        print(json.dumps({"success": False, "error": str(e)}))
        sys.exit(1)
