import time, ifcopenshell, ifcopenshell.geom, trimesh, numpy as np
t0 = time.time()
f = ifcopenshell.open("sample_buildings/Duplex_Architecture.ifc")
settings = ifcopenshell.geom.settings(); settings.set(settings.USE_WORLD_COORDS, True)
SKIP = {"IfcFurnishingElement", "IfcFurniture", "IfcSystemFurnitureElement", "IfcSpace"}  # empty shell
scene = trimesh.Scene()
n = 0
for prod in f.by_type("IfcProduct"):
    if prod.is_a() in SKIP: continue
    if not getattr(prod, "Representation", None): continue
    try:
        sh = ifcopenshell.geom.create_shape(settings, prod)
        v = np.array(sh.geometry.verts).reshape(-1, 3)
        faces = np.array(sh.geometry.faces).reshape(-1, 3)
        if len(v) and len(faces):
            scene.add_geometry(trimesh.Trimesh(vertices=v, faces=faces), node_name=f"{prod.is_a()}-{n}")
            n += 1
    except Exception:
        pass
out = "outputs/duplex_empty.glb"
scene.export(out)
import os
b = scene.bounds
print(f"WROTE {out} | {os.path.getsize(out)//1024} KB | {n} elements | "
      f"bbox {b[1][0]-b[0][0]:.1f}x{b[1][2]-b[0][2]:.1f}x{b[1][1]-b[0][1]:.1f} m | {time.time()-t0:.1f}s")
