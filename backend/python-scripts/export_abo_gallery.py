"""
Export the ABO comparison gallery into a SELF-CONTAINED, portable bundle that can be
re-opened any time without the project's Node server.

Produces deliverable/abo_gallery/:
  - index.html         interactive (orbit) gallery — needs the bundled launcher (a tiny
                       static server) because browsers block file:// GLB fetches.
  - gallery_static.html  image-only gallery — works by double-click (file://), offline,
                       no server, no CDN. The bulletproof "any time, any day" view.
  - assets/            every input/SAM2/rembg/ABO .png and .glb.
  - serve.py / serve.bat  double-click -> static server + opens index.html.
  - README.txt
And zips the whole thing to deliverable/abo_gallery.zip.

Re-run any time to regenerate from outputs/abo_test/.
"""
from __future__ import annotations
import json, shutil, zipfile, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FOLDER = sys.argv[1] if len(sys.argv) > 1 else "abo_test"
NAME = "abo_gallery" if FOLDER == "abo_test" else f"abo_gallery_{FOLDER.replace('abo_test_','')}"
SRC = REPO / "outputs" / FOLDER
OUT = REPO / "deliverable" / NAME
ASSETS = OUT / "assets"

res = json.loads((SRC / "results.json").read_text(encoding="utf-8"))
scores = {}
sp = SRC / "scores.json"
if sp.exists():
    for r in json.loads(sp.read_text(encoding="utf-8"))["rows"]:
        scores[r["base"]] = r

if ASSETS.exists():
    shutil.rmtree(ASSETS)
ASSETS.mkdir(parents=True, exist_ok=True)

# ---- copy assets ------------------------------------------------------------
copied = 0
for r in res["results"]:
    for suf in ("input.png", "sam2.png", "rembg.png", "abo.png",
                "sam2.glb", "rembg.glb", "abo.glb"):
        f = SRC / f"{r['base']}_{suf}"
        if f.exists():
            shutil.copy(f, ASSETS / f.name); copied += 1


def f_label(base, key):
    s = scores.get(base)
    if not s:
        return ""
    m = s["sam"] if key == "sam2" else s["rem"]
    return f' &middot; F={m["fscore"]:.2f}'


by_type = {}
for r in res["results"]:
    by_type.setdefault(r["type"], []).append(r)


def build_rows(interactive: bool):
    out = []
    for t, items in by_type.items():
        out.append(f'<h2>{t.replace("_"," ").title()} <small>({len(items)} models)</small></h2>')
        for r in items:
            b = r["base"]
            if interactive:
                def panel(label, cls, glb, png, extra=""):
                    return (f'<div class="cell"><h4 class="{cls}">{label}{extra}</h4>'
                            f'<model-viewer src="assets/{glb}" poster="assets/{png}" '
                            f'camera-controls auto-rotate auto-rotate-delay="2500" rotation-per-second="18deg" camera-orbit="0deg 76deg 105%" interaction-prompt="none"></model-viewer></div>')
                out.append('<div class="model">'
                    + f'<div class="cell"><h4>Input</h4><img src="assets/{b}_input.png"></div>'
                    + panel("TripoSR&middot;SAM2", "bad", f"{b}_sam2.glb", f"{b}_sam2.png", f_label(b, "sam2"))
                    + panel("TripoSR&middot;rembg", "bad", f"{b}_rembg.glb", f"{b}_rembg.png", f_label(b, "rembg"))
                    + panel("ABO mesh", "win", f"{b}_abo.glb", f"{b}_abo.png", " &middot; F=1.00")
                    + '</div>')
            else:
                def img(label, cls, png, extra=""):
                    return (f'<div class="cell"><h4 class="{cls}">{label}{extra}</h4>'
                            f'<img src="assets/{png}"></div>')
                out.append('<div class="model">'
                    + img("Input", "", f"{b}_input.png")
                    + img("TripoSR&middot;SAM2", "bad", f"{b}_sam2.png", f_label(b, "sam2"))
                    + img("TripoSR&middot;rembg", "bad", f"{b}_rembg.png", f_label(b, "rembg"))
                    + img("ABO mesh", "win", f"{b}_abo.png", " &middot; F=1.00")
                    + '</div>')
    return "\n".join(out)


