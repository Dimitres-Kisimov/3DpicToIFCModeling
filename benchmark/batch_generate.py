"""
batch_generate.py — the TripoSR A/B proof engine (app untouched; standalone).

Per image: segment (SAM2 -> rembg fallback, same as the app) -> TripoSR ->
the SAME light cleanup the app ships today  => raw.glb   ("TripoSR today")
-> repair_packs.repair_mesh(known category)  => improved.glb ("our improvement")
   (office_chair additionally gets the proven 5-star base graft, as in the app).

Then: software renders of both, silhouette-IoU + CLIP category agreement scores,
accurate timestamps, and (for 2 designated categories per list) an IFC spot-proof
through the existing createIFCFurniture.py.

TripoSR + CLIP load ONCE for the whole run.

    python batch_generate.py --lists 1
    python batch_generate.py --lists 2-10
"""
from __future__ import annotations
import os, sys, io, json, time, argparse, subprocess, traceback
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO / "backend" / "python-scripts"))
sys.path.insert(0, str(REPO / "backend" / "triposr"))

import numpy as np
import trimesh
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from PIL import Image

import repair_packs
from repair_packs import repair_mesh, UP

PY = sys.executable
IMG_DIR = HERE / "images"
RES_DIR = HERE / "results"

# the 17 picker items -> display name + real-world height (m) from catalog.py CATALOG_META
CATEGORIES = {
    "bookshelf": ("Bookshelf", 1.50), "cabinet": ("Cabinet", 1.20), "clock": ("Clock", 0.30),
    "coffee_table": ("Coffee Table", 0.45), "desk": ("Desk", 0.74),
    "filing_cabinet": ("Filing Cabinet", 1.32), "lamp": ("Lamp", 1.60),
    "laptop": ("Laptop", 0.25), "mirror": ("Mirror", 1.20), "monitor": ("Monitor", 0.45),
    "office_chair": ("Office Chair", 1.10), "picture_frame": ("Picture Frame", 0.50),
    "planter": ("Planter", 0.60), "side_table": ("Side Table", 0.55),
    "sofa": ("Sofa", 0.85), "stool": ("Stool", 0.50), "table": ("Table", 0.74),
}
CAT_LIST = list(CATEGORIES)
CLIP_LABELS = [v[0].lower() for v in CATEGORIES.values()] + ["other object"]


# ── one-time model loads ─────────────────────────────────────────────────────
def load_models():
    import torch
    from tsr.system import TSR
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"[batch] device={device} — loading TripoSR once...", flush=True)
    model = TSR.from_pretrained("stabilityai/TripoSR", config_name="config.yaml",
                                weight_name="model.ckpt")
    model.renderer.set_chunk_size(8192 if device == "cuda" else 2048)
    model.to(device)
    print("[batch] TripoSR ready. Loading CLIP (CPU)...", flush=True)
    from transformers import pipeline
    clip = pipeline("zero-shot-image-classification",
                    model="openai/clip-vit-base-patch32", device=-1)
    print("[batch] CLIP ready.", flush=True)
    return model, clip, device


# ── generation (mirrors run_triposr.py's app path, minus CLIP/depth-scale) ───
def generate_raw(model, device, image_path):
    import torch
    from tsr.utils import resize_foreground
    from run_triposr import _segment_foreground          # same segmenter as the app
    from _triposr_postprocess import clean_triposr_mesh  # same light cleanup as the app
    img_rgba = _segment_foreground(str(image_path))
    img_rgba = resize_foreground(img_rgba, 0.85)
    arr = np.array(img_rgba).astype(np.float32) / 255.0
    arr = arr[:, :, :3] * arr[:, :, 3:4] + (1 - arr[:, :, 3:4]) * 0.5
    image = Image.fromarray((arr * 255.0).astype(np.uint8))
    with torch.no_grad():
        scene_codes = model([image], device=device)
    mesh = model.extract_mesh(scene_codes, True, resolution=256 if device == "cuda" else 96)[0]
    del scene_codes
    if device == "cuda":
        torch.cuda.empty_cache()
    mesh = clean_triposr_mesh(mesh)                      # what the app ships today
    return mesh, img_rgba


