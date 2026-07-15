"""make_building_shots.py — one 3D X-ray picture per building for the
presentation pack (50_building_*.jpg). Uses the xray GLBs + _shot_viewer.html.

    python scripts/make_building_shots.py     (server running)
"""
import json
import re
import subprocess
import urllib.parse
from pathlib import Path

from PIL import Image

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "deliverable" / "local_only" / "presentation_shots"
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"


def main():
    idx = json.load(open(REPO / "demo/app_out/xray_index.json", encoding="utf-8"))
    OUT.mkdir(parents=True, exist_ok=True)
    lines = []
    for k, b in enumerate(idx):
        name = re.sub(r"[^A-Za-z0-9]+", "_", b["name"]).strip("_")[:34]
        fn = f"50_building_{k:02d}_{name}"
        label = f"{b['name']} — {b['pieces']} pieces (X-ray)"
        url = ("http://localhost:3000/_shot_viewer.html?src=" +
               urllib.parse.quote(b["glb"]) + "&label=" + urllib.parse.quote(label))
        png = OUT / (fn + ".png")
        budget = 40000 if b["kb"] > 20000 else 20000
        subprocess.run([CHROME, "--headless=new", "--disable-gpu",
                        "--enable-unsafe-swiftshader", f"--screenshot={png}",
                        "--window-size=1500,950", f"--virtual-time-budget={budget}",
                        "--hide-scrollbars", url], capture_output=True, timeout=300)
        if png.exists():
            Image.open(png).convert("RGB").save(OUT / (fn + ".jpg"), "JPEG", quality=90)
            png.unlink()
            lines.append(f"{fn}.jpg\n    3D X-ray of {b['name']} - {b['pieces']} "
                         "solver-placed pieces visible through the ghosted shell.\n")
            print("shot", fn, flush=True)
        else:
            print("FAIL", fn, flush=True)
    idx_p = OUT / "INDEX.txt"
    if idx_p.exists():
        idx_p.write_text(idx_p.read_text(encoding="utf-8") + "\n" + "\n".join(lines),
                         encoding="utf-8")
    print(f"{len(lines)} building pictures added", flush=True)


if __name__ == "__main__":
    main()
