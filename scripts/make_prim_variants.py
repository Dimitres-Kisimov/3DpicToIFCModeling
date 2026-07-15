"""make_prim_variants.py — parametric style variants for the 15 late-added
catalog categories (presentation kit + tier-2 office realism), registered as
real selectable catalog items with engine tag PRIM.

STRICT rule (user): only the 15 categories in question, exact category names,
every mesh IS the item — different recognizable styles of the same product.
These are our own builds: the cleanest license possible.

    python scripts/make_prim_variants.py     (server running)
"""
import json
import tempfile
import urllib.request
import uuid
from pathlib import Path

import numpy as np
import trimesh
from trimesh.creation import box as _box, cylinder as _cyl
from trimesh.visual.material import PBRMaterial

BASE = "http://localhost:3000"

# palette
WHITE = [0.92, 0.92, 0.90, 1]
OFFW = [0.96, 0.95, 0.92, 1]
GREY = [0.55, 0.57, 0.60, 1]
DGREY = [0.28, 0.29, 0.31, 1]
BLACK = [0.12, 0.12, 0.13, 1]
SILVER = [0.75, 0.76, 0.78, 1]
RED = [0.78, 0.12, 0.10, 1]
GREEN = [0.10, 0.45, 0.25, 1]
BLUE = [0.66, 0.78, 0.88, 1]
WOOD = [0.55, 0.40, 0.26, 1]
CREAM = [0.90, 0.86, 0.74, 1]


def B(w, d, h, x=0.0, y=0.0, z=0.0, c=GREY):
    """Z-up box: w×d footprint, h tall, CENTER at (x, y), BASE at z."""
    m = _box(extents=[w, d, h])
    m.apply_translation([x, y, z + h / 2])
    return (m, c)


def C(r, h, x=0.0, y=0.0, z=0.0, c=GREY, axis="z"):
    m = _cyl(radius=r, height=h, sections=24)
    if axis == "y":
        m.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [1, 0, 0]))
    elif axis == "x":
        m.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [0, 1, 0]))
    m.apply_translation([x, y, z + (h / 2 if axis == "z" else 0)])
    return (m, c)


