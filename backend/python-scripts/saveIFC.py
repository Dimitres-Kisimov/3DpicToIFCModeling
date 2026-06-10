"""
Save IFC — real ifcopenshell IFC4 export with actual mesh geometry.
Loads each object's GLB, extracts mesh, writes IfcTriangulatedFaceSet.
"""

import json
import sys
import os
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from inference_base import log, error_exit, success_exit


def _make_project(ifc):
    """Create the standard IFC4 project hierarchy and return key entities."""
    import ifcopenshell
    import ifcopenshell.guid as guid

    org = ifc.createIfcOrganization(Name="3DPicToIFC")
    person = ifc.createIfcPerson(FamilyName="User")
    person_org = ifc.createIfcPersonAndOrganization(ThePerson=person, TheOrganization=org)
    app = ifc.createIfcApplication(
        ApplicationDeveloper=org, Version="1.0",
        ApplicationFullName="3DPicToIFC", ApplicationIdentifier="3DPicToIFC"
    )
    owner_history = ifc.createIfcOwnerHistory(
        OwningUser=person_org, OwningApplication=app,
        ChangeAction="ADDED", CreationDate=int(time.time())
    )
    unit_assignment = ifc.createIfcUnitAssignment(Units=[
        ifc.createIfcSIUnit(UnitType="LENGTHUNIT", Name="METRE"),
        ifc.createIfcSIUnit(UnitType="AREAUNIT", Name="SQUARE_METRE"),
        ifc.createIfcSIUnit(UnitType="VOLUMEUNIT", Name="CUBIC_METRE"),
        ifc.createIfcSIUnit(UnitType="PLANEANGLEUNIT", Name="RADIAN"),
    ])
    origin_pt = ifc.createIfcCartesianPoint((0., 0., 0.))
    z_dir = ifc.createIfcDirection((0., 0., 1.))
    x_dir = ifc.createIfcDirection((1., 0., 0.))
    world_axes = ifc.createIfcAxis2Placement3D(Location=origin_pt, Axis=z_dir, RefDirection=x_dir)
    world_ctx = ifc.createIfcGeometricRepresentationContext(
        ContextType="Model", CoordinateSpaceDimension=3,
        Precision=1e-5, WorldCoordinateSystem=world_axes
    )
    body_ctx = ifc.createIfcGeometricRepresentationSubContext(
        ContextIdentifier="Body", ContextType="Model",
        ParentContext=world_ctx, TargetView="MODEL_VIEW"
    )
    project = ifc.createIfcProject(
        GlobalId=guid.new(), OwnerHistory=owner_history,
        Name="Office Project",
        UnitsInContext=unit_assignment,
        RepresentationContexts=[world_ctx]
    )
    origin_placement = ifc.createIfcAxis2Placement3D(
        Location=origin_pt, Axis=z_dir, RefDirection=x_dir
    )
    site = ifc.createIfcSite(
        GlobalId=guid.new(), OwnerHistory=owner_history, Name="Site",
        ObjectPlacement=ifc.createIfcLocalPlacement(RelativePlacement=origin_placement),
        CompositionType="ELEMENT"
    )
    building = ifc.createIfcBuilding(
        GlobalId=guid.new(), OwnerHistory=owner_history, Name="Building",
        ObjectPlacement=ifc.createIfcLocalPlacement(
            PlacementRelTo=site.ObjectPlacement, RelativePlacement=origin_placement
        ),
        CompositionType="ELEMENT"
    )
    storey = ifc.createIfcBuildingStorey(
        GlobalId=guid.new(), OwnerHistory=owner_history, Name="Ground Floor",
        ObjectPlacement=ifc.createIfcLocalPlacement(
            PlacementRelTo=building.ObjectPlacement, RelativePlacement=origin_placement
        ),
        CompositionType="ELEMENT", Elevation=0.
    )
    ifc.createIfcRelAggregates(
        GlobalId=guid.new(), OwnerHistory=owner_history,
        RelatingObject=project, RelatedObjects=[site]
    )
    ifc.createIfcRelAggregates(
        GlobalId=guid.new(), OwnerHistory=owner_history,
        RelatingObject=site, RelatedObjects=[building]
    )
    ifc.createIfcRelAggregates(
        GlobalId=guid.new(), OwnerHistory=owner_history,
        RelatingObject=building, RelatedObjects=[storey]
    )
    return owner_history, body_ctx, storey


