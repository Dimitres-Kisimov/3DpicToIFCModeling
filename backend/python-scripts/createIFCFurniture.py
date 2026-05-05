"""
IFC export — uses CLIP classification and Depth Anything V2 scale to produce
a semantically correct IFC entity (not always IfcFurnitureElement) with
real-world dimensions baked into the placement.
"""

import json
import sys
import os
import uuid
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))
from inference_base import log, error_exit, success_exit


# Maps IFC class name → IFC entity line template tag used in the STEP file
_IFC_ENTITY_TAGS = {
    "IfcFurnitureElement": "IFCFURNITUREELEMENT",
    "IfcDoor":             "IFCDOOR",
    "IfcWindow":           "IFCWINDOW",
    "IfcStair":            "IFCSTAIR",
    "IfcWall":             "IFCWALL",
    "IfcSlab":             "IFCSLAB",
    "IfcSanitaryTerminal": "IFCSANITARYTERMINAL",
}

# Standard IFC properties per category
_CATEGORY_PROPS = {
    "Chair":     {"Reference": "CHAIR", "Status": "NEW", "IsExternal": False},
    "Sofa":      {"Reference": "SOFA",  "Status": "NEW", "IsExternal": False},
    "Table":     {"Reference": "TABLE", "Status": "NEW", "IsExternal": False},
    "Bed":       {"Reference": "BED",   "Status": "NEW", "IsExternal": False},
    "Cabinet":   {"Reference": "CABINET","Status": "NEW","IsExternal": False},
    "Shelf":     {"Reference": "SHELF", "Status": "NEW", "IsExternal": False},
    "Door":      {"Reference": "DOOR",  "Status": "NEW", "IsExternal": True},
    "Window":    {"Reference": "WINDOW","Status": "NEW", "IsExternal": True},
    "Equipment": {"Reference": "EQUIP", "Status": "NEW", "IsExternal": False},
    "Lighting":  {"Reference": "LIGHT", "Status": "NEW", "IsExternal": False},
    "Toilet":    {"Reference": "TOILET","Status": "NEW", "IsExternal": False},
    "Sink":      {"Reference": "SINK",  "Status": "NEW", "IsExternal": False},
    "Bath":      {"Reference": "BATH",  "Status": "NEW", "IsExternal": False},
    "Stair":     {"Reference": "STAIR", "Status": "NEW", "IsExternal": False},
    "Wall":      {"Reference": "WALL",  "Status": "NEW", "IsExternal": True},
    "Floor":     {"Reference": "FLOOR", "Status": "NEW", "IsExternal": False},
    "Furniture": {"Reference": "FURN",  "Status": "NEW", "IsExternal": False},
}


def _uid():
    return str(uuid.uuid4()).replace("-", "")[:22].upper()


def create_ifc_furniture(glb_path, output_ifc, object_info=None):
    try:
        log(f"Creating IFC from GLB: {glb_path}", "info")

        if not os.path.exists(glb_path):
            error_exit(f"GLB file not found: {glb_path}")

        object_info = object_info or {}
        glb_size = os.path.getsize(glb_path)
        log(f"GLB size: {glb_size} bytes", "info")

        # Pull CLIP + scale data passed through from the generation step
        ifc_class    = object_info.get("ifc_class",    "IfcFurnitureElement")
        category     = object_info.get("ifc_category", "Furniture")
        label        = object_info.get("object_label", "object")
        dims         = object_info.get("estimated_dimensions_m", {})
        name         = object_info.get("name") or label.title()
        position     = object_info.get("position", [0.0, 0.0, 0.0])

        height_mm = int(dims.get("height_m", 1.0) * 1000)
        width_mm  = int(dims.get("width_m",  0.8) * 1000)
        depth_mm  = int(dims.get("depth_m",  0.8) * 1000)

        entity_tag = _IFC_ENTITY_TAGS.get(ifc_class, "IFCFURNITUREELEMENT")
        props = _CATEGORY_PROPS.get(category, _CATEGORY_PROPS["Furniture"])

        log(f"IFC entity: {ifc_class} | category: {category} | "
            f"dims: {height_mm}mm × {width_mm}mm × {depth_mm}mm", "info")

        ifc_content = _build_ifc_step(
            name=name,
            entity_tag=entity_tag,
            ifc_class=ifc_class,
            category=category,
            props=props,
            position=position,
            height_mm=height_mm,
            width_mm=width_mm,
            depth_mm=depth_mm,
            label=label,
        )

        with open(output_ifc, "w") as f:
            f.write(ifc_content)

        ifc_size = os.path.getsize(output_ifc)
        log(f"IFC written: {ifc_size} bytes", "info")

        return {
            "status": "created",
            "glb_path": glb_path,
            "ifc_path": output_ifc,
            "ifc_size_bytes": ifc_size,
            "ifc_class": ifc_class,
            "ifc_category": category,
            "object_name": name,
            "object_label": label,
            "position": position,
            "dimensions_mm": {"height": height_mm, "width": width_mm, "depth": depth_mm},
        }

    except Exception as e:
        import traceback
        log(traceback.format_exc(), "error")
        error_exit(f"IFC creation failed: {str(e)}")


