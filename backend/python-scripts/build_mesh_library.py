"""
Build a small retrieval library for SCS office furniture.

Produces:
  data/mesh_library/<id>.glb        per-variant GLB meshes
  data/mesh_library/<id>.thumb.png  front-view silhouette render
  data/mesh_library/index.faiss     L2-normalised DINOv2 embedding index
  data/mesh_library/manifest.json   list of {id, category, glb, thumb, dimensions_m}

The library is procedurally generated. Each category has multiple variants
so DINOv2 retrieval picks a plausibly-different shape per input photo.

This is the substitution point for the real Amazon Berkeley Objects subset:
swap the variants list for downloaded ABO meshes, run this script again, done.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import numpy as np
import trimesh
from PIL import Image, ImageDraw

REPO_ROOT = Path(__file__).resolve().parents[2]
LIBRARY_DIR = REPO_ROOT / "data" / "mesh_library"
LIBRARY_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Procedural mesh builders (richer than primitives in run_detect_and_place)
# ---------------------------------------------------------------------------
def chair_classic(h=0.95, w=0.55, d=0.55, leg_style="straight"):
    parts = []
    seat_t = 0.06
    seat = trimesh.creation.box(extents=[w, d, seat_t]); seat.apply_translation([0, 0, h * 0.45]); parts.append(seat)
    back = trimesh.creation.box(extents=[w, 0.06, h * 0.45]); back.apply_translation([0, -d / 2 + 0.03, h * 0.7]); parts.append(back)
    leg_h = h * 0.45
    leg_inset = 0.05
    radius = 0.025 if leg_style == "straight" else 0.04
    for x in [-w / 2 + leg_inset, w / 2 - leg_inset]:
        for y in [-d / 2 + leg_inset, d / 2 - leg_inset]:
            leg = trimesh.creation.cylinder(radius=radius, height=leg_h, sections=20)
            leg.apply_translation([x, y, leg_h / 2]); parts.append(leg)
    return trimesh.util.concatenate(parts)


def chair_with_arms(h=0.95, w=0.60, d=0.60):
    base = chair_classic(h, w, d)
    parts = [base]
    arm_h = 0.20
    arm_z = h * 0.45 + arm_h / 2 + 0.03
    for x_sign in (-1, 1):
        arm = trimesh.creation.box(extents=[0.04, d * 0.5, arm_h])
        arm.apply_translation([x_sign * (w / 2 - 0.02), 0, arm_z]); parts.append(arm)
        post = trimesh.creation.box(extents=[0.04, 0.04, h * 0.2])
        post.apply_translation([x_sign * (w / 2 - 0.02), 0, h * 0.55]); parts.append(post)
    return trimesh.util.concatenate(parts)


def chair_swivel(h=1.10, w=0.60, d=0.60):
    parts = []
    # padded seat
    seat = trimesh.creation.box(extents=[w, d, 0.08]); seat.apply_translation([0, 0, h * 0.45]); parts.append(seat)
    # tall padded back
    back = trimesh.creation.box(extents=[w * 0.95, 0.06, h * 0.50]); back.apply_translation([0, -d / 2 + 0.03, h * 0.72]); parts.append(back)
    # central column
    col = trimesh.creation.cylinder(radius=0.035, height=h * 0.42, sections=20)
    col.apply_translation([0, 0, h * 0.22]); parts.append(col)
    # 5-star base with castors
    for i in range(5):
        angle = i * 2 * np.pi / 5
        arm = trimesh.creation.cylinder(radius=0.018, height=0.22, sections=8)
        T = trimesh.transformations.rotation_matrix(angle, [0, 0, 1])
        arm.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [0, 1, 0]))
        arm.apply_transform(T)
        arm.apply_translation([0.11 * np.cos(angle), 0.11 * np.sin(angle), 0.04]); parts.append(arm)
        wheel = trimesh.creation.icosphere(radius=0.035, subdivisions=2)
        wheel.apply_translation([0.22 * np.cos(angle), 0.22 * np.sin(angle), 0.03]); parts.append(wheel)
    return trimesh.util.concatenate(parts)


def chair_stool(h=0.75, w=0.40, d=0.40):
    parts = []
    seat = trimesh.creation.cylinder(radius=w / 2, height=0.04, sections=20)
    seat.apply_translation([0, 0, h * 0.94]); parts.append(seat)
    for ang_idx in range(4):
        ang = ang_idx * np.pi / 2 + np.pi / 4
        leg = trimesh.creation.cylinder(radius=0.018, height=h * 0.92, sections=12)
        leg.apply_translation([w * 0.32 * np.cos(ang), w * 0.32 * np.sin(ang), h * 0.46]); parts.append(leg)
    return trimesh.util.concatenate(parts)


def sofa_two_seater(h=0.85, w=1.80, d=0.90):
    parts = []
    base = trimesh.creation.box(extents=[w, d, h * 0.55]); base.apply_translation([0, 0, h * 0.275]); parts.append(base)
    back = trimesh.creation.box(extents=[w, 0.20, h * 0.50]); back.apply_translation([0, -d / 2 + 0.10, h * 0.7]); parts.append(back)
    for x_sign in (-1, 1):
        arm = trimesh.creation.box(extents=[0.18, d, h * 0.60]); arm.apply_translation([x_sign * (w / 2 - 0.09), 0, h * 0.45]); parts.append(arm)
    for cx in [-w / 4, w / 4]:
        cushion = trimesh.creation.box(extents=[w / 2 - 0.25, d * 0.85, 0.10])
        cushion.apply_translation([cx, 0, h * 0.6]); parts.append(cushion)
    return trimesh.util.concatenate(parts)


def desk_office(h=0.74, w=1.60, d=0.80):
    parts = []
    top = trimesh.creation.box(extents=[w, d, 0.04]); top.apply_translation([0, 0, h - 0.02]); parts.append(top)
    # pedestal on one side
    ped = trimesh.creation.box(extents=[0.45, d - 0.06, h - 0.06]); ped.apply_translation([w / 2 - 0.225, 0, (h - 0.06) / 2]); parts.append(ped)
    for y in [-d / 2 + 0.04, d / 2 - 0.04]:
        leg = trimesh.creation.box(extents=[0.04, 0.04, h - 0.06])
        leg.apply_translation([-w / 2 + 0.05, y, (h - 0.06) / 2]); parts.append(leg)
    return trimesh.util.concatenate(parts)


def table_round(h=0.74, w=1.20, d=1.20):
    parts = []
    top = trimesh.creation.cylinder(radius=w / 2, height=0.04, sections=32)
    top.apply_translation([0, 0, h - 0.02]); parts.append(top)
    col = trimesh.creation.cylinder(radius=0.06, height=h - 0.04, sections=16)
    col.apply_translation([0, 0, (h - 0.04) / 2]); parts.append(col)
    base = trimesh.creation.cylinder(radius=w * 0.30, height=0.05, sections=20)
    base.apply_translation([0, 0, 0.025]); parts.append(base)
    return trimesh.util.concatenate(parts)


def cabinet_storage(h=1.80, w=0.80, d=0.40):
    parts = []
    body = trimesh.creation.box(extents=[w, d, h]); body.apply_translation([0, 0, h / 2]); parts.append(body)
    door_split = trimesh.creation.box(extents=[0.01, d * 0.5, h - 0.10])
    door_split.apply_translation([0, -d / 2 + 0.005, h / 2]); parts.append(door_split)
    handle1 = trimesh.creation.box(extents=[0.02, 0.02, 0.10])
    handle1.apply_translation([-w / 6, -d / 2 + 0.02, h * 0.6]); parts.append(handle1)
    handle2 = trimesh.creation.box(extents=[0.02, 0.02, 0.10])
    handle2.apply_translation([w / 6, -d / 2 + 0.02, h * 0.6]); parts.append(handle2)
    return trimesh.util.concatenate(parts)


def bookshelf(h=1.80, w=0.80, d=0.30):
    parts = []
    body = trimesh.creation.box(extents=[w, 0.02, h]); body.apply_translation([0, -d / 2 + 0.01, h / 2]); parts.append(body)
    for x_sign in (-1, 1):
        side = trimesh.creation.box(extents=[0.02, d, h]); side.apply_translation([x_sign * (w / 2 - 0.01), 0, h / 2]); parts.append(side)
    for sh in range(1, 5):
        shelf = trimesh.creation.box(extents=[w - 0.04, d - 0.05, 0.02])
        shelf.apply_translation([0, 0, sh * (h / 5)]); parts.append(shelf)
    return trimesh.util.concatenate(parts)


def lamp_floor(h=1.60, w=0.30, d=0.30):
    parts = []
    base = trimesh.creation.cylinder(radius=w * 0.45, height=0.03, sections=24)
    base.apply_translation([0, 0, 0.015]); parts.append(base)
    pole = trimesh.creation.cylinder(radius=0.018, height=h * 0.82, sections=12)
    pole.apply_translation([0, 0, h * 0.43]); parts.append(pole)
    shade = trimesh.creation.cone(radius=w * 0.5, height=0.25, sections=20)
    shade.apply_transform(trimesh.transformations.rotation_matrix(np.pi, [1, 0, 0]))
    shade.apply_translation([0, 0, h - 0.05]); parts.append(shade)
    return trimesh.util.concatenate(parts)


def monitor_standard(h=0.55, w=0.62, d=0.18):
    parts = []
    screen = trimesh.creation.box(extents=[w, 0.04, h * 0.65]); screen.apply_translation([0, 0, h * 0.5 + 0.06]); parts.append(screen)
    stand = trimesh.creation.box(extents=[w * 0.25, d, 0.04]); stand.apply_translation([0, 0, 0.02]); parts.append(stand)
    neck = trimesh.creation.cylinder(radius=0.03, height=0.07, sections=12); neck.apply_translation([0, 0, 0.07]); parts.append(neck)
    return trimesh.util.concatenate(parts)


# ---------------------------------------------------------------------------
# Library catalog
# ---------------------------------------------------------------------------
CATALOG = [
    ("chair_classic_a",       "office_chair", chair_classic, {}),
    ("chair_classic_b",       "office_chair", chair_classic, {"h": 0.90, "w": 0.50, "d": 0.50}),
    ("chair_classic_c",       "office_chair", chair_classic, {"h": 1.00, "w": 0.55, "d": 0.55, "leg_style": "turned"}),
    ("chair_with_arms",       "office_chair", chair_with_arms, {}),
    ("chair_swivel",          "office_chair", chair_swivel, {}),
    ("chair_stool",           "office_chair", chair_stool, {}),
    ("sofa_two_seater",       "sofa",         sofa_two_seater, {}),
    ("sofa_compact",          "sofa",         sofa_two_seater, {"w": 1.50, "d": 0.80}),
    ("desk_office",           "table",        desk_office, {}),
    ("desk_compact",          "table",        desk_office, {"w": 1.20, "d": 0.70}),
    ("table_round",           "table",        table_round, {}),
    ("table_round_small",     "table",        table_round, {"w": 0.90, "d": 0.90, "h": 0.74}),
    ("cabinet_tall",          "appliance",    cabinet_storage, {}),
    ("cabinet_low",           "appliance",    cabinet_storage, {"h": 1.00, "w": 0.80, "d": 0.40}),
    ("bookshelf_tall",        "appliance",    bookshelf, {}),
    ("bookshelf_low",         "appliance",    bookshelf, {"h": 1.20, "w": 0.80, "d": 0.30}),
    ("lamp_floor",            "plant",        lamp_floor, {}),  # treated as floor-standing object
    ("monitor_standard",      "monitor",      monitor_standard, {}),
    ("monitor_wide",          "monitor",      monitor_standard, {"w": 0.80, "h": 0.45}),
]


def render_silhouette(mesh: trimesh.Trimesh, out_png: Path, size: int = 224):
    """Pure-numpy front-view silhouette render: project vertices to 2D, draw a
    convex outline. Sufficient as a shape signature for DINOv2 retrieval."""
    verts = mesh.vertices
    # Front view: project onto XZ plane (Y is depth, Z is up)
    xs, zs = verts[:, 0], verts[:, 2]
    if xs.size == 0:
        Image.new("RGB", (size, size), (255, 255, 255)).save(out_png)
        return

    # Map vertices to a centred [0, size]^2 image with 10% margin
    pad = int(size * 0.10)
    span = max(xs.max() - xs.min(), zs.max() - zs.min(), 1e-3)
    scale = (size - 2 * pad) / span
    cx = (xs.min() + xs.max()) / 2
    cz = (zs.min() + zs.max()) / 2
    px = (xs - cx) * scale + size / 2
    py = size - ((zs - cz) * scale + size / 2)  # flip Y because image origin top-left

    img = Image.new("RGB", (size, size), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    # Draw triangles as filled polygons for a richer silhouette
    for face in mesh.faces:
        p = [(px[i], py[i]) for i in face]
        try:
            draw.polygon(p, fill=(40, 40, 50), outline=(40, 40, 50))
        except Exception:
            pass
    img.save(out_png)


def embed_with_dinov2(image_paths):
    """Return an (N, D) array of L2-normalised DINOv2-base embeddings."""
    import torch
    from transformers import AutoImageProcessor, AutoModel
    device = "cuda" if torch.cuda.is_available() else "cpu"
    mid = "facebook/dinov2-base"
    processor = AutoImageProcessor.from_pretrained(mid)
    model = AutoModel.from_pretrained(mid).to(device).eval()
    embeddings = []
    for p in image_paths:
        img = Image.open(p).convert("RGB")
        inputs = processor(images=img, return_tensors="pt").to(device)
        with torch.no_grad():
            outputs = model(**inputs)
        emb = outputs.last_hidden_state[:, 0, :].cpu().numpy().astype(np.float32)
        emb /= max(np.linalg.norm(emb), 1e-6)
        embeddings.append(emb[0])
    return np.stack(embeddings, axis=0)


def main():
    import faiss
    manifest = []
    thumbs = []
    print(f"Building mesh library in: {LIBRARY_DIR}")
    for idx, (lid, category, builder, kwargs) in enumerate(CATALOG):
        glb_path = LIBRARY_DIR / f"{lid}.glb"
        thumb_path = LIBRARY_DIR / f"{lid}.thumb.png"
        mesh = builder(**kwargs)
        mesh.apply_translation([0, 0, -mesh.bounding_box.bounds[0][2]])  # rest on z=0
        mesh.export(str(glb_path))
        render_silhouette(mesh, thumb_path)
        ext = mesh.bounding_box.extents
        manifest.append({
            "id": lid,
            "category": category,
            "glb": glb_path.name,
            "thumb": thumb_path.name,
            "dimensions_m": {
                "height": round(float(ext[2]), 3),
                "width":  round(float(ext[0]), 3),
                "depth":  round(float(ext[1]), 3),
            },
        })
        thumbs.append(thumb_path)
        print(f"  [{idx+1}/{len(CATALOG)}] {lid} ({category}) — {ext[0]:.2f} x {ext[1]:.2f} x {ext[2]:.2f} m")

    print("Embedding thumbnails with DINOv2-base...")
    embs = embed_with_dinov2(thumbs)
    dim = embs.shape[1]
    index = faiss.IndexFlatIP(dim)  # inner product = cosine after L2-norm
    index.add(embs)
    faiss.write_index(index, str(LIBRARY_DIR / "index.faiss"))
    (LIBRARY_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"\nLibrary: {len(manifest)} meshes, {dim}-d index at {LIBRARY_DIR}/index.faiss")


if __name__ == "__main__":
    main()
