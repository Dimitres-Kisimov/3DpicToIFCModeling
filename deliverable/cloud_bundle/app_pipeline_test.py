"""
app_pipeline_test.py — "does the APP's machinery work with each AI's output?"

For every generated mesh out/<model>/<key>.glb, run the app's post-generation
pipeline exactly as the product would: archetype repair packs -> mesh-geometry
IFC4 export (saveIFC, the app's real exporter) -> stats. This answers "what works
and what doesn't with the other AIs inside the app" WITHOUT the app's engine
selector existing yet (that lands after this run).

Run on the pod from the repo root (needs the repo clone next to the bundle):

    python app_pipeline_test.py out/ apptest/ --repo /workspace/3DpicToIFCModeling

Writes apptest/<model>/<key>.{repaired.glb,ifc} + apptest/report.csv
"""
from __future__ import annotations
import os, sys, csv, json, argparse, traceback
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("outdir")                      # out/ with per-model mesh dirs
ap.add_argument("dest")                        # apptest/
ap.add_argument("--repo", default="/workspace/3DpicToIFCModeling")
args = ap.parse_args()

sys.path.insert(0, str(Path(args.repo) / "backend" / "python-scripts"))
import trimesh
from repair_packs import repair_mesh
import saveIFC

# manifest key -> the app's category vocabulary
KEY_CATEGORY = {"bed": "bed", "bookshelf": "bookshelf", "cabinet": "cabinet",
                "chair": "chair", "desk": "desk", "lamp": "lamp",
                "office_chair": "office_chair", "sofa": "sofa",
                "stool": "stool", "table": "table"}

outdir, dest = Path(args.outdir), Path(args.dest)
rows = []
for model_dir in sorted(p for p in outdir.iterdir() if p.is_dir()):
    model = model_dir.name
    for glb in sorted(model_dir.glob("*.glb")):
        key = glb.stem
        cat = KEY_CATEGORY.get(key, key)
        d = dest / model
        d.mkdir(parents=True, exist_ok=True)
        row = {"model": model, "item": key, "repair": "", "ifc": "", "error": ""}
        try:
            m = trimesh.load(glb, force="mesh")
            faces_in = len(m.faces)
            m, rep = repair_mesh(m, label=cat)
            rglb = d / f"{key}.repaired.glb"
            m.export(rglb)
            row["repair"] = f"ok {faces_in}->{len(m.faces)}f " \
                            f"{'wt' if all(p.is_watertight for p in m.split(only_watertight=False)) else 'open'}"
            ifc_path = d / f"{key}.ifc"
            saveIFC.save_ifc_project([{"glbPath": str(rglb), "name": key,
                                       "category": cat, "ifc_class": "IfcFurniture"}],
                                     str(ifc_path))
            ok = ifc_path.exists() and ifc_path.stat().st_size > 5000
            row["ifc"] = f"ok {ifc_path.stat().st_size // 1024}KB" if ok else "too small"
        except Exception as e:
            row["error"] = f"{type(e).__name__}: {e}"
            traceback.print_exc()
        rows.append(row)
        print(f"[apptest] {model}/{key}: repair={row['repair'] or '-'} ifc={row['ifc'] or '-'} {row['error']}",
              flush=True)

dest.mkdir(parents=True, exist_ok=True)
with open(dest / "report.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["model", "item", "repair", "ifc", "error"])
    w.writeheader(); w.writerows(rows)
ok_n = sum(1 for r in rows if r["ifc"].startswith("ok"))
print(f"[apptest] DONE: {ok_n}/{len(rows)} meshes survived repair+IFC — report.csv written", flush=True)