def V():
    """variant builders: category -> [(style_name, [parts])]"""
    out = {}

    out["coat_rack"] = [
        ("classic pole", [C(0.03, 1.65, c=DGREY), B(0.5, 0.5, 0.04, c=DGREY)]
         + [C(0.015, 0.16, x=0.08 * dx, y=0.08 * dy, z=1.45 + k * 0.08, c=SILVER, axis="x" if dx else "y")
            for k, (dx, dy) in enumerate([(1, 0), (-1, 0), (0, 1), (0, -1)])]),
        ("twin post", [C(0.025, 1.7, x=-0.12, c=WOOD), C(0.025, 1.7, x=0.12, c=WOOD),
                       B(0.44, 0.06, 0.05, z=1.55, c=WOOD), B(0.5, 0.3, 0.04, c=WOOD)]),
        ("panel pegs", [B(0.5, 0.06, 1.6, y=-0.2, c=WOOD), B(0.5, 0.44, 0.04, c=DGREY)]
         + [C(0.014, 0.14, x=-0.16 + 0.16 * k, y=-0.14, z=1.35, c=SILVER, axis="y")
            for k in range(3)]),
    ]

    out["coffee_machine"] = [
        ("espresso", [B(0.28, 0.34, 0.36, c=DGREY), B(0.24, 0.10, 0.06, y=0.14, z=0.20, c=SILVER),
                      C(0.025, 0.08, y=0.14, z=0.12, c=SILVER), B(0.20, 0.16, 0.02, y=0.10, z=0.02, c=SILVER)]),
        ("drip carafe", [B(0.26, 0.30, 0.42, y=-0.04, c=BLACK), C(0.07, 0.16, y=0.08, z=0.02, c=BLUE),
                         B(0.24, 0.10, 0.05, y=0.08, z=0.34, c=BLACK)]),
        ("pod machine", [C(0.11, 0.34, c=RED), B(0.16, 0.20, 0.05, y=0.10, z=0.02, c=DGREY),
                         B(0.10, 0.12, 0.08, y=0.06, z=0.26, c=DGREY)]),
    ]

    out["fire_extinguisher"] = [
        ("classic 6kg", [C(0.075, 0.44, z=0.05, c=RED), C(0.02, 0.07, z=0.49, c=BLACK),
                         B(0.05, 0.12, 0.04, z=0.52, c=BLACK), C(0.012, 0.30, x=0.08, z=0.15, c=BLACK)]),
        ("slim 2kg", [C(0.055, 0.50, z=0.04, c=RED), C(0.016, 0.06, z=0.54, c=BLACK),
                      B(0.04, 0.10, 0.035, z=0.57, c=BLACK)]),
    ]

    out["first_aid_cabinet"] = [
        ("DIN green", [B(0.34, 0.14, 0.44, c=GREEN), B(0.20, 0.015, 0.06, y=0.075, z=0.19, c=WHITE),
                       B(0.06, 0.015, 0.20, y=0.075, z=0.12, c=WHITE)]),
        ("white steel", [B(0.34, 0.14, 0.44, c=WHITE), B(0.20, 0.015, 0.06, y=0.075, z=0.19, c=GREEN),
                         B(0.06, 0.015, 0.20, y=0.075, z=0.12, c=GREEN),
                         B(0.05, 0.02, 0.10, x=0.15, y=0.075, z=0.17, c=SILVER)]),
    ]

    out["flipchart"] = [
        ("tripod", [B(0.68, 0.03, 0.95, z=0.85, c=WHITE), B(0.70, 0.05, 0.05, z=1.80, c=GREY)]
         + [C(0.018, 1.35, x=dx, y=dy, z=0.0, c=GREY)
            for dx, dy in [(-0.30, 0.18), (0.30, 0.18), (0.0, -0.30)]]),
        ("frame stand", [B(0.68, 0.03, 0.95, z=0.85, c=WHITE),
                         C(0.02, 1.75, x=-0.30, c=DGREY), C(0.02, 1.75, x=0.30, c=DGREY),
                         B(0.66, 0.30, 0.04, c=DGREY)]),
        ("mobile", [B(0.68, 0.03, 0.95, z=0.80, c=WHITE),
                    C(0.02, 1.70, x=-0.28, c=SILVER), C(0.02, 1.70, x=0.28, c=SILVER),
                    B(0.60, 0.40, 0.04, z=0.02, c=SILVER)]
         + [C(0.035, 0.02, x=dx, y=dy, z=0.0, c=BLACK)
            for dx, dy in [(-0.26, 0.16), (0.26, 0.16), (-0.26, -0.16), (0.26, -0.16)]]),
    ]

    out["lectern"] = [
        ("panel", [B(0.58, 0.42, 1.02, c=WOOD), B(0.60, 0.48, 0.06, z=1.02, c=WOOD),
                   B(0.58, 0.06, 0.10, y=0.24, z=1.08, c=WOOD)]),
        ("column", [C(0.09, 1.00, c=DGREY), B(0.58, 0.46, 0.05, z=1.00, c=WOOD),
                    B(0.50, 0.42, 0.04, z=0.0, c=DGREY)]),
        ("open frame", [B(0.06, 0.42, 1.05, x=-0.25, c=SILVER), B(0.06, 0.42, 1.05, x=0.25, c=SILVER),
                        B(0.58, 0.46, 0.05, z=1.05, c=WHITE), B(0.56, 0.40, 0.04, z=0.35, c=WHITE)]),
    ]

    out["microwave"] = [
        ("stainless", [B(0.48, 0.36, 0.28, c=SILVER), B(0.30, 0.015, 0.22, x=-0.06, y=0.185, z=0.03, c=BLACK),
                       B(0.03, 0.02, 0.20, x=0.13, y=0.185, z=0.04, c=DGREY),
                       B(0.10, 0.015, 0.22, x=0.18, y=0.185, z=0.03, c=SILVER)]),
        ("black glass", [B(0.48, 0.36, 0.28, c=BLACK), B(0.34, 0.015, 0.22, x=-0.05, y=0.185, z=0.03, c=DGREY),
                         B(0.09, 0.015, 0.20, x=0.18, y=0.185, z=0.04, c=GREY)]),
    ]

    out["partition"] = [
        ("fabric", [B(1.46, 0.05, 1.50, z=0.08, c=GREY), B(1.50, 0.07, 0.04, z=1.58, c=DGREY),
                    B(0.30, 0.30, 0.04, x=-0.60, c=DGREY), B(0.30, 0.30, 0.04, x=0.60, c=DGREY)]),
        ("frosted", [B(1.46, 0.03, 1.45, z=0.12, c=BLUE), B(1.50, 0.05, 0.05, z=1.57, c=SILVER),
                     B(1.50, 0.05, 0.06, z=0.06, c=SILVER),
                     B(0.26, 0.30, 0.05, x=-0.58, c=SILVER), B(0.26, 0.30, 0.05, x=0.58, c=SILVER)]),
    ]

    out["phone_booth"] = [
        ("dark cube", [B(1.02, 1.02, 2.15, c=DGREY), B(0.62, 0.03, 1.75, y=0.51, z=0.18, c=BLUE),
                       B(1.02, 1.02, 0.06, z=2.15, c=BLACK)]),
        ("light pod", [B(1.02, 1.02, 2.12, c=OFFW), B(0.56, 0.03, 1.70, y=0.51, z=0.20, c=BLUE),
                       B(0.10, 0.03, 1.70, x=0.40, y=0.51, z=0.20, c=DGREY)]),
        ("acoustic", [B(1.02, 1.02, 2.15, c=GREEN), B(0.60, 0.03, 1.72, y=0.51, z=0.20, c=BLUE),
                      B(1.06, 1.06, 0.05, z=0.0, c=DGREY)]),
    ]

    out["presentation_screen"] = [
        ("wall matte", [B(2.36, 0.06, 1.44, z=0.03, c=WHITE), B(2.40, 0.09, 0.05, z=1.47, c=BLACK),
                        B(2.40, 0.09, 0.05, z=0.0, c=BLACK)]),
        ("slim bezel", [B(2.38, 0.05, 1.46, z=0.02, c=OFFW), B(2.40, 0.07, 0.03, z=1.48, c=DGREY)]),
    ]

    out["printer"] = [
        ("floor MFP", [B(0.56, 0.56, 0.55, c=OFFW), B(0.52, 0.50, 0.30, z=0.55, c=WHITE),
                       B(0.36, 0.24, 0.04, y=0.20, z=0.85, c=DGREY),
                       B(0.44, 0.30, 0.06, y=-0.05, z=0.89, c=OFFW)]),
        ("desk on stand", [B(0.50, 0.50, 0.60, c=GREY), B(0.44, 0.38, 0.24, z=0.62, c=WHITE),
                           B(0.30, 0.20, 0.03, y=0.12, z=0.86, c=DGREY)]),
        ("copier tower", [B(0.58, 0.56, 0.90, c=WHITE), B(0.50, 0.46, 0.12, z=0.90, c=OFFW),
                          B(0.20, 0.40, 0.30, x=0.38, z=0.45, c=OFFW),
                          B(0.34, 0.22, 0.03, y=0.20, z=1.02, c=DGREY)]),
    ]

    out["projector"] = [
        ("office white", [B(0.36, 0.28, 0.11, c=WHITE), C(0.045, 0.04, x=-0.10, y=0.14, z=0.03, c=BLACK, axis="y"),
                          B(0.10, 0.06, 0.015, x=0.10, y=0.10, z=0.11, c=GREY)]),
        ("compact dark", [B(0.30, 0.24, 0.09, c=DGREY), C(0.04, 0.03, x=-0.08, y=0.12, z=0.025, c=BLACK, axis="y")]),
    ]

    out["server_rack"] = [
        ("closed 42U", [B(0.58, 0.78, 1.95, c=BLACK)]
         + [B(0.50, 0.02, 0.03, y=0.39, z=0.25 + k * 0.30, c=DGREY) for k in range(5)]),
        ("open frame", [B(0.05, 0.05, 1.90, x=dx, y=dy, c=DGREY)
                        for dx, dy in [(-0.26, -0.36), (0.26, -0.36), (-0.26, 0.36), (0.26, 0.36)]]
         + [B(0.55, 0.75, 0.03, z=0.30 + k * 0.45, c=GREY) for k in range(4)]),
    ]

    out["water_dispenser"] = [
        ("bottle cooler", [B(0.33, 0.33, 0.85, c=WHITE), C(0.13, 0.22, z=0.85, c=BLUE),
                           B(0.06, 0.04, 0.05, x=-0.08, y=0.17, z=0.62, c=BLUE),
                           B(0.06, 0.04, 0.05, x=0.08, y=0.17, z=0.62, c=RED)]),
        ("slim POU", [B(0.30, 0.32, 1.05, c=SILVER), B(0.22, 0.06, 0.16, y=0.17, z=0.70, c=DGREY),
                      B(0.05, 0.04, 0.04, x=-0.06, y=0.19, z=0.66, c=BLUE)]),
        ("column", [C(0.16, 1.02, c=OFFW), B(0.18, 0.10, 0.12, y=0.14, z=0.68, c=DGREY)]),
    ]

    out["whiteboard"] = [
        ("classic tray", [B(1.76, 0.04, 1.16, z=0.02, c=WHITE), B(1.80, 0.06, 0.04, z=1.16, c=SILVER),
                          B(1.80, 0.06, 0.04, z=0.0, c=SILVER), B(1.60, 0.10, 0.03, y=0.06, z=0.0, c=SILVER)]),
        ("glass", [B(1.76, 0.03, 1.18, z=0.02, c=BLUE)]
         + [C(0.02, 0.05, x=dx, z=dz, c=SILVER, axis="y")
            for dx, dz in [(-0.80, 0.10), (0.80, 0.10), (-0.80, 1.12), (0.80, 1.12)]]),
        ("mobile", [B(1.70, 0.04, 1.10, z=0.55, c=WHITE),
                    C(0.02, 1.70, x=-0.80, c=GREY), C(0.02, 1.70, x=0.80, c=GREY),
                    B(0.50, 0.40, 0.04, x=-0.80, c=DGREY), B(0.50, 0.40, 0.04, x=0.80, c=DGREY)]),
    ]
    return out


