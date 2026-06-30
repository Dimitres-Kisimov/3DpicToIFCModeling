"""Build the comparison gallery from outputs/abo_test/results.json.
Each model: input screenshot | TripoSR(SAM2) orbit | TripoSR(rembg) orbit | ABO mesh orbit.
Writes outputs/view_abo_gallery.html (served at /outputs/view_abo_gallery.html)."""
import json
from pathlib import Path

import sys
REPO = Path(__file__).resolve().parents[2]
FOLDER = sys.argv[1] if len(sys.argv) > 1 else "abo_test"
OUT = REPO / "outputs" / FOLDER
res = json.loads((OUT / "results.json").read_text(encoding="utf-8"))

by_type = {}
for r in res["results"]:
    by_type.setdefault(r["type"], []).append(r)

rows = []
for t, items in by_type.items():
    rows.append(f'<h2>{t.replace("_"," ").title()} <small>({len(items)} models)</small></h2>')
    for r in items:
        b = r["base"]
        rows.append(f'''<div class="model">
  <div class="cell"><h4>Input (ABO screenshot)</h4><img src="{FOLDER}/{b}_input.png"></div>
  <div class="cell"><h4 class="bad">TripoSR · SAM2</h4><model-viewer src="{FOLDER}/{b}_sam2.glb" poster="{FOLDER}/{b}_sam2.png" camera-controls auto-rotate></model-viewer><small>{r["faces_sam2"]:,} faces</small></div>
  <div class="cell"><h4 class="bad">TripoSR · rembg</h4><model-viewer src="{FOLDER}/{b}_rembg.glb" poster="{FOLDER}/{b}_rembg.png" camera-controls auto-rotate></model-viewer><small>{r["faces_rembg"]:,} faces</small></div>
  <div class="cell"><h4 class="win">ABO mesh (ground truth)</h4><model-viewer src="{FOLDER}/{b}_abo.glb" poster="{FOLDER}/{b}_abo.png" camera-controls auto-rotate></model-viewer><small>real catalog mesh</small></div>
</div>''')

html = f'''<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ABO test gallery — TripoSR SAM2 vs rembg vs ABO mesh</title>
<script type="module" src="https://unpkg.com/@google/model-viewer/dist/model-viewer.min.js"></script>
<style>
body{{margin:0;background:#15171c;color:#e7e7ea;font-family:system-ui,sans-serif}}
h1{{padding:12px 16px;margin:0;border-bottom:1px solid #333}}
h2{{padding:14px 16px 4px;margin:0;color:#cfd3da}} h2 small{{color:#888;font-weight:normal}}
.model{{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;padding:8px 16px;border-bottom:1px solid #2a2d34}}
.cell{{background:#23262d;border:1px solid #333;border-radius:8px;overflow:hidden;text-align:center}}
.cell h4{{margin:0;padding:7px 10px;font-size:12px;border-bottom:1px solid #333}}
.cell small{{display:block;color:#888;padding:4px;font-size:11px}}
.bad{{color:#d68a8a}} .win{{color:#7ad28a}}
img{{width:100%;display:block;background:#fff;height:240px;object-fit:contain}}
model-viewer{{width:100%;height:240px;background:#23262d}}
@media(max-width:900px){{.model{{grid-template-columns:1fr 1fr}}}}
</style></head><body>
<h1>ABO test — TripoSR (SAM2) vs TripoSR (rembg) vs real ABO mesh &nbsp;<small style="color:#888;font-weight:normal">{len(res["results"])} models across {len(by_type)} types · drag any panel to orbit</small></h1>
{chr(10).join(rows)}
</body></html>'''

dst = REPO / "outputs" / (f"view_{FOLDER}.html" if FOLDER != "abo_test" else "view_abo_gallery.html")
dst.write_text(html, encoding="utf-8")
print(f"wrote {dst} — {len(res['results'])} models, {len(by_type)} types")
