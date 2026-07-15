"""fetch_ph_variants.py — fetch the PolyHaven CC0 meshes that match our 15
late-added catalog categories and register them as selectable variants.

Only the items in question (user directive), all CC0, engine tag CC0:
    python scripts/fetch_ph_variants.py     (server running)
"""
import json
import subprocess
import sys
import tempfile
import urllib.request
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BASE = "http://localhost:3000"
UA = "SCSStudio/1.0 (research; CC0 assets)"

# PolyHaven asset id -> our category. STRICT rule (user): the model must BE the
# item, same category name, nothing loosely related. Rejected during screening:
# standing_chalkboard_01 (a sign, not a flipchart), worn_metal_rack (shelving,
# not a server rack).
PICKS = {
    "korean_fire_extinguisher_01": "fire_extinguisher",
    "medical_box": "first_aid_cabinet",          # green first-aid box (wall-mount scaled)
    "filmstrip_projector_8mm": "projector",      # vintage projector variant
    "chinese_screen_panels": "partition",        # folding room divider
    "projector_screen": "presentation_screen",   # tripod projection screen
    "vintage_microwave": "microwave",
}


def fetch_gltf(asset_id, workdir):
    """Download the 1k gltf + all includes with curl (python UA gets 403)."""
    files = json.load(urllib.request.urlopen(
        urllib.request.Request(f"https://api.polyhaven.com/files/{asset_id}",
                               headers={"User-Agent": UA}), timeout=120))
    node = files["gltf"]["1k"]["gltf"]
    entries = [(node["url"], Path(node["url"]).name)]
    for rel, inc in (node.get("include") or {}).items():
        entries.append((inc["url"], rel))
    for url, rel in entries:
        dest = workdir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["curl", "-sSL", "-A", UA, "-o", str(dest), url],
                       check=True, timeout=300)
    return workdir / entries[0][1]


def register(glb_path, category, display):
    boundary = uuid.uuid4().hex
    data = glb_path.read_bytes()
    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="category"\r\n\r\n'
            f'{category}\r\n'
            f'--{boundary}\r\nContent-Disposition: form-data; name="engine"\r\n\r\n'
            f'CC0\r\n'
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
            f'filename="{display}.glb"\r\nContent-Type: model/gltf-binary\r\n\r\n'
            ).encode() + data + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(BASE + "/api/room/upload", data=body, method="POST",
                                 headers={"Content-Type":
                                          f"multipart/form-data; boundary={boundary}"})
    return json.load(urllib.request.urlopen(req, timeout=300))


def main():
    import trimesh
    ok = 0
    for asset_id, category in PICKS.items():
        try:
            with tempfile.TemporaryDirectory() as td:
                gltf = fetch_gltf(asset_id, Path(td))
                scene = trimesh.load(str(gltf))
                glb = Path(td) / f"{asset_id}.glb"
                scene.export(str(glb))
                r = register(glb, category, asset_id)
            item = r.get("item") or {}
            print(f"OK  {asset_id} -> {category}: id {item.get('id')} "
                  f"dims {item.get('dims_m')}", flush=True)
            ok += 1
        except Exception as e:
            print(f"FAIL {asset_id} -> {category}: {str(e)[:160]}", flush=True)
    print(f"{ok}/{len(PICKS)} PolyHaven variants registered", flush=True)


if __name__ == "__main__":
    main()