def _build_ifc_step(name, entity_tag, ifc_class, category, props,
                    position, height_mm, width_mm, depth_mm, label):
    ts = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
    px, py, pz = position[0], position[1], position[2]
    is_ext = ".T." if props.get("IsExternal") else ".F."
    ref = props.get("Reference", "OBJ")

    return f"""ISO-10303-21;
HEADER;
FILE_DESCRIPTION(('IFC4 {ifc_class} — generated by 3DpicToIFCModeling'), '2;1');
FILE_NAME('{name}.ifc','{ts}',('{name}'),(''),'3DpicToIFCModeling 1.0','','');
FILE_SCHEMA(('IFC4'));
ENDSEC;
DATA;
/* ── Ownership ─────────────────────────────────────────────────────────── */
#1=IFCORGANIZATION($,'3DpicToIFCModeling',$,$,$);
#2=IFCPERSON($,'Student',$,$,$,$,$,$);
#3=IFCPERSONANDORGANIZATION(#2,#1,$);
#4=IFCAPPLICATION(#1,'1.0','3DpicToIFCModeling','3DPIC');
#5=IFCOWNERHISTORY(#3,#4,$,.ADDED.,${int(datetime.utcnow().timestamp())},$,$,${int(datetime.utcnow().timestamp())});
/* ── Geometry context ──────────────────────────────────────────────────── */
#6=IFCDIRECTION((0.,0.,1.));
#7=IFCDIRECTION((1.,0.,0.));
#8=IFCCARTESIANPOINT((0.,0.,0.));
#9=IFCAXIS2PLACEMENT3D(#8,#6,#7);
#10=IFCGEOMETRICREPRESENTATIONCONTEXT('Model','Model',3,1.E-05,#9,$);
#11=IFCGEOMETRICREPRESENTATIONSUBCONTEXT('Body','Model',*,*,*,*,#10,$,.MODEL_VIEW.,$);
#12=IFCGEOMETRICREPRESENTATIONSUBCONTEXT('Box','Model',*,*,*,*,#10,$,.MODEL_VIEW.,$);
/* ── Units ─────────────────────────────────────────────────────────────── */
#13=IFCSIUNIT(*,.LENGTHUNIT.,.MILLI.,.METRE.);
#14=IFCSIUNIT(*,.AREAUNIT.,$,.SQUARE_METRE.);
#15=IFCSIUNIT(*,.VOLUMEUNIT.,$,.CUBIC_METRE.);
#16=IFCUNITASSIGNMENT((#13,#14,#15));
/* ── Project / Site / Building / Storey ────────────────────────────────── */
#17=IFCPROJECT('{_uid()}',#5,'{name} Project',$,$,$,$,(#10),#16);
#18=IFCSITE('{_uid()}',#5,'Site',$,$,#9,$,$,.ELEMENT.,$,$,$,$,$);
#19=IFCBUILDING('{_uid()}',#5,'Building',$,$,#9,$,$,.ELEMENT.,$,$,$);
#20=IFCBUILDINGSTOREY('{_uid()}',#5,'Ground Floor',$,$,#9,$,$,.ELEMENT.,$,0.);
#21=IFCRELAGGREGATES('{_uid()}',#5,$,$,#17,(#18));
#22=IFCRELAGGREGATES('{_uid()}',#5,$,$,#18,(#19));
#23=IFCRELAGGREGATES('{_uid()}',#5,$,$,#19,(#20));
/* ── Bounding box geometry ─────────────────────────────────────────────── */
#24=IFCCARTESIANPOINT(({px},{py},{pz}));
#25=IFCAXIS2PLACEMENT3D(#24,#6,#7);
#26=IFCLOCALPLACEMENT($,#25);
#27=IFCCARTESIANPOINT((0.,0.,0.));
#28=IFCBOUNDINGBOX(#27,{width_mm}.,{depth_mm}.,{height_mm}.);
#29=IFCSHAPEREPRESENTATION(#12,'Box','BoundingBox',(#28));
#30=IFCPRODUCTDEFINITIONSHAPE($,$,(#29));
/* ── {ifc_class} element ───────────────────────────────────────────────── */
#31={entity_tag}('{_uid()}',#5,'{name}','{category} generated from photo of {label}','{ref}',#26,#30,$,$);
/* ── Spatial containment ───────────────────────────────────────────────── */
#32=IFCRELCONTAINEDINSPATIALSTRUCTURE('{_uid()}',#5,$,$,(#31),#20);
/* ── Properties ────────────────────────────────────────────────────────── */
#33=IFCPROPERTYSINGLEVALUE('ObjectType',$,IFCLABEL('{category}'),$);
#34=IFCPROPERTYSINGLEVALUE('Reference',$,IFCLABEL('{ref}'),$);
#35=IFCPROPERTYSINGLEVALUE('IsExternal',$,IFCBOOLEAN({is_ext}),$);
#36=IFCPROPERTYSINGLEVALUE('NominalHeight',$,IFCLENGTHMEASURE({height_mm}.),$);
#37=IFCPROPERTYSINGLEVALUE('NominalWidth',$,IFCLENGTHMEASURE({width_mm}.),$);
#38=IFCPROPERTYSINGLEVALUE('NominalDepth',$,IFCLENGTHMEASURE({depth_mm}.),$);
#39=IFCPROPERTYSINGLEVALUE('AIModel',$,IFCLABEL('TripoSR+SAM2+CLIP+DepthAnythingV2'),$);
#40=IFCPROPERTYSINGLEVALUE('SourceLabel',$,IFCLABEL('{label}'),$);
#41=IFCPROPERTYSET('{_uid()}',#5,'Pset_ObjectCommon',$,(#33,#34,#35,#36,#37,#38,#39,#40));
#42=IFCRELDEFINESBYPROPERTIES('{_uid()}',#5,$,$,(#31),#41);
ENDSEC;
END-ISO-10303-21;
"""


if __name__ == "__main__":
    if len(sys.argv) < 3:
        error_exit("Usage: createIFCFurniture.py <input_glb> <output_ifc> [object_info_json]")

    input_glb  = sys.argv[1]
    output_ifc = sys.argv[2]
    object_info = {}

    if len(sys.argv) > 3:
        try:
            object_info = json.loads(sys.argv[3])
        except Exception:
            pass

    result = create_ifc_furniture(input_glb, output_ifc, object_info)
    success_exit(result)
