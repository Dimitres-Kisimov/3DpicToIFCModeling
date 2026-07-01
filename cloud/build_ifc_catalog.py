"""build_ifc_catalog.py — export the generated furniture meshes as a decimated, IFC4 BIM catalog.

Pick the source per item: a specific model, or 'best' = the highest-F-score model for that item
(from cloud_scores.csv) — the benchmark's finding is that no single model wins every category, so
'best' gives the strongest possible catalog.

Each mesh is: (1) DECIMATED to a BIM-practical face budget (raw meshes are 150k-2.7M faces => multi-100 MB
IFC; Finding B); (2) ORIENTED to Z-up (IFC/BIM convention) reusing the gallery's front-facing pose; and
(3) REAL-WORLD SCALED so its height matches a typical furniture dimension in metres. Then laid out in a
grid and written as IFC4 (IfcTriangulatedFaceSet + IfcFurniture/IfcChair + full Project/Site/Building/
Storey hierarchy), re-opened with ifcopenshell, and validated. STANDALONE catalog — loads in Revit/
ArchiCAD, independent of the ABO data.

CAVEAT (printed X x Y x Z dims are the check): generated meshes aren't perfectly canonically oriented
(Finding A), so the Z-up + height-scale normalization is BEST-EFFORT — most items land at sensible
real-world sizes, but a few (esp. flat/elongated pieces where height isn't the defining dimension) may
come out mis-sized and need a manual orientation/scale nudge. Use --no-realworld for raw unit scale.

  python cloud/build_ifc_catalog.py                        # best-of-each, real-world m, every item
  python cloud/build_ifc_catalog.py --model triposg        # all from TripoSG (best overall, MIT)
  python cloud/build_ifc_catalog.py --model sam3d --items table,office_chair,cabinet,stool
  python cloud/build_ifc_catalog.py --faces 5000 --spacing 2.0 --no-realworld
"""
import sys, os, csv, argparse, math
from pathlib import Path
import trimesh
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend" / "python-scripts"))
from saveIFC import save_ifc_project
import ifcopenshell

CLOUD = REPO / "deliverable" / "cloud_results"
ASSETS = REPO / "deliverable" / "cloud_gallery" / "assets"   # front-facing, decimated gallery copies
SCORES = REPO / "deliverable" / "cloud_gallery" / "cloud_scores.csv"
BIM = CLOUD / "_bim_catalog"

# IFC4 has no IfcTable/IfcStool; chairs map to IfcChair, everything else to the generic IfcFurniture.
IFC_CLASS = {"office_chair": "IfcChair", "chair": "IfcChair"}

# Caveat 2 fixes (real-world use):
# ORIENTATION — the gallery/asset copies are front-facing in model-viewer's Y-up frame; IFC/BIM is Z-up,
# so rotate +90deg about X (Y-up -> Z-up). This reuses the orientation you already approved in the gallery.
# NOTE: per Finding A, generated meshes aren't perfectly canonically oriented, so this is a best-effort
# normalization — a few items may still need a manual nudge; the printed X x Y x Z dims are the check.
import trimesh.transformations as _tf
from math import radians
RX_Z_UP = _tf.rotation_matrix(radians(90), [1, 0, 0])
# REAL-WORLD SCALE — generators output unit-normalized meshes; scale each so its height (Z after Z-up)
# matches a typical real furniture dimension in METRES, so the IFC lands at real size in Revit.
REAL_HEIGHT_M = {"bed": 0.55, "bookshelf": 1.90, "cabinet": 1.20, "chair": 0.90, "desk": 0.75,
                 "lamp": 1.55, "office_chair": 1.10, "sofa": 0.85, "stool": 0.60, "table": 0.75}