# Map the per-category IFC labels the pipeline emits to entities that exist
# in plain IFC4 (base) — IfcChair/IfcTable/IfcDesk were only added in IFC4.3,
# so for maximum BIM-tool compatibility we instantiate IfcFurniture and stamp
# the canonical class name into ObjectType. Revit and BIM Vision schedule
# correctly off ObjectType, which is the standard IFC4 pattern.
IFC4_FALLBACK_ENTITY = "IfcFurniture"

IFC4_ENTITY_MAP = {
    "IfcFurniture":               ("IfcFurniture",             None),
    "IfcChair":                   ("IfcFurniture",             "Chair"),
    "IfcTable":                   ("IfcFurniture",             "Table"),
    "IfcDesk":                    ("IfcFurniture",             "Desk"),
    "IfcSystemFurnitureElement":  ("IfcSystemFurnitureElement",None),
    "IfcFurnishingElement":       ("IfcFurnishingElement",     None),
    "IfcAudioVisualAppliance":    ("IfcAudioVisualAppliance",  None),
    "IfcCommunicationsAppliance": ("IfcCommunicationsAppliance", None),
    "IfcInputDevice":             ("IfcCommunicationsAppliance", "InputDevice"),
    "IfcElectricAppliance":       ("IfcElectricAppliance",     None),
    "IfcSanitaryTerminal":        ("IfcSanitaryTerminal",      None),
}


def _add_furniture(ifc, owner_history, body_ctx, storey, mesh, name, position, scale,
                    ifc_class="IfcFurniture", category=None, dimensions=None):
    """Add one furniture item with real triangulated mesh geometry.

    ifc_class is the IFC4 entity type to instantiate (IfcChair, IfcTable, ...).
    If the requested class is unknown, falls back to IfcFurnishingElement.
    Adds a Pset_FurnitureCommon property set with the SCS category and
    measured dimensions when supplied."""
    import ifcopenshell
    import ifcopenshell.guid as guid
    import numpy as np

    # Decimate if too heavy — IFC readers struggle above ~8000 faces
    if len(mesh.faces) > 8000:
        try:
            mesh = mesh.simplify_quadric_decimation(8000)
        except Exception:
            pass

    # Apply scale transform
    sx, sy, sz = (scale or [1, 1, 1])
    mesh = mesh.copy()
    mesh.apply_scale([sx, sy, sz])

    verts = mesh.vertices.tolist()
    faces = (mesh.faces + 1).tolist()  # IFC is 1-indexed

    coord_list = ifc.createIfcCartesianPointList3D(
        [tuple(round(float(v), 6) for v in pt) for pt in verts]
    )
    tri_face_set = ifc.createIfcTriangulatedFaceSet(
        Coordinates=coord_list,
        Normals=None,
        Closed=False,
        CoordIndex=[tuple(int(i) for i in f) for f in faces]
    )
    shape_rep = ifc.createIfcShapeRepresentation(
        ContextOfItems=body_ctx,
        RepresentationIdentifier="Body",
        RepresentationType="Tessellation",
        Items=[tri_face_set]
    )
    product_shape = ifc.createIfcProductDefinitionShape(Representations=[shape_rep])

    px, py, pz = (position or [0, 0, 0])
    loc = ifc.createIfcCartesianPoint((float(px), float(py), float(pz)))
    placement = ifc.createIfcLocalPlacement(
        RelativePlacement=ifc.createIfcAxis2Placement3D(Location=loc)
    )

    # Pick the entity class and the ObjectType label (canonical class name
    # for the BIM scheduler when the entity itself is generic IfcFurniture).
    cls, object_type = IFC4_ENTITY_MAP.get(ifc_class, (IFC4_FALLBACK_ENTITY, None))
    factory = getattr(ifc, f"create{cls}", None)
    if factory is None:
        cls = IFC4_FALLBACK_ENTITY
        object_type = None
        factory = getattr(ifc, f"create{cls}")

    kwargs = dict(
        GlobalId=guid.new(),
        OwnerHistory=owner_history,
        Name=str(name),
        ObjectPlacement=placement,
        Representation=product_shape,
    )
    if object_type:
        kwargs["ObjectType"] = object_type
    try:
        furniture = factory(**kwargs)
    except Exception:
        # Some IFC4 entities don't accept ObjectType in the positional signature
        kwargs.pop("ObjectType", None)
        furniture = factory(**kwargs)
    ifc.createIfcRelContainedInSpatialStructure(
        GlobalId=guid.new(),
        OwnerHistory=owner_history,
        RelatedElements=[furniture],
        RelatingStructure=storey
    )

    # Attach Pset_FurnitureCommon with SCS-specific properties and measured
    # dimensions so they survive into Revit/BIM Vision schedules.
    if dimensions or category:
        props = []
        if category:
            props.append(ifc.createIfcPropertySingleValue(
                Name="Category", NominalValue=ifc.createIfcText(str(category))
            ))
        if dimensions:
            for key in ("height", "width", "depth"):
                if dimensions.get(key) is not None:
                    props.append(ifc.createIfcPropertySingleValue(
                        Name=f"Measured_{key.capitalize()}_m",
                        NominalValue=ifc.createIfcReal(float(dimensions[key]))
                    ))
        if props:
            pset = ifc.createIfcPropertySet(
                GlobalId=guid.new(), OwnerHistory=owner_history,
                Name="Pset_SCS_DetectionMetadata", HasProperties=props
            )
            ifc.createIfcRelDefinesByProperties(
                GlobalId=guid.new(), OwnerHistory=owner_history,
                RelatedObjects=[furniture], RelatingPropertyDefinition=pset
            )
    return furniture


