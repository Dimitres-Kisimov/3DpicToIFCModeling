"""batch_optimize_test.py — run mesh-cleanup + IFC-optimizer across one example of every item.

For each item: raw mesh -> clean_and_optimize (MESH) -> saveIFC -> optimize_ifc (IFC).
Records before/after for BOTH the mesh and the IFC, so we can print two side-by-side lists.

    python batch_optimize_test.py [model]     # model dir under deliverable/cloud_results (default triposg)
"""
from __future__ import annotations
import sys, os, json, subprocess
import trimesh

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
from clean_and_optimize import clean_mesh, _capture_color, _apply_color
from optimize_ifc import optimize_ifc

ITEMS = ["bed", "bookshelf", "cabinet", "chair", "desk", "lamp",
         "office_chair", "sofa", "stool", "table"]
MODEL = sys.argv[1] if len(sys.argv) > 1 else "triposg"
OUT = os.path.join(REPO, "outputs", "batch_test")
os.makedirs(OUT, exist_ok=True)


def kb(p):
    return os.path.getsize(p) // 1024 if os.path.exists(p) else 0


rows = []
for item in ITEMS:
    src = os.path.join(REPO, "deliverable", "cloud_results", MODEL, f"{item}.glb")
    if not os.path.exists(src):
        continue
    try:
        raw = trimesh.load(src, force="mesh")
        raw_faces = len(raw.faces); raw_kb = kb(src)

        # --- MESH cleanup ---
        color = _capture_color(raw)
        cm, _ = clean_mesh(raw.copy(), target_faces=15000)
        _apply_color(cm, color)
        clean_glb = os.path.join(OUT, f"{item}_clean.glb")
        cm.export(clean_glb)
        clean_faces = len(cm.faces); clean_kb = kb(clean_glb)

        # --- IFC: build raw IFC then optimize it ---
        raw_ifc = os.path.join(OUT, f"{item}.ifc")
        subprocess.run([sys.executable, os.path.join(HERE, "saveIFC.py"), raw_ifc,
                        json.dumps([{"glbPath": src, "name": item, "ifcClass": "IfcFurniture"}])],
                       capture_output=True, text=True, timeout=180)
        raw_ifc_kb = kb(raw_ifc)
        opt_ifc = os.path.join(OUT, f"{item}_opt.ifc")
        rep = optimize_ifc(raw_ifc, opt_ifc, target_faces=15000)
        opt_ifc_kb = kb(opt_ifc)

        rows.append({"item": item, "raw_faces": raw_faces, "clean_faces": clean_faces,
                     "raw_kb": raw_kb, "clean_kb": clean_kb,
                     "raw_ifc_kb": raw_ifc_kb, "opt_ifc_kb": opt_ifc_kb,
                     "ifc_faces_before": rep["before"]["faces"], "ifc_faces_after": rep["after"]["faces"]})
        print(f"  {item:14} mesh {raw_faces:>6}->{clean_faces:<6} f | IFC {raw_ifc_kb:>5}->{opt_ifc_kb:<4} KB", flush=True)
    except Exception as e:
        print(f"  {item:14} ERROR: {e}", flush=True)

json.dump({"model": MODEL, "rows": rows}, open(os.path.join(OUT, "results.json"), "w"), indent=2)
print("\nDONE ->", os.path.join(OUT, "results.json"))
