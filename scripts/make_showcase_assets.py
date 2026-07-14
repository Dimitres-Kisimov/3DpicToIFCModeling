"""make_showcase_assets.py — regenerate the two research-hub 3D showcases:

1. THE SHOWROOM (/showroom.html): one 16x12 m office solved with ONE of every
   catalog category (dining ring + desk cluster patterns included)
   -> demo/app_out/showroom.glb + showroom_plan.png + showroom_3d.png
2. X-RAY BUILDING (/xray_building.html): the Buerogebaeude shell ghosted to
   22% opacity with all its populated pieces merged in
   -> demo/app_out/xray_building.glb  (populate the building first)

    python scripts/make_showcase_assets.py    (server must be running)
"""
import json
import shutil
import urllib.request
from pathlib import Path

import numpy as np
import trimesh

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "demo" / "app_out"
XRAY_BUILDING = "b_02a4d40679"          # Buerogebaeude — 380 pieces, reads great ghosted

ONE_OF_EACH = ['armchair', 'bookshelf', 'cabinet', 'clock', 'coat_rack', 'coffee_machine',
               'coffee_table', 'desk', 'filing_cabinet', 'fire_extinguisher',
               'first_aid_cabinet', 'flipchart', 'fridge', 'lamp', 'laptop', 'lectern',
               'locker', 'microwave', 'mirror', 'monitor', 'office_chair', 'partition',
               'phone_booth', 'picture_frame', 'planter', 'presentation_screen', 'printer',
               'projector', 'server_rack', 'side_table', 'sofa', 'table', 'waste_bin',
               'water_dispenser', 'whiteboard', 'bed']


def showroom():
    counts = {c: 1 for c in ONE_OF_EACH}
    counts["chair"] = 4                 # ring the table
    counts["stool"] = 2
    body = json.dumps({"room": {"width": 16, "depth": 12, "type": "office",
                                "name": "The Showroom"},
                       "items": [{"category": k, "count": n} for k, n in counts.items()]}).encode()
    req = urllib.request.Request("http://localhost:3000/api/room/layout", data=body,
                                 method="POST", headers={"Content-Type": "application/json"})
    r = json.load(urllib.request.urlopen(req, timeout=900))
    placed = [o for o in r["items"] if o.get("x") is not None]
    shutil.copy(OUT / "scene.glb", OUT / "showroom.glb")
    shutil.copy(OUT / "renders" / "floorplan.png", OUT / "showroom_plan.png")
    shutil.copy(OUT / "renders" / "furniture3d.png", OUT / "showroom_3d.png")
    print(f"showroom: {len(placed)} placed, unplaced={r.get('unplaced')}")


def xray():
    d = OUT / f"bldg_{XRAY_BUILDING}"
    scene = trimesh.load(str(d / "shell.glb"))
    if not isinstance(scene, trimesh.Scene):
        scene = trimesh.Scene(scene)
    for g in scene.geometry.values():   # ghost the shell
        mat = getattr(g.visual, "material", None)
        if mat is None:
            continue
        if hasattr(mat, "baseColorFactor") and mat.baseColorFactor is not None:
            c = np.array(mat.baseColorFactor, dtype=float)
            if c.max() > 1.0:
                c = c / 255.0
            c[3] = 0.22
            mat.baseColorFactor = c.tolist()
        if hasattr(mat, "alphaMode"):
            mat.alphaMode = "BLEND"
    man = json.load(open(d / "furniture.json", encoding="utf-8"))
    for p in man["pieces"]:
        piece = trimesh.load(str(d / p["glb"]))
        T = np.eye(4)
        T[:3, 3] = p["pos"]
        subs = piece.dump() if isinstance(piece, trimesh.Scene) else [piece]
        for k, sub in enumerate(subs):
            scene.add_geometry(sub, node_name=f"{p['id']}_p{k}", transform=T)
    scene.export(str(OUT / "xray_building.glb"))
    print(f"xray: shell + {len(man['pieces'])} pieces -> xray_building.glb")


if __name__ == "__main__":
    showroom()
    xray()