def save_ifc_project(objects_list, output_ifc):
    try:
        import ifcopenshell
        import trimesh

        log(f"Creating IFC4 project with {len(objects_list)} objects", "info")

        ifc = ifcopenshell.file(schema="IFC4")
        owner_history, body_ctx, storey = _make_project(ifc)

        added = 0
        for obj in objects_list:
            glb_path = obj.get("glbPath") or obj.get("glbUrl", "")
            # Resolve URL-style paths (/outputs/file.glb) to filesystem
            if glb_path.startswith("/outputs/"):
                glb_path = os.path.join(".", "outputs", os.path.basename(glb_path))

            if not glb_path or not os.path.exists(glb_path):
                log(f"GLB not found for '{obj.get('name')}': {glb_path}", "warn")
                continue

            log(f"Loading GLB: {glb_path}", "info")
            try:
                scene = trimesh.load(glb_path, force="mesh")
                if isinstance(scene, trimesh.Scene):
                    meshes = [g for g in scene.geometry.values()
                              if isinstance(g, trimesh.Trimesh) and len(g.faces) > 0]
                    if not meshes:
                        log(f"No meshes in GLB: {glb_path}", "warn")
                        continue
                    mesh = trimesh.util.concatenate(meshes)
                else:
                    mesh = scene
            except Exception as le:
                log(f"Failed to load GLB: {le}", "warn")
                continue

            _add_furniture(
                ifc, owner_history, body_ctx, storey,
                mesh,
                name=obj.get("name", f"Object_{added}"),
                position=obj.get("position", [0, 0, 0]),
                scale=obj.get("scale", [1, 1, 1]),
                ifc_class=obj.get("ifcClass") or obj.get("ifc_class") or "IfcFurniture",
                category=obj.get("category"),
                dimensions=obj.get("dimensions"),
            )
            added += 1
            log(f"Added '{obj.get('name')}' as {obj.get('ifcClass') or 'IfcFurniture'} — {len(mesh.faces)} faces", "info")

        ifc.write(output_ifc)
        ifc_size = os.path.getsize(output_ifc)
        log(f"IFC4 written: {ifc_size} bytes, {added} objects", "info")

        return {
            "status": "saved",
            "project_path": output_ifc,
            "ifc_size_bytes": ifc_size,
            "object_count": added,
        }

    except Exception as e:
        import traceback
        log(traceback.format_exc(), "error")
        error_exit(f"IFC save failed: {str(e)}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        error_exit("Usage: saveIFC.py <output_ifc> <objects_json>")

    output_ifc = sys.argv[1]
    try:
        objects_list = json.loads(sys.argv[2])
    except Exception as e:
        error_exit(f"Failed to parse objects JSON: {e}")

    result = save_ifc_project(objects_list, output_ifc)
    success_exit(result)
