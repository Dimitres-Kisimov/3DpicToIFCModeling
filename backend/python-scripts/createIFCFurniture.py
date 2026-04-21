"""
Create IFC Furniture - Phase 6
Converts 3D geometry to IFC furniture objects
"""

import json
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from inference_base import log, error_exit, success_exit


def create_ifc_furniture(glb_path, output_ifc, object_info=None):
    """
    Convert GLB model to IFC furniture object.
    
    In production, would use ifcopenshell:
    - model = ifcopenshell.file()
    - Create IfcFurnitureType
    - Create IfcFurnitureElement
    - Add geometry from GLB
    - model.write(output_ifc)
    """
    
    try:
        log(f"Creating IFC furniture from GLB: {glb_path}", "info")
        
        if not os.path.exists(glb_path):
            error_exit(f"GLB file not found: {glb_path}")
        
        object_info = object_info or {}
        glb_size = os.path.getsize(glb_path)
        
        log(f"GLB size: {glb_size} bytes", "info")
        
        # Placeholder - actual implementation would use ifcopenshell
        # For now, create minimal IFC structure
        ifc_content = create_minimal_ifc(
            glb_path,
            object_info.get('name', 'Generated Furniture'),
            object_info.get('position', [0, 0, 0]),
            object_info.get('rotation', [0, 0, 0])
        )
        
        with open(output_ifc, 'w') as f:
            f.write(ifc_content)
        
        ifc_size = os.path.getsize(output_ifc)
        log(f"IFC file created: {ifc_size} bytes", "info")
        
        return {
            "status": "created",
            "glb_path": glb_path,
            "ifc_path": output_ifc,
            "ifc_size_bytes": ifc_size,
            "object_name": object_info.get('name', 'Furniture'),
            "position": object_info.get('position', [0, 0, 0]),
            "type": "IfcFurnitureElement",
        }
        
    except Exception as e:
        error_exit(f"IFC furniture creation failed: {str(e)}")


def create_minimal_ifc(glb_path, name, position, rotation):
    """Create minimal valid IFC file with furniture element"""
    
    # Minimal IFC2x3 structure with furniture
    ifc_header = """ISO-10303-21;
HEADER;
FILE_DESCRIPTION(('IFC2x3 with geometry from 3D model'), '2;1');
FILE_NAME('GeneratedFurniture.ifc', 2026-04-21T00:00:00, ('Generator'), (''), '', '', '');
FILE_SCHEMA(('IFC2x3'));
ENDSEC;
DATA;
#1=IFCORGANIZATION($,'Company',$,$,$);
#2=IFCPERSON($,'User',$,$,$,$,$,$);
#3=IFCPERSONANDORGANIZATION(#2,#1,$);
#4=IFCAPPLICATION(#1,'1.0','Generator','');
#5=IFCOWNERHISTORY(#3,#4,.ADDED.,$,#3,.ADDED.,2026-04-21T00:00:00,$,$);
#6=IFCDIRECTION((0.,0.,1.));
#7=IFCDIRECTION((1.,0.,0.));
#8=IFCCARTESIANPOINT((0.,0.,0.));
#9=IFCAXIS2PLACEMENT3D(#8,#6,#7);
#10=IFCDIRECTION((0.,0.,1.));
#11=IFCGEOMETRICREPRESENTATIONCONTEXT('Model',3,#9,.MODEL.,$);
#12=IFCGEOMETRICREPRESENTATIONSUBCONTEXT('Body','Model',*,*,*,*,#11,$,.MODEL.,$);
#13=IFCPROJECT('ProjectId',#5,'GeneratedModel',$,$,$,$,(#11),#12);
#14=IFCSITE('SiteId',#5,'Site',$,$,#9,$,$,.ELEMENT.,$,$,$,$);
#15=IFCBUILDING('BuildingId',#5,'Building',$,$,#9,$,$,.ELEMENT.,$,$,$);
#16=IFCBUILDINGSTOREY('FloorId',#5,'Ground Floor',$,$,#9,$,$,.ELEMENT.,$,0.);
#17=IFCFURNITUREELEMENT('FurnitureId',#5,'""" + name + """',$,$,#9,$,$);
#18=IFCRELCONTAINEDINSPATIALSTRUCTURE('ContainmentId',#5,$,$,(#17),#16);
#19=IFCRELFILLSELEMENT('FillingId',#5,$,$,#15,#17);
ENDSEC;
END-ISO-10303-21;
"""
    
    return ifc_header


if __name__ == "__main__":
    if len(sys.argv) < 3:
        error_exit("Usage: createIFCFurniture.py <input_glb> <output_ifc> [object_info_json]")
    
    input_glb = sys.argv[1]
    output_ifc = sys.argv[2]
    object_info = {}
    
    if len(sys.argv) > 3:
        try:
            object_info = json.loads(sys.argv[3])
        except:
            pass
    
    result = create_ifc_furniture(input_glb, output_ifc, object_info)
    success_exit(result)
