"""
build_room_ifc.py — turn the object table (schedule.json) into a real IFC/BIM file.

Reads <out_dir>/schedule.json (from build_room_scene.py) and writes
<out_dir>/scene.ifc: IfcProject → IfcSite → IfcBuilding → IfcBuildingStorey →
IfcSpace (the room), with each table row as its mapped IFC furniture entity,
placed at the solver coordinates, carrying a Pset with real dimensions + source
+ licence. Body geometry lives in scene.glb/scene.xkt; this file carries the BIM
semantics (types, placement, properties) that IFC exists for.

Note: IFC4 has no IfcChair/IfcTable entity — those map to IfcFurniture with the
intended class kept as ObjectType. Everything is guarded so one bad row can't
abort the export.

Usage: python build_room_ifc.py <out_dir>
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import ifcopenshell
import ifcopenshell.api.root
import ifcopenshell.api.unit
import ifcopenshell.api.context
import ifcopenshell.api.project
import ifcopenshell.api.aggregate

try:
    import ifcopenshell.api.spatial
    _HAVE_SPATIAL = True
except Exception:
    _HAVE_SPATIAL = False
try:
    import ifcopenshell.api.pset
    _HAVE_PSET = True
except Exception:
    _HAVE_PSET = False
try:
    import ifcopenshell.api.group
    _HAVE_GROUP = True
except Exception:
    _HAVE_GROUP = False


def _placement(model, x, y, z, angle_deg):
    pt = model.create_entity("IfcCartesianPoint", Coordinates=(float(x), float(y), float(z)))
    a = math.radians(angle_deg or 0.0)
    refdir = model.create_entity("IfcDirection", DirectionRatios=(math.cos(a), math.sin(a), 0.0))
    zdir = model.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0))
    axis = model.create_entity("IfcAxis2Placement3D", Location=pt, Axis=zdir, RefDirection=refdir)
    return model.create_entity("IfcLocalPlacement", RelativePlacement=axis)


def _contain(model, ent, structure):
    if not _HAVE_SPATIAL:
        return
    for kwargs in ({"products": [ent]}, {"product": ent}):
        try:
            ifcopenshell.api.spatial.assign_container(model, relating_structure=structure, **kwargs)
            return
        except Exception:
            continue


def build(out_dir: Path) -> dict:
    sched = json.loads((out_dir / "schedule.json").read_text(encoding="utf-8"))
    room = sched["room"]
    items = sched["items"]

    model = ifcopenshell.api.project.create_file()
    project = ifcopenshell.api.root.create_entity(model, ifc_class="IfcProject", name="SCS Room")
    ifcopenshell.api.unit.assign_unit(model)
    ifcopenshell.api.context.add_context(model, context_type="Model")

    site = ifcopenshell.api.root.create_entity(model, ifc_class="IfcSite", name="Site")
    building = ifcopenshell.api.root.create_entity(model, ifc_class="IfcBuilding", name="Building")
    storey = ifcopenshell.api.root.create_entity(model, ifc_class="IfcBuildingStorey", name="Ground Floor")
    space = ifcopenshell.api.root.create_entity(model, ifc_class="IfcSpace", name=room.get("name", "Room"))
    for rel, prods in ((project, [site]), (site, [building]), (building, [storey]), (storey, [space])):
        try:
            ifcopenshell.api.aggregate.assign_object(model, relating_object=rel, products=prods)
        except Exception:
            pass

    made = 0
    ents_by_id = {}
    for it in items:
        try:
            ifc_class = it.get("ifc_class", "IfcFurnishingElement")
            try:
                ent = ifcopenshell.api.root.create_entity(model, ifc_class=ifc_class, name=it["name"])
            except Exception:
                ent = ifcopenshell.api.root.create_entity(model, ifc_class="IfcFurniture", name=it["name"])
                try:
                    ent.ObjectType = ifc_class
                except Exception:
                    pass
            # IFC is Z-up: solver (x=width, z=depth) -> IFC (X=x, Y=z, Z=0)
            ent.ObjectPlacement = _placement(model, it["x"], it["z"], 0.0, it.get("rotation_deg", 0))
            _contain(model, ent, space)
            if _HAVE_PSET:
                try:
                    ps = ifcopenshell.api.pset.add_pset(model, product=ent, name="Pset_SCS_Object")
                    props = {
                        "Category": it.get("category", ""),
                        "Width": float(it["width_m"]), "Depth": float(it["depth_m"]), "Height": float(it["height_m"]),
                        "PositionX": float(it["x"]), "PositionZ": float(it["z"]),
                        "RotationDeg": float(it.get("rotation_deg", 0)),
                        "Source": it.get("source", ""), "License": it.get("license", ""),
                    }
                    # A6 — functional relationship survives into BIM (was dropped before)
                    if it.get("anchor_to"):
                        props["FunctionalAnchor"] = str(it["anchor_to"])
                        props["FunctionalRelation"] = str(it.get("relation") or "in_front")
                    ifcopenshell.api.pset.edit_pset(model, pset=ps, properties=props)
                except Exception:
                    pass
            ents_by_id[it["id"]] = ent
            made += 1
        except Exception as exc:
            print(f"[build_room_ifc] skipped {it.get('id')}: {exc}", file=sys.stderr)

    # A6 — one IfcGroup per functional cluster (desk + its chair/monitor/lamp), so
    # downstream BIM tools see the workstation as a unit, not loose furniture.
    groups = 0
    clusters = {}
    for it in items:
        if it.get("anchor_to") and it["anchor_to"] in ents_by_id and it["id"] in ents_by_id:
            clusters.setdefault(it["anchor_to"], []).append(it["id"])
    for parent_id, child_ids in clusters.items():
        if not _HAVE_GROUP:
            break
        try:
            grp = ifcopenshell.api.group.add_group(model, name=f"Workstation:{parent_id}")
            ifcopenshell.api.group.assign_group(
                model, products=[ents_by_id[parent_id]] + [ents_by_id[c] for c in child_ids], group=grp)
            groups += 1
        except Exception as exc:
            print(f"[build_room_ifc] group skipped for {parent_id}: {exc}", file=sys.stderr)

    out = out_dir / "scene.ifc"
    model.write(str(out))
    return {"success": True, "ifc": str(out), "entities": made, "groups": groups,
            "bytes": out.stat().st_size}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"success": False, "error": "Usage: build_room_ifc.py <out_dir>"}))
        sys.exit(1)
    try:
        print(json.dumps(build(Path(sys.argv[1]))))
    except Exception as exc:
        import traceback
        print(json.dumps({"success": False, "error": str(exc), "traceback": traceback.format_exc()}))
        sys.exit(1)
