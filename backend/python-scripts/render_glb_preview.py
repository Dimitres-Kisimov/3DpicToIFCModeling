"""
Renders a GLB to a 4-angle preview PNG using pyrender's offscreen renderer
(EGL backend) — gives real depth-sorted images, not matplotlib soup.

Usage:
    python render_glb_preview.py <input.glb> <output.png>
"""
import os
os.environ["PYOPENGL_PLATFORM"] = "egl"  # offscreen, no X11 needed

import sys
import numpy as np
import trimesh
import pyrender
from PIL import Image


def load_mesh(path: str) -> trimesh.Trimesh:
    obj = trimesh.load(path, force="mesh")
    if isinstance(obj, trimesh.Scene):
        obj = trimesh.util.concatenate([g for g in obj.geometry.values()
                                          if isinstance(g, trimesh.Trimesh)])
    return obj


def look_at(camera_pos, target, up=(0, 1, 0)):
    """Build a 4x4 camera pose matrix looking from camera_pos at target."""
    f = np.array(target) - np.array(camera_pos)
    f = f / np.linalg.norm(f)
    u = np.array(up, dtype=float)
    s = np.cross(f, u); s = s / np.linalg.norm(s)
    u2 = np.cross(s, f)
    m = np.eye(4)
    m[:3, 0] = s
    m[:3, 1] = u2
    m[:3, 2] = -f
    m[:3, 3] = camera_pos
    return m


def render_one(mesh, elev_deg, azim_deg, w=512, h=512):
    scene = pyrender.Scene(bg_color=(0.16, 0.16, 0.18, 1.0),
                            ambient_light=(0.3, 0.3, 0.3))
    pmesh = pyrender.Mesh.from_trimesh(mesh, smooth=False)
    scene.add(pmesh)

    elev = np.radians(elev_deg)
    azim = np.radians(azim_deg)
    r = 2.2
    cam_pos = (r * np.cos(elev) * np.sin(azim),
               r * np.sin(elev),
               r * np.cos(elev) * np.cos(azim))
    cam_pose = look_at(cam_pos, (0, 0, 0))
    cam = pyrender.PerspectiveCamera(yfov=np.pi / 4.0)
    scene.add(cam, pose=cam_pose)

    light = pyrender.DirectionalLight(color=(1, 1, 1), intensity=4.0)
    scene.add(light, pose=cam_pose)

    r = pyrender.OffscreenRenderer(w, h)
    color, _ = r.render(scene)
    r.delete()
    return Image.fromarray(color)


def main(argv):
    if len(argv) < 3:
        print("Usage: render_glb_preview.py <input.glb> <output.png>")
        sys.exit(1)
    in_path, out_path = argv[1], argv[2]
    print(f"loading {in_path} ...")
    mesh = load_mesh(in_path)
    print(f"loaded: {len(mesh.vertices)} verts, {len(mesh.faces)} faces")

    # Centre + unit-scale so camera frame fits any input
    mesh.apply_translation(-mesh.bounding_box.centroid)
    s = mesh.bounding_box.extents.max()
    if s > 0:
        mesh.apply_scale(1.0 / s)

    views = [("front", 10, 0), ("right", 10, 90),
             ("back",  10, 180), ("3/4",  20, 45)]
    tiles = []
    for name, elev, azim in views:
        print(f"  rendering {name} (elev={elev}, azim={azim}) ...")
        img = render_one(mesh, elev, azim, w=512, h=512)
        tiles.append((name, img))

    # 2x2 grid with labels
    grid = Image.new("RGB", (1024 + 16, 1024 + 48), (29, 29, 29))
    from PIL import ImageDraw, ImageFont
    draw = ImageDraw.Draw(grid)
    try:
        font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 18)
        title_font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 22)
    except Exception:
        font = ImageFont.load_default()
        title_font = font
    draw.text((10, 8), "InstantMesh chair preview — 4 angles",
              fill="white", font=title_font)

    positions = [(0, 40), (520, 40), (0, 560), (520, 560)]
    for (name, img), (x, y) in zip(tiles, positions):
        grid.paste(img, (x, y))
        draw.text((x + 8, y + 6), name, fill="white", font=font)

    grid.save(out_path)
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main(sys.argv)