CSS = '''
body{margin:0;background:#15171c;color:#e7e7ea;font-family:system-ui,sans-serif}
h1{padding:12px 16px;margin:0;border-bottom:1px solid #333} h1 small{color:#888;font-weight:normal}
h2{padding:14px 16px 4px;margin:0;color:#cfd3da} h2 small{color:#888;font-weight:normal}
.model{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;padding:8px 16px;border-bottom:1px solid #2a2d34}
.cell{background:#23262d;border:1px solid #333;border-radius:8px;overflow:hidden;text-align:center}
.cell h4{margin:0;padding:7px 10px;font-size:12px;border-bottom:1px solid #333}
.bad{color:#d68a8a} .win{color:#7ad28a}
img{width:100%;display:block;background:#fff;height:240px;object-fit:contain}
model-viewer{width:100%;height:240px;background:#23262d}
@media(max-width:900px){.model{grid-template-columns:1fr 1fr}}
'''
HEAD = lambda title, mv: (f'<!DOCTYPE html><html><head><meta charset="utf-8">'
    f'<meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title>'
    + ('<script type="module" src="https://unpkg.com/@google/model-viewer/dist/model-viewer.min.js"></script>' if mv else '')
    + f'<style>{CSS}</style></head><body>')

n = len(res["results"])
(OUT / "index.html").write_text(
    HEAD("ABO gallery (interactive)", True)
    + f'<h1>ABO comparison &mdash; TripoSR(SAM2) vs TripoSR(rembg) vs real ABO mesh '
      f'<small>{n} models &middot; drag any panel to orbit &middot; F-score vs ground truth shown</small></h1>'
    + build_rows(True) + '</body></html>', encoding="utf-8")

(OUT / "gallery_static.html").write_text(
    HEAD("ABO gallery (static images)", False)
    + f'<h1>ABO comparison (static images) <small>{n} models &middot; offline, no server needed</small></h1>'
    + build_rows(False) + '</body></html>', encoding="utf-8")

# ---- launcher + readme ------------------------------------------------------
(OUT / "serve.py").write_text(
    'import http.server, socketserver, webbrowser, os\n'
    'os.chdir(os.path.dirname(os.path.abspath(__file__)))\n'
    'PORT = 8801\n'
    'webbrowser.open(f"http://localhost:{PORT}/index.html")\n'
    'print(f"Serving gallery at http://localhost:{PORT}/index.html  (Ctrl+C to stop)")\n'
    'socketserver.TCPServer(("", PORT), http.server.SimpleHTTPRequestHandler).serve_forever()\n',
    encoding="utf-8")
(OUT / "serve.bat").write_text('@echo off\npython "%~dp0serve.py"\n', encoding="utf-8")
(OUT / "README.txt").write_text(
    "ABO comparison gallery -- portable export\n"
    "=========================================\n\n"
    f"{n} furniture models, each: input screenshot | TripoSR(SAM2) | TripoSR(rembg) | real ABO mesh.\n\n"
    "TWO WAYS TO VIEW:\n\n"
    "1) INTERACTIVE (orbit the 3D meshes):\n"
    "   - Double-click  serve.bat   (needs Python + internet for the 3D viewer library).\n"
    "   - It starts a tiny local server and opens index.html in your browser.\n\n"
    "2) STATIC IMAGES (always works, offline, no server):\n"
    "   - Just double-click  gallery_static.html.\n\n"
    "Everything is self-contained in this folder (see assets/). Move/zip it anywhere.\n",
    encoding="utf-8")

# ---- zip --------------------------------------------------------------------
zip_path = REPO / "deliverable" / f"{NAME}.zip"
with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
    for f in OUT.rglob("*"):
        if f.is_file():
            z.write(f, f.relative_to(OUT.parent))

mb = lambda p: p.stat().st_size / 1e6
print(f"bundle: {OUT}  ({copied} asset files copied)")
print(f"zip:    {zip_path}  ({mb(zip_path):.1f} MB)")
print(f"models: {n} across {len(by_type)} types")
