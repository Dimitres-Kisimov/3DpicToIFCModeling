import json, trimesh, numpy as np
from pathlib import Path

ROOT = Path("deliverable/building/SCS_Office_Complex")
meta = json.load(open(ROOT/"building_metamodel.json"))["meta_objects"] if False else json.load(open(ROOT/"building_metamodel.json"))["metaObjects"]
place = json.load(open(ROOT/"building_placement.json"))
sh = float(place.get("storey_height_m", 3.5))

def storey_index(sid): return int(sid.split("-")[-1])

combined = trimesh.Scene()
n = 0
for o in meta:
    if o.get("type") != "IfcSpace": continue
    rid = o["id"]                       # e.g. storey-0-room-1
    parent = o.get("parent")            # storey-0
    cx = float(o.get("room_origin_m", [0,0])[0])
    elev = storey_index(parent) * sh
    # room glb path
    ri = rid.split("room-")[-1]
    glb = ROOT/"rooms"/parent/f"room-{ri}"/"scene.glb"
    if not glb.exists():
        print("MISSING", glb); continue
    s = trimesh.load(str(glb), force="scene")
    T = np.eye(4); T[0,3] = cx; T[1,3] = elev   # world offset (X=cursor, Y=storey elevation)
    for name, geom in s.geometry.items():
        g = geom.copy(); g.apply_transform(T)
        combined.add_geometry(g, node_name=f"{rid}-{name}-{n}")
        n += 1
    print(f"placed {rid} at X={cx} Y={elev}")

out = ROOT/"building.glb"
combined.export(str(out))
b = combined.bounds
print(f"WROTE {out} | {out.stat().st_size//1024} KB | bbox X={b[1][0]-b[0][0]:.1f} Y={b[1][1]-b[0][1]:.1f} Z={b[1][2]-b[0][2]:.1f} m | {n} meshes")
