"""
Build a DINOv2 + FAISS retrieval index over the downloaded ABO meshes.

Inputs (from download_abo_subset.py):
  data/mesh_library_abo/manifest.json  — per-mesh {id, category, glb, dimensions_m, source, license, attribution}
  data/mesh_library_abo/*.glb          — real artist-authored CAD meshes (CC-BY-4.0)

Outputs:
  data/mesh_library_abo/*.thumb.png    — front-view silhouettes
  data/mesh_library_abo/index.faiss    — DINOv2-base 768-d, L2-normalised, IndexFlatIP
  data/mesh_library_abo/manifest.json  — updated in place with thumb references

Once this runs, run_detect_and_place.py's _resolve_mesh_library() switches over
to the ABO library automatically (it prefers any folder with index.faiss +
manifest.json).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import trimesh
from PIL import Image, ImageDraw

REPO_ROOT = Path(__file__).resolve().parents[2]
LIBRARY_DIR = REPO_ROOT / "data" / "mesh_library_abo"


def render_silhouette(mesh: trimesh.Trimesh, out_png: Path, size: int = 224):
    """Project front view (XZ plane) to a centred filled-triangle silhouette."""
    verts = mesh.vertices
    if len(verts) == 0:
        Image.new("RGB", (size, size), (255, 255, 255)).save(out_png)
        return
    xs, zs = verts[:, 0], verts[:, 2]
    span = max(xs.max() - xs.min(), zs.max() - zs.min(), 1e-3)
    pad = int(size * 0.10)
    scale = (size - 2 * pad) / span
    cx = (xs.min() + xs.max()) / 2
    cz = (zs.min() + zs.max()) / 2
    px = (xs - cx) * scale + size / 2
    py = size - ((zs - cz) * scale + size / 2)

    img = Image.new("RGB", (size, size), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    # Sample faces (some ABO meshes have 100k+ faces — drawing all of them is slow)
    faces = mesh.faces
    if len(faces) > 8000:
        step = max(1, len(faces) // 8000)
        faces = faces[::step]
    for face in faces:
        try:
            p = [(float(px[i]), float(py[i])) for i in face]
            draw.polygon(p, fill=(40, 40, 50))
        except Exception:
            pass
    img.save(out_png)


def load_mesh_safely(glb_path: Path) -> trimesh.Trimesh | None:
    try:
        scene = trimesh.load(str(glb_path), force="mesh")
        if isinstance(scene, trimesh.Scene):
            geoms = [g for g in scene.geometry.values() if isinstance(g, trimesh.Trimesh) and len(g.faces) > 0]
            if not geoms:
                return None
            return trimesh.util.concatenate(geoms)
        return scene
    except Exception as e:
        print(f"[WARN] failed to load {glb_path.name}: {e}", flush=True)
        return None


def main():
    manifest_path = LIBRARY_DIR / "manifest.json"
    if not manifest_path.exists():
        print(f"[ERROR] no manifest at {manifest_path}; run download_abo_subset.py first", flush=True)
        sys.exit(1)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    print(f"[INFO] {len(manifest)} entries in manifest", flush=True)

    # Render thumbnails and extract real mesh dimensions
    thumbs = []
    valid_manifest = []
    for idx, entry in enumerate(manifest):
        glb_path = LIBRARY_DIR / entry["glb"]
        if not glb_path.exists():
            print(f"[WARN] missing GLB: {glb_path.name}", flush=True)
            continue
        mesh = load_mesh_safely(glb_path)
        if mesh is None or len(mesh.faces) == 0:
            print(f"[WARN] invalid mesh: {glb_path.name}", flush=True)
            continue

        thumb_name = glb_path.stem + ".thumb.png"
        thumb_path = LIBRARY_DIR / thumb_name
        try:
            render_silhouette(mesh, thumb_path)
        except Exception as e:
            print(f"[WARN] silhouette failed for {glb_path.name}: {e}", flush=True)
            continue

        ext = mesh.bounding_box.extents
        # Store the canonical bounding-box dimensions from the actual mesh; ABO
        # listings can have unit ambiguity, so prefer the mesh-measured value
        # for retrieval. The original dimensions stay under raw_dimensions_m.
        new_entry = dict(entry)
        new_entry["thumb"] = thumb_name
        new_entry["mesh_dimensions_m"] = {
            "x": round(float(ext[0]), 3),
            "y": round(float(ext[1]), 3),
            "z": round(float(ext[2]), 3),
        }
        new_entry["faces"] = int(len(mesh.faces))
        valid_manifest.append(new_entry)
        thumbs.append(thumb_path)
        print(f"[INFO] [{idx+1}/{len(manifest)}] {entry['id']:50s}  faces={len(mesh.faces):6d}  bbox={ext}", flush=True)

    print(f"[INFO] {len(valid_manifest)} valid meshes (of {len(manifest)}) — embedding with DINOv2-base", flush=True)

    # DINOv2-base embeddings on the silhouettes
    import torch
    from transformers import AutoImageProcessor, AutoModel
    device = "cuda" if torch.cuda.is_available() else "cpu"
    mid = "facebook/dinov2-base"
    processor = AutoImageProcessor.from_pretrained(mid)
    model = AutoModel.from_pretrained(mid).to(device).eval()

    embs = []
    for p in thumbs:
        img = Image.open(p).convert("RGB")
        inputs = processor(images=img, return_tensors="pt").to(device)
        with torch.no_grad():
            outputs = model(**inputs)
        emb = outputs.last_hidden_state[:, 0, :].cpu().numpy().astype(np.float32)
        n = max(np.linalg.norm(emb), 1e-6)
        embs.append((emb / n)[0])
    embs = np.stack(embs, axis=0)
    print(f"[INFO] embeddings shape: {embs.shape}", flush=True)

    # FAISS index
    import faiss
    dim = embs.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(embs)
    index_path = LIBRARY_DIR / "index.faiss"
    faiss.write_index(index, str(index_path))
    print(f"[INFO] wrote FAISS index: {index_path}", flush=True)

    # Update manifest with thumb + measured dims + faces
    manifest_path.write_text(json.dumps(valid_manifest, indent=2), encoding="utf-8")
    print(f"[INFO] updated manifest: {manifest_path}", flush=True)

    # Per-category counts
    from collections import Counter
    cnt = Counter(m["category"] for m in valid_manifest)
    print("[INFO] === Library category counts ===", flush=True)
    for cat, n in sorted(cnt.items()):
        print(f"[INFO]   {cat:14s}  {n}", flush=True)
    print(f"[INFO] Library ready: {len(valid_manifest)} meshes in {LIBRARY_DIR}", flush=True)


if __name__ == "__main__":
    main()
