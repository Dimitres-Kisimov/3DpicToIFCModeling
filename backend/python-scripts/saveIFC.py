"""
saveIFC.py - Phase 6 (real geometry)
Exports scene objects (GLB meshes) to a valid IFC4 file using ifcopenshell.
Each object becomes an IfcFurnishingElement with IfcTriangulatedFaceSet geometry.
"""

import json
import sys
import os
import math
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from inference_base import log, error_exit, success_exit


# ─── IFC project skeleton ─────────────────────────────────────────────────────

def _make_project(ifc):
    """Create the mandatory IFC project hierarchy and return helpers."""
    import ifcopenshell
    import ifcopenshell.api
    import ifcopenshell.util.element

    o = ifc.createIfcOrganization()
    o.Name = "Generated"
    p = ifc.createIfcPerson()
    p.FamilyName = "User"
    pa = ifc.createIfcPersonAndOrganization(ThePerson=p, TheOrganization=o)
    app = ifc.createIfcApplication(ApplicationDeveloper=o,
                                   Version="1.0",
                                   ApplicationFullName="3DpicToIFC",
                                   ApplicationIdentifier="3DpicToIFC")
    now = int(__import__("time").time())
    owner_history = ifc.createIfcOwnerHistory(
        OwningUser=pa,
        OwningApplication=app,
        State="READWRITE",
        ChangeAction="ADDED",
        CreationDate=now,
    )

    # Geometric contexts
    world_origin = ifc.createIfcCartesianPoint(Coordinates=(0.0, 0.0, 0.0))
    z_axis = ifc.createIfcDirection(DirectionRatios=(0.0, 0.0, 1.0))
    x_axis = ifc.createIfcDirection(DirectionRatios=(1.0, 0.0, 0.0))
    placement_3d = ifc.createIfcAxis2Placement3D(
        Location=world_origin, Axis=z_axis, RefDirection=x_axis
    )
    body_ctx = ifc.createIfcGeometricRepresentationContext(
        ContextType="Model",
        CoordinateSpaceDimension=3,
        Precision=0.00001,
        WorldCoordinateSystem=placement_3d,
    )
    body_sub = ifc.createIfcGeometricRepresentationSubContext(
        ContextIdentifier="Body",
        ContextType="Model",
        ParentContext=body_ctx,
        TargetView="MODEL_VIEW",
    )

    # Project / Site / Building / Storey
    proj = ifc.createIfcProject(
        GlobalId=ifcopenshell.guid.new(),
        OwnerHistory=owner_history,
        Name="GeneratedScene",
        UnitsInContext=ifc.createIfcUnitAssignment(
            Units=[ifc.createIfcSIUnit(UnitType="LENGTHUNIT", Name="METRE")]
        ),
        RepresentationContexts=[body_ctx],
    )
    site = ifc.createIfcSite(
        GlobalId=ifcopenshell.guid.new(),
        OwnerHistory=owner_history,
        Name="Site",
        ObjectPlacement=ifc.createIfcLocalPlacement(
            RelativePlacement=placement_3d
        ),
    )
    building = ifc.createIfcBuilding(
        GlobalId=ifcopenshell.guid.new(),
        OwnerHistory=owner_history,
        Name="Building",
        ObjectPlacement=ifc.createIfcLocalPlacement(
            PlacementRelTo=site.ObjectPlacement,
            RelativePlacement=ifc.createIfcAxis2Placement3D(
                Location=ifc.createIfcCartesianPoint(Coordinates=(0.0, 0.0, 0.0))
            ),
        ),
    )
    storey = ifc.createIfcBuildingStorey(
        GlobalId=ifcopenshell.guid.new(),
        OwnerHistory=owner_history,
        Name="Ground Floor",
        Elevation=0.0,
        ObjectPlacement=ifc.createIfcLocalPlacement(
            PlacementRelTo=building.ObjectPlacement,
            RelativePlacement=ifc.createIfcAxis2Placement3D(
                Location=ifc.createIfcCartesianPoint(Coordinates=(0.0, 0.0, 0.0))
            ),
        ),
    )

    # Aggregate
    ifc.createIfcRelAggregates(
        GlobalId=ifcopenshell.guid.new(),
        OwnerHistory=owner_history,
        RelatingObject=proj,
        RelatedObjects=[site],
    )
    ifc.createIfcRelAggregates(
        GlobalId=ifcopenshell.guid.new(),
        OwnerHistory=owner_history,
        RelatingObject=site,
        RelatedObjects=[building],
    )
    ifc.createIfcRelAggregates(
        GlobalId=ifcopenshell.guid.new(),
        OwnerHistory=owner_history,
        RelatingObject=building,
        RelatedObjects=[storey],
    )

    return owner_history, body_sub, storey


# ─── Geometry helpers ─────────────────────────────────────────────────────────

def _mat3_from_rotation_euler(rx, ry, rz):
    """Build a 3x3 rotation matrix from XYZ Euler angles (radians)."""
    cx, sx = math.cos(rx), math.sin(rx)
    cy, sy = math.cos(ry), math.sin(ry)
    cz, sz = math.cos(rz), math.sin(rz)
    # ZYX convention
    return [
        [cy*cz,              cy*sz,              -sy   ],
        [sx*sy*cz - cx*sz,   sx*sy*sz + cx*cz,   sx*cy ],
        [cx*sy*cz + sx*sz,   cx*sy*sz - sx*cz,   cx*cy ],
    ]


