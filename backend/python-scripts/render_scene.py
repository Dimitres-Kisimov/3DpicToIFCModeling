"""
render_scene.py — report-ready figures from the object table (schedule.json).

Produces, in <out_dir>/renders/:
  floorplan.png         numbered top-down plan + legend (object names + dimensions)
  view_01..04.png       3D massing of the room from four angles

Drawn from schedule.json with matplotlib (Agg) — no GPU/GL, always renders. For
photoreal shots of the real furniture, use the "Save image" button in the web demo.

Usage: python render_scene.py <out_dir>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import numpy as np

_TXT = "#1b1b1b"


def _hex(h):
    h = (h or "#888888").lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _wd(it):
    w, d = it["width_m"], it["depth_m"]
    if it.get("rotation_deg", 0) == 90:
        w, d = d, w
    return w, d


def floorplan(room, items, path):
    W, D = room["width"], room["depth"]
    fig, ax = plt.subplots(figsize=(9.5, 9.5 * D / W))
    ax.set_facecolor("#fafaf8")
    ax.add_patch(Rectangle((0, 0), W, D, fill=False, lw=2.4, ec="#2b2b2b"))
    handles = []
    for i, it in enumerate(items, 1):
        w, d = _wd(it)
        col = _hex(it["material_hex"])
        ax.add_patch(Rectangle((it["x"] - w / 2, it["z"] - d / 2), w, d,
                               facecolor=col, ec="#1a1a1a", lw=1.2, alpha=0.92))
        ax.text(it["x"], it["z"], str(i), ha="center", va="center",
                fontsize=11, fontweight="bold", color="#fff" if sum(col) < 1.4 else "#111")
        handles.append((Rectangle((0, 0), 1, 1, fc=col, ec="#1a1a1a"),
                        f"{i}.  {it['name']}   ({it['width_m']}×{it['depth_m']}×{it['height_m']} m · {it['ifc_class']})"))
    ax.set_xticks(range(0, int(W) + 1)); ax.set_yticks(range(0, int(D) + 1))
    ax.grid(True, color="#e6e6e3", lw=0.6)
    ax.set_xlim(-0.3, W + 0.3); ax.set_ylim(-0.3, D + 0.3); ax.set_aspect("equal")
    ax.invert_yaxis()
    ax.set_title(f"Office layout plan — {W:.1f} × {D:.1f} m", fontsize=13, fontweight="bold", color=_TXT)
    ax.set_xlabel("X (m)", color=_TXT); ax.set_ylabel("Z (m)", color=_TXT)
    ax.legend([h for h, _ in handles], [l for _, l in handles], title="Objects",
              loc="upper left", bbox_to_anchor=(1.01, 1.0), fontsize=9, frameon=False)
    fig.savefig(path, dpi=150, bbox_inches="tight"); plt.close(fig)


def _box_faces(x0, x1, y0, y1, z0, z1):
    c = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
         (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    return [[c[0], c[1], c[2], c[3]], [c[4], c[5], c[6], c[7]],
            [c[0], c[1], c[5], c[4]], [c[2], c[3], c[7], c[6]],
            [c[1], c[2], c[6], c[5]], [c[0], c[3], c[7], c[4]]]


def view3d(room, items, path, azim, elev, label):
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    W, D, H = room["width"], room["depth"], room.get("height", 3.0)
    fig = plt.figure(figsize=(8.5, 6.5)); ax = fig.add_subplot(111, projection="3d")
    ax.add_collection3d(Poly3DCollection([[(0, 0, 0), (W, 0, 0), (W, D, 0), (0, D, 0)]],
                                         facecolor="#e7e4da", edgecolor="#b9b6ac", lw=0.5, alpha=0.7))
    for it in items:
        w, d, h = *_wd(it), it["height_m"]
        cx, cz = it["x"], it["z"]
        faces = _box_faces(cx - w / 2, cx + w / 2, cz - d / 2, cz + d / 2, 0, h)
        ax.add_collection3d(Poly3DCollection(faces, facecolor=_hex(it["material_hex"]),
                                             edgecolor="#1a1a1a", linewidths=0.35, alpha=0.96))
    ax.set_xlim(0, W); ax.set_ylim(0, D); ax.set_zlim(0, H)
    ax.set_box_aspect((W, D, H))
    ax.view_init(elev=elev, azim=azim)
    ax.set_xlabel("X (m)"); ax.set_ylabel("Z (m)"); ax.set_zlabel("Y (m)")
    ax.set_title(f"Populated office room — {label}", fontsize=12, fontweight="bold", color=_TXT)
    fig.savefig(path, dpi=150, bbox_inches="tight"); plt.close(fig)


def meshrender(out_dir, room, path):
    """Render the real furniture meshes from scene.glb with the room as a
    non-occluding wireframe (walls solid would hide everything in matplotlib)."""
    import trimesh
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection, Line3DCollection
    W, D, H = room["width"], room["depth"], room.get("height", 3.0)
    scene = trimesh.load(str(out_dir / "scene.glb"))
    for g in [n for n in list(scene.geometry) if n.startswith("room-")]:
        scene.delete_geometry(g)
    mesh = scene.to_geometry()
    tris = mesh.triangles[:, :, [0, 2, 1]]   # world (x, y-up, z) -> plot (x, z, y)
    light = np.array([0.4, 0.85, 0.5]); light /= np.linalg.norm(light)
    shade = np.clip(mesh.face_normals @ light, 0, 1) * 0.6 + 0.4
    try:
        fc = mesh.visual.face_colors[:, :3] / 255.0
    except Exception:
        fc = np.full((len(tris), 3), 0.6)
    colors = np.clip(fc * shade[:, None], 0, 1)

    fig = plt.figure(figsize=(11, 7)); ax = fig.add_subplot(111, projection="3d")
    # floor + room wireframe (plot coords: x=X, y=Z, z=Y-up)
    ax.add_collection3d(Poly3DCollection([[(0, 0, 0), (W, 0, 0), (W, D, 0), (0, D, 0)]],
                                         facecolor="#efece4", alpha=0.4))
    c = [(0, 0, 0), (W, 0, 0), (W, D, 0), (0, D, 0),
         (0, 0, H), (W, 0, H), (W, D, H), (0, D, H)]
    edges = [(0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4),
             (0, 4), (1, 5), (2, 6), (3, 7)]
    ax.add_collection3d(Line3DCollection([[c[a], c[b]] for a, b in edges],
                                         colors="#9a9a9a", linewidths=1.0))
    ax.add_collection3d(Poly3DCollection(tris, facecolors=colors, edgecolor="none"))
    ax.set_xlim(0, W); ax.set_ylim(0, D); ax.set_zlim(0, H)
    ax.set_box_aspect((W, D, H))
    ax.view_init(elev=24, azim=-62); ax.set_axis_off()
    ax.set_title("Office room — real furniture, AI-placed", fontweight="bold", color=_TXT)
    fig.savefig(path, dpi=150, bbox_inches="tight"); plt.close(fig)


def main(out_dir):
    out_dir = Path(out_dir)
    sched = json.loads((out_dir / "schedule.json").read_text(encoding="utf-8"))
    room, items = sched["room"], sched["items"]
    rdir = out_dir / "renders"; rdir.mkdir(exist_ok=True)
    floorplan(room, items, rdir / "floorplan.png")
    angles = [(-55, 24, "front-right"), (40, 24, "front-left"),
              (135, 22, "back-left"), (-130, 30, "back-right")]
    paths = [str(rdir / "floorplan.png")]
    for i, (az, el, lbl) in enumerate(angles, 1):
        p = rdir / f"view_{i:02d}.png"
        view3d(room, items, p, az, el, lbl)
        paths.append(str(p))
    try:
        meshrender(out_dir, room, rdir / "furniture3d.png")
        paths.append(str(rdir / "furniture3d.png"))
    except Exception as exc:
        print(f"[render_scene] mesh render skipped: {exc}", file=sys.stderr)
    print(json.dumps({"success": True, "renders": paths}))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "demo/out")