def export_glb(parts, path):
    scene = trimesh.Scene()
    rotx = trimesh.transformations.rotation_matrix(-np.pi / 2, [1, 0, 0])  # Z-up -> Y-up
    for k, (m, c) in enumerate(parts):
        m = m.copy()
        m.apply_transform(rotx)
        m.visual = trimesh.visual.TextureVisuals(material=PBRMaterial(
            baseColorFactor=c, metallicFactor=0.1, roughnessFactor=0.7))
        scene.add_geometry(m, node_name=f"p{k}")
    scene.export(str(path))


def register(glb_path, category, display):
    boundary = uuid.uuid4().hex
    data = Path(glb_path).read_bytes()
    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="category"\r\n\r\n'
            f'{category}\r\n'
            f'--{boundary}\r\nContent-Disposition: form-data; name="engine"\r\n\r\n'
            f'PRIM\r\n'
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
            f'filename="{display}.glb"\r\nContent-Type: model/gltf-binary\r\n\r\n'
            ).encode() + data + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(BASE + "/api/room/upload", data=body, method="POST",
                                 headers={"Content-Type":
                                          f"multipart/form-data; boundary={boundary}"})
    return json.load(urllib.request.urlopen(req, timeout=300))


def main():
    variants = V()
    total = ok = 0
    for category, styles in variants.items():
        for style, parts in styles:
            total += 1
            try:
                with tempfile.TemporaryDirectory() as td:
                    glb = Path(td) / f"{category}_{style.replace(' ', '_')}.glb"
                    export_glb(parts, glb)
                    r = register(glb, category, f"{category} — {style}")
                item = r.get("item") or {}
                print(f"OK  {category:22s} {style:15s} -> {item.get('id')}", flush=True)
                ok += 1
            except Exception as e:
                print(f"FAIL {category} {style}: {str(e)[:140]}", flush=True)
    print(f"{ok}/{total} PRIM variants registered", flush=True)


if __name__ == "__main__":
    main()
