"""validate_ifc.py — prove the cloud-generated meshes are BIM/IFC-ready.
Wraps TripoSG meshes in IFC4 via the project's saveIFC, then reopens with ifcopenshell
and checks schema + geometry + entity classes + spatial hierarchy. Run LOCALLY."""
import sys, json
from pathlib import Path
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend" / "python-scripts"))
from saveIFC import save_ifc_project
import ifcopenshell

TG = REPO / "deliverable" / "cloud_results" / "triposg"
objs = [
    {"glbPath": str(TG / "office_chair.glb"), "name": "OfficeChair_TripoSG",
     "ifcClass": "IfcChair", "category": "office_chair", "position": [0, 0, 0], "scale": [1, 1, 1]},
    {"glbPath": str(TG / "table.glb"), "name": "Table_TripoSG",
     "ifcClass": "IfcTable", "category": "table", "position": [2, 0, 0], "scale": [1, 1, 1]},
    {"glbPath": str(TG / "stool.glb"), "name": "Stool_TripoSG",
     "ifcClass": "IfcFurniture", "category": "stool", "position": [4, 0, 0], "scale": [1, 1, 1]},
]
out_ifc = str(REPO / "deliverable" / "cloud_results" / "triposg_validation.ifc")
res = save_ifc_project(objs, out_ifc)
print("EXPORT:", res)

# ---- reopen + validate ------------------------------------------------------
f = ifcopenshell.open(out_ifc)
tfs = f.by_type("IfcTriangulatedFaceSet")
ents = []
for cls in ("IfcFurniture", "IfcFurnishingElement", "IfcChair", "IfcTable"):
    try:  # IfcChair/IfcTable aren't IFC4 entity types — mapped to IfcFurniture on export
        ents += [e.is_a() for e in f.by_type(cls)]
    except Exception:
        pass
hierarchy = bool(f.by_type("IfcProject") and f.by_type("IfcBuildingStorey"))
print(f"SCHEMA: {f.schema}")
print(f"IfcProject: {len(f.by_type('IfcProject'))}  IfcBuildingStorey: {len(f.by_type('IfcBuildingStorey'))}")
print(f"IfcTriangulatedFaceSet (geometry): {len(tfs)}")
print(f"furniture entities: {ents}")
ok = f.schema == "IFC4" and len(tfs) > 0 and hierarchy and len(ents) >= 1
print("RESULT:", "IFC4_BIM_VALIDATION_OK" if ok else "VALIDATION_FAILED")