def dominant_color(img_rgba):
    """k-means dominant colour on the cutout — same recipe as the app."""
    try:
        from scipy.cluster.vq import kmeans, vq
        arr = np.array(img_rgba)
        m = arr[:, :, 3] > 64
        if m.sum() == 0:
            return np.array([0.47, 0.47, 0.47, 1.0])
        fg = arr[:, :, :3][m].astype(np.float32)
        cent, _ = kmeans(fg, min(3, len(fg)))
        lab, _ = vq(fg, cent)
        c = cent[np.bincount(lab).argmax()] / 255.0
        return np.array([c[0], c[1], c[2], 1.0])
    except Exception:
        return np.array([0.47, 0.47, 0.47, 1.0])


def apply_color(mesh, rgba):
    mesh.visual = trimesh.visual.TextureVisuals(
        material=trimesh.visual.material.PBRMaterial(
            baseColorFactor=rgba, roughnessFactor=0.7, metallicFactor=0.0))
    return mesh


def scale_to_height(mesh, height_m):
    e = float(mesh.extents[UP])
    if e > 0:
        mesh.apply_scale(height_m / e)
    return mesh


# ── rendering (software, no GPU) — X-up native frame shown upright ───────────
_XUP_TO_ZUP = trimesh.transformations.rotation_matrix(-np.pi / 2, [0, 1, 0])