def _add_furniture(ifc, owner_history, body_ctx, storey, mesh, name, obj_id,
                   position, rotation, scale):
    """Add a single IfcFurnishingElement with real mesh geometry."""
    import ifcopenshell
    import numpy as np

    # ── Apply scale then rotation to vertices ─────────────────────────────────
    verts = mesh.vertices.copy().astype(float)
    verts *= scale  # broadcast [sx, sy, sz]

    rx, ry, rz = [math.radians(a) for a in rotation]
    R = _mat3_from_rotation_euler(rx, ry, rz)
    verts = verts @ [[R[0][0], R[1][0], R[2][0]],
                     [R[0][1], R[1][1], R[2][1]],
                     [R[0][2], R[1][2], R[2][2]]]

    # IFC coords: metres, Y-up matches xeokit world
    ifc_coords = [tuple(float(v) for v in row) for row in verts]
    ifc_faces  = [((int(f[0])+1, int(f[1])+1, int(f[2])+1),) for f in mesh.faces]

    coord_list = ifc.createIfcCartesianPointList3D(CoordList=ifc_coords)
    face_set   = ifc.createIfcTriangulatedFaceSet(
        Coordinates=coord_list,
        CoordIndex=ifc_faces,
        Closed=False,
    )

    shape_rep = ifc.createIfcShapeRepresentation(
        ContextOfItems=body_ctx,
        RepresentationIdentifier="Body",
        RepresentationType="Tessellation",
        Items=[face_set],
    )
    prod_def = ifc.createIfcProductDefinitionShape(Representations=[shape_rep])

    # Placement at object position
    loc = ifc.createIfcCartesianPoint(
        Coordinates=(float(position[0]), float(position[1]), float(position[2]))
    )
    obj_placement = ifc.createIfcLocalPlacement(
        PlacementRelTo=storey.ObjectPlacement,
        RelativePlacement=ifc.createIfcAxis2Placement3D(Location=loc),
    )

    element = ifc.createIfcFurnishingElement(
        GlobalId=ifcopenshell.guid.new(),
        OwnerHistory=owner_history,
        Name=name,
        Tag=obj_id,
        ObjectPlacement=obj_placement,
        Representation=prod_def,
    )

    ifc.createIfcRelContainedInSpatialStructure(
        GlobalId=ifcopenshell.guid.new(),
        OwnerHistory=owner_history,
        RelatingStructure=storey,
        RelatedElements=[element],
    )

    return element


# ─── Main export ──────────────────────────────────────────────────────────────

def save_ifc_project(objects_list, output_ifc):
    try:
        import ifcopenshell
        import trimesh
        import numpy as np
    except ImportError as e:
        error_exit(f"Missing dependency: {e}. Install: pip install ifcopenshell trimesh")

    log(f"Saving IFC project with {len(objects_list)} objects", "info")
    log(f"Output: {output_ifc}", "info")

    ifc = ifcopenshell.file(schema="IFC4")
    owner_history, body_ctx, storey = _make_project(ifc)

    exported = 0
    for obj in objects_list:
        glb_path = obj.get("glbPath") or obj.get("glbUrl", "")
        if not glb_path:
            log(f"Object {obj.get('id')} has no glbPath — skipped", "warn")
            continue

        # Resolve relative /outputs/ URLs to filesystem path
        if glb_path.startswith("/outputs/"):
            glb_path = os.path.join(".", "outputs", os.path.basename(glb_path))

        if not os.path.exists(glb_path):
            log(f"GLB not found: {glb_path} — skipped", "warn")
            continue

        try:
            scene = trimesh.load(glb_path, force="scene")
            mesh = trimesh.util.concatenate(
                [g for g in scene.geometry.values()]
            ) if hasattr(scene, "geometry") else scene
        except Exception as e:
            log(f"Could not load {glb_path}: {e} — skipped", "warn")
            continue

        # Decimate to ≤8000 faces for IFC file size
        if len(mesh.faces) > 8000:
            ratio = 8000 / len(mesh.faces)
            mesh = mesh.simplify_quadric_decimation(int(len(mesh.faces) * ratio))
            log(f"Decimated to {len(mesh.faces)} faces", "info")

        name     = obj.get("name", "Furniture")
        obj_id   = str(obj.get("id", "unknown"))
        position = obj.get("position", [0, 0, 0]) or [0, 0, 0]
        rotation = obj.get("rotation", [0, 0, 0]) or [0, 0, 0]
        scale_v  = obj.get("scale",    [1, 1, 1]) or [1, 1, 1]

        _add_furniture(ifc, owner_history, body_ctx, storey,
                       mesh, name, obj_id, position, rotation, scale_v)
        exported += 1
        log(f"Added: {name} ({len(mesh.faces)} faces)", "info")

    if exported == 0:
        error_exit("No objects with valid GLB meshes were exported")

    ifc.write(output_ifc)
    ifc_size = os.path.getsize(output_ifc)
    log(f"IFC4 saved: {ifc_size} bytes, {exported} objects", "info")

    return {
        "status": "saved",
        "project_path": output_ifc,
        "ifc_size_bytes": ifc_size,
        "object_count": exported,
        "schema": "IFC4",
    }


if __name__ == "__main__":
    if len(sys.argv) < 3:
        error_exit("Usage: saveIFC.py <output_ifc> <objects_json_array>")

    output_ifc = sys.argv[1]

    try:
        objects_list = json.loads(sys.argv[2])
        if not isinstance(objects_list, list):
            objects_list = [objects_list]
    except json.JSONDecodeError as e:
        error_exit(f"Invalid JSON: {e}")

    result = save_ifc_project(objects_list, output_ifc)
    success_exit(result)