def best_model_per_item():
    """Highest-F-score generator for each item, among models actually present in cloud_results/
    (TripoSR ran locally, so it isn't a source here — 'best' means best available cloud model)."""
    available = {d.name for d in CLOUD.iterdir() if d.is_dir() and d.name != "_bim_catalog"}
    best = {}
    with open(SCORES, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            k, m, s = r["key"], r["model"], float(r["fscore"])
            if m == "abo_gt" or m not in available:
                continue
            if k not in best or s > best[k][1]:
                best[k] = (m, s)
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="best", help="'best' (per-item winner) or a model dir name (triposg, sam3d, trellis, instantmesh, triposr_rembg, triposr_sam2)")
    ap.add_argument("--items", default="", help="comma-separated item keys; default = all available")
    ap.add_argument("--faces", type=int, default=8000, help="decimation target per item (BIM-practical ~5-8k)")
    ap.add_argument("--spacing", type=float, default=1.5, help="grid spacing in metres")
    ap.add_argument("--no-realworld", action="store_true", help="skip Z-up orientation + real-world metre scaling (keep raw unit-scale)")
    ap.add_argument("--out", default=str(BIM / "furniture_catalog.ifc"))
    args = ap.parse_args()
    BIM.mkdir(parents=True, exist_ok=True)

    best = best_model_per_item()
    all_items = sorted(best.keys())
    items = [i.strip() for i in args.items.split(",") if i.strip()] or all_items

    # resolve (item -> source glb): prefer the front-facing gallery copy (already oriented + decimated),
    # fall back to the raw cloud output.
    picks = []
    for it in items:
        model = best[it][0] if args.model == "best" else args.model
        glb = ASSETS / f"{it}_{model}.glb"
        if not glb.exists():
            glb = CLOUD / model / f"{it}.glb"
        if not glb.exists():
            print(f"  skip {it}: no mesh for {model}/{it}"); continue
        picks.append((it, model, glb, best.get(it, (None, 0))[1]))
    if not picks:
        print("no items to export"); return

    # grid layout (a 'population')
    cols = max(1, int(math.ceil(math.sqrt(len(picks)))))
    objects = []
    for idx, (it, model, glb, fscore) in enumerate(picks):
        row, col = divmod(idx, cols)
        pos = [col * args.spacing, -row * args.spacing, 0.0]
        m = trimesh.load(str(glb), force="mesh")
        before = len(m.faces)
        if not args.no_realworld:
            m.apply_transform(RX_Z_UP)                                  # -> Z-up (IFC/BIM)
            h = float(m.extents[2])
            if h > 1e-6:
                m.apply_scale(REAL_HEIGHT_M.get(it, 1.0) / h)           # -> real-world height in metres
            c = m.bounds.mean(axis=0)
            m.apply_translation([-c[0], -c[1], -float(m.bounds[0][2])])  # centre in XY, base on floor (z=0)
        if before > args.faces:
            m = m.simplify_quadric_decimation(face_count=args.faces)
        dec = BIM / f"{it}_{model}_bim.glb"
        m.export(dec)
        dx, dy, dz = (float(v) for v in m.extents)
        cls = IFC_CLASS.get(it, "IfcFurniture")
        print(f"  {it:14} <- {model:13} F={fscore:.2f}  {before:>7}->{len(m.faces):>5} f  "
              f"{dx:.2f}x{dy:.2f}x{dz:.2f} m  {cls}")
        objects.append({"glbPath": str(dec), "name": f"{it.title()}_{model}",
                        "ifcClass": cls, "category": it, "position": pos, "scale": [1, 1, 1]})

    res = save_ifc_project(objects, args.out)
    print("\nEXPORT:", res)

    f = ifcopenshell.open(args.out)
    tfs = f.by_type("IfcTriangulatedFaceSet")
    furn = set(e.GlobalId for e in (f.by_type("IfcFurniture") + f.by_type("IfcFurnishingElement")))
    hierarchy = bool(f.by_type("IfcProject") and f.by_type("IfcBuildingStorey"))
    size_kb = os.path.getsize(args.out) // 1024
    print(f"SCHEMA {f.schema} | Project/Site/Building/Storey hierarchy: {hierarchy}")
    print(f"furniture elements: {len(furn)} | geometry bodies (IfcTriangulatedFaceSet): {len(tfs)} | {size_kb} KB")
    ok = f.schema == "IFC4" and len(tfs) >= len(objects) and hierarchy and len(furn) >= len(objects)
    print("RESULT:", "IFC4_BIM_CATALOG_OK" if ok else "VALIDATION_FAILED")
    print("wrote:", args.out)


if __name__ == "__main__":
    main()
