"""
Save IFC - Phase 6
Combines multiple IFC objects into a single project file
"""

import json
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from inference_base import log, error_exit, success_exit


def save_ifc_project(objects_list, output_ifc):
    """
    Combine multiple IFC objects into single project file.
    
    In production, would use ifcopenshell:
    - Load multiple IFC files
    - Merge into single project
    - Apply transformations
    - Write combined file
    """
    
    try:
        log(f"Saving IFC project with {len(objects_list)} objects", "info")
        log(f"Output: {output_ifc}", "info")
        
        # Create project-level IFC
        ifc_content = create_project_ifc(objects_list)
        
        with open(output_ifc, 'w') as f:
            f.write(ifc_content)
        
        ifc_size = os.path.getsize(output_ifc)
        log(f"Project IFC saved: {ifc_size} bytes", "info")
        
        return {
            "status": "saved",
            "project_path": output_ifc,
            "ifc_size_bytes": ifc_size,
            "object_count": len(objects_list),
            "timestamp": str(Path(output_ifc).stat().st_mtime),
        }
        
    except Exception as e:
        error_exit(f"IFC save failed: {str(e)}")


def create_project_ifc(objects_list):
    """Create project-level IFC with all objects"""
    
    # Build object list
    object_refs = []
    object_defs = []
    obj_id = 20  # Start after standard definitions
    
    for obj in objects_list:
        name = obj.get('name', 'Object')
        pos = obj.get('position', [0, 0, 0])
        
        object_refs.append(f"#{obj_id}")
        object_defs.append(
            f"#{obj_id}=IFCFURNITUREELEMENT('{obj['id']}',#5,'{name}',$,$,#9,$,$);"
        )
        obj_id += 1
    
    object_refs_str = ",".join(object_refs) if object_refs else ""
    object_defs_str = "\n".join(object_defs)
    
    # Minimal project IFC
    ifc_header = f"""ISO-10303-21;
HEADER;
FILE_DESCRIPTION(('IFC2x3 Scene Export'), '2;1');
FILE_NAME('ProjectExport.ifc', 2026-04-21T00:00:00, ('Generator'), (''), '', '', '');
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
#13=IFCPROJECT('ProjectId',#5,'GeneratedScene',$,$,$,$,(#11),#12);
#14=IFCSITE('SiteId',#5,'Site',$,$,#9,$,$,.ELEMENT.,$,$,$,$);
#15=IFCBUILDING('BuildingId',#5,'Building',$,$,#9,$,$,.ELEMENT.,$,$,$);
#16=IFCBUILDINGSTOREY('FloorId',#5,'Ground Floor',$,$,#9,$,$,.ELEMENT.,$,0.);
#17=IFCRELCONTAINEDINSPATIALSTRUCTURE('ContainmentId',#5,$,$,({object_refs_str}),#16);
{object_defs_str}
ENDSEC;
END-ISO-10303-21;
"""
    
    return ifc_header


if __name__ == "__main__":
    if len(sys.argv) < 2:
        error_exit("Usage: saveIFC.py <output_ifc> [objects_json...]")
    
    output_ifc = sys.argv[1]
    objects_list = []
    
    for i in range(2, len(sys.argv)):
        try:
            obj = json.loads(sys.argv[i])
            objects_list.append(obj)
        except:
            pass
    
    result = save_ifc_project(objects_list, output_ifc)
    success_exit(result)