def render_mesh(mesh_in, out_png, az=-60, el=18, color=None):
    mesh = mesh_in.copy()
    mesh.apply_transform(_XUP_TO_ZUP)
    v, f = mesh.vertices, mesh.faces
    if len(f) > 24000:
        try:
            import fast_simplification
            vs, fs = fast_simplification.simplify(np.asarray(v, np.float32),
                                                  np.asarray(f, np.int32),
                                                  target_reduction=1 - 24000 / len(f))
            v, f = vs, fs
        except Exception:
            pass
    tri = v[f]
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    n = n / (np.linalg.norm(n, axis=1, keepdims=True) + 1e-9)
    light = np.array([0.4, -0.6, 0.8]); light = light / np.linalg.norm(light)
    lum = 0.35 + 0.65 * np.clip(np.abs(n @ light), 0, 1)
    base = np.array(color[:3]) if color is not None else np.array([0.62, 0.66, 0.72])
    cols = np.clip(lum[:, None] * base[None, :], 0, 1)
    order = np.argsort(tri[:, :, 1].mean(axis=1))[::-1]      # painter-ish
    fig = plt.figure(figsize=(4.2, 4.2), dpi=110)
    ax = fig.add_subplot(111, projection="3d")
    pc = Poly3DCollection(tri[order], facecolors=cols[order], edgecolors="none")
    ax.add_collection3d(pc)
    lo, hi = v.min(axis=0), v.max(axis=0)
    c, r = (lo + hi) / 2, float((hi - lo).max()) / 2 + 1e-6
    ax.set_xlim(c[0] - r, c[0] + r); ax.set_ylim(c[1] - r, c[1] + r); ax.set_zlim(c[2] - r, c[2] + r)
    ax.view_init(elev=el, azim=az)
    ax.set_axis_off(); ax.set_facecolor("white"); fig.patch.set_facecolor("white")
    plt.tight_layout(pad=0)
    fig.savefig(out_png, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def silhouette_mask(mesh_in, az, el=12, size=160):
    mesh = mesh_in.copy()
    mesh.apply_transform(_XUP_TO_ZUP)
    v, f = mesh.vertices, mesh.faces
    if len(f) > 12000:
        idx = np.random.RandomState(0).choice(len(f), 12000, replace=False)
        f = f[idx]
    tri = v[f]
    fig = plt.figure(figsize=(2, 2), dpi=size // 2)
    ax = fig.add_subplot(111, projection="3d")
    ax.add_collection3d(Poly3DCollection(tri, facecolors="black", edgecolors="black"))
    lo, hi = v.min(axis=0), v.max(axis=0)
    c, r = (lo + hi) / 2, float((hi - lo).max()) / 2 + 1e-6
    ax.set_xlim(c[0] - r, c[0] + r); ax.set_ylim(c[1] - r, c[1] + r); ax.set_zlim(c[2] - r, c[2] + r)
    ax.view_init(elev=el, azim=az); ax.set_axis_off()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor="white", bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    g = np.array(Image.open(buf).convert("L"))
    return g < 128


def _norm_mask(m, out=128):
    ys, xs = np.where(m)
    if len(ys) < 10:
        return None
    crop = m[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    h, w = crop.shape
    s = max(h, w)
    pad = np.zeros((s, s), bool)
    pad[(s - h) // 2:(s - h) // 2 + h, (s - w) // 2:(s - w) // 2 + w] = crop
    im = Image.fromarray(pad.astype(np.uint8) * 255).resize((out, out), Image.NEAREST)
    return np.array(im) > 127


def silhouette_iou(mesh, photo_mask):
    """Best IoU between the photo cutout silhouette and the mesh silhouette over
    8 azimuths (the photo's viewpoint is unknown)."""
    pm = _norm_mask(photo_mask)
    if pm is None:
        return 0.0
    best = 0.0
    for az in range(0, 360, 45):
        mm = _norm_mask(silhouette_mask(mesh, az))
        if mm is None:
            continue
        inter = np.logical_and(pm, mm).sum()
        union = np.logical_or(pm, mm).sum()
        if union:
            best = max(best, inter / union)
    return round(float(best), 3)


def clip_check(clip, png_path, category):
    """Does CLIP see the render as the right category?"""
    try:
        res = clip(Image.open(png_path).convert("RGB"), candidate_labels=CLIP_LABELS)
        top = res[0]["label"]
        want = CATEGORIES[category][0].lower()
        return {"label": top, "score": round(res[0]["score"], 3), "match": top == want}
    except Exception as e:
        return {"label": "error", "score": 0.0, "match": False, "error": str(e)}


def mesh_stats(mesh):
    """A multi-part mesh (body + legs) is 'watertight' when EVERY part is —
    trimesh's whole-mesh flag is always False for concatenations."""
    try:
        parts = mesh.split(only_watertight=False)
        comps = len(parts)
        wt = bool(parts) and all(p.is_watertight for p in parts)
    except Exception:
        comps, wt = -1, bool(mesh.is_watertight)
    return {"faces": int(len(mesh.faces)), "components": comps, "watertight": wt}


# ── IFC spot-proof (read-only use of the existing exporter) ──────────────────
def ifc_spot_proof(glb_path, category, out_dir):
    """Export the improved mesh through the app's REAL mesh-geometry IFC exporter
    (saveIFC.save_ifc_project — the same path the room export uses) and validate."""
    name, _height = CATEGORIES[category]
    ifc_path = out_dir / "item.ifc"
    try:
        import saveIFC
        saveIFC.save_ifc_project([{"glbPath": str(glb_path), "name": name,
                                   "category": name, "ifc_class": "IfcFurniture"}],
                                 str(ifc_path))
        ok = ifc_path.exists() and ifc_path.stat().st_size > 5000
        n_products = None
        if ok:
            import ifcopenshell
            f = ifcopenshell.open(str(ifc_path))
            # by_type includes subtypes (IfcFurniture < IfcFurnishingElement) — count once
            n_products = len(f.by_type("IfcFurnishingElement"))
        return {"ok": bool(ok and n_products), "size_kb": ifc_path.stat().st_size // 1024 if ok else 0,
                "furniture_elements": n_products, "note": "" if ok else "file too small/absent"}
    except Exception as e:
        return {"ok": False, "note": str(e)[:200]}


# ── per-item pipeline ─────────────────────────────────────────────────────────
def process_item(model, clip, device, list_no, category, image_path, do_ifc):
    image_path = Path(image_path).resolve()
    name, height_m = CATEGORIES[category]
    out = RES_DIR / f"list{list_no:02d}" / category
    out.mkdir(parents=True, exist_ok=True)
    rec = {"category": category, "display": name, "list": list_no,
           "image": str(image_path.relative_to(HERE)).replace("\\", "/"),
           "started_at": datetime.now().isoformat(timespec="seconds")}
    t0 = time.time()
    try:
        mesh_raw, img_rgba = generate_raw(model, device, image_path)
        color = dominant_color(img_rgba)
        photo_mask = np.array(img_rgba)[:, :, 3] > 64

        # ── "TripoSR today" ──
        raw = mesh_raw.copy()
        scale_to_height(raw, height_m)
        apply_color(raw, color)
        raw.export(out / "raw.glb")
        rec["raw"] = mesh_stats(raw)
        render_mesh(raw, out / "raw.png", color=color)
        rec["raw"]["iou"] = silhouette_iou(raw, photo_mask)
        rec["raw"]["clip"] = clip_check(clip, out / "raw.png", category)

        # ── "our improvement" ──
        imp = mesh_raw.copy()
        imp, report = repair_mesh(imp, label=category, category=name)
        if category == "office_chair":               # the proven 5-star base graft
            tmp = out / "_pre_graft.glb"
            scale_to_height(imp, height_m); apply_color(imp, color)
            imp.export(tmp)
            import graft_chair_base
            graft_chair_base.build(str(tmp), str(out / "improved.glb"))
            imp = trimesh.load(out / "improved.glb", force="mesh")
            try:
                tmp.unlink()
            except OSError:
                pass
            report["graft"] = "5-star base grafted (app-proven)"
        else:
            scale_to_height(imp, height_m)
            apply_color(imp, color)
            imp.export(out / "improved.glb")
        rec["improved"] = mesh_stats(imp)
        rec["improved"]["repair"] = report
        render_mesh(imp, out / "improved.png", color=color)
        rec["improved"]["iou"] = silhouette_iou(imp, photo_mask)
        rec["improved"]["clip"] = clip_check(clip, out / "improved.png", category)

        if do_ifc:
            rec["ifc"] = ifc_spot_proof(out / "improved.glb", category, out)
        rec["status"] = "ok"
    except Exception as e:
        rec["status"] = "failed"
        rec["error"] = f"{type(e).__name__}: {e}"
        traceback.print_exc()
        try:
            import torch
            if device == "cuda":
                torch.cuda.empty_cache()
        except Exception:
            pass
    rec["finished_at"] = datetime.now().isoformat(timespec="seconds")
    rec["seconds"] = round(time.time() - t0, 1)
    (out / "metrics.json").write_text(json.dumps(rec, indent=1), encoding="utf-8")
    print(f"[list{list_no:02d}] {category}: {rec['status']} in {rec['seconds']}s "
          f"(raw {rec.get('raw', {}).get('faces', '-')}f -> "
          f"imp {rec.get('improved', {}).get('faces', '-')}f)", flush=True)
    return rec


def find_image(category, list_no):
    cdir = IMG_DIR / category
    for ext in (".jpg", ".png"):
        p = cdir / f"list{list_no:02d}{ext}"
        if p.exists():
            return p
    return None


def run_list(model, clip, device, list_no):
    t_start = datetime.now().isoformat(timespec="seconds")
    # IFC spot-proof: 2 rotating categories per list -> all 17 covered across 10 lists
    ifc_cats = {CAT_LIST[(2 * (list_no - 1)) % 17], CAT_LIST[(2 * (list_no - 1) + 1) % 17]}
    records = []
    for cat in CAT_LIST:
        img = find_image(cat, list_no)
        if img is None:
            records.append({"category": cat, "list": list_no, "status": "no_image"})
            print(f"[list{list_no:02d}] {cat}: NO IMAGE", flush=True)
            continue
        done = RES_DIR / f"list{list_no:02d}" / cat / "metrics.json"
        if done.exists():
            try:
                old = json.loads(done.read_text(encoding="utf-8"))
                if old.get("status") == "ok":
                    records.append(old)
                    print(f"[list{list_no:02d}] {cat}: cached", flush=True)
                    continue
            except Exception:
                pass
        records.append(process_item(model, clip, device, list_no, cat, img, cat in ifc_cats))
    summary = {"list": list_no, "started_at": t_start,
               "finished_at": datetime.now().isoformat(timespec="seconds"),
               "ok": sum(1 for r in records if r.get("status") == "ok"),
               "failed": sum(1 for r in records if r.get("status") != "ok")}
    ldir = RES_DIR / f"list{list_no:02d}"
    ldir.mkdir(parents=True, exist_ok=True)
    (ldir / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    # refresh the gallery after each completed list so :8000 fills in live
    try:
        subprocess.run([PY, str(HERE / "build_gallery.py")], timeout=120)
    except Exception as e:
        print(f"[gallery] rebuild failed: {e}", flush=True)
    return summary


def parse_lists(spec):
    out = []
    for part in spec.split(","):
        if "-" in part:
            a, b = part.split("-")
            out += list(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--lists", default="1")
    args = ap.parse_args()
    model, clip, device = load_models()
    for n in parse_lists(args.lists):
        print(f"=== LIST {n} ===", flush=True)
        s = run_list(model, clip, device, n)
        print(json.dumps(s), flush=True)
    print("ALL DONE", flush=True)
