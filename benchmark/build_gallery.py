"""
build_gallery.py — static localhost:8000 gallery for the TripoSR A/B proof.

Reads benchmark/results/ + benchmark/images/sources.json, writes:
  index.html            campaign overview + accurate dates + links
  list01.html ... html  one page per list: 17 rows of photo | today | improved
  angles.html           the photo-angle capture guide

Serve:  python -m http.server 8000   (from the benchmark/ folder)
"""
from __future__ import annotations
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
RES = HERE / "results"

CATEGORIES = ["bookshelf", "cabinet", "clock", "coffee_table", "desk", "filing_cabinet",
              "lamp", "laptop", "mirror", "monitor", "office_chair", "picture_frame",
              "planter", "side_table", "sofa", "stool", "table"]
DISPLAY = {"bookshelf": "Bookshelf", "cabinet": "Cabinet", "clock": "Clock",
           "coffee_table": "Coffee Table", "desk": "Desk", "filing_cabinet": "Filing Cabinet",
           "lamp": "Lamp", "laptop": "Laptop", "mirror": "Mirror", "monitor": "Monitor",
           "office_chair": "Office Chair", "picture_frame": "Picture Frame",
           "planter": "Planter", "side_table": "Side Table", "sofa": "Sofa",
           "stool": "Stool", "table": "Table"}

CSS = """
:root{--bg:#f6f8fb;--card:#fff;--ink:#1c2733;--mut:#5b6b7c;--line:#e3e9f1;--acc:#2f81f7;
--good:#1a7f4b;--bad:#b3261e;--warn:#8a6d00}
*{box-sizing:border-box}body{margin:0;font:15px/1.55 'Segoe UI',system-ui,sans-serif;
background:var(--bg);color:var(--ink);padding:28px 4vw}
h1{font-size:26px;margin:0 0 4px}h2{font-size:19px;margin:26px 0 10px}
.sub{color:var(--mut);margin:0 0 22px}
a{color:var(--acc);text-decoration:none}a:hover{text-decoration:underline}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;
padding:18px 20px;margin:0 0 16px;box-shadow:0 1px 2px rgba(20,40,80,.05)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:14px}
.row{display:grid;grid-template-columns:160px 1fr 1fr 1fr;gap:14px;align-items:start;
border-top:1px solid var(--line);padding:16px 0}
.row:first-of-type{border-top:none}
.cell img{width:100%;border-radius:8px;border:1px solid var(--line);background:#fff}
.lbl{font-size:12px;letter-spacing:.4px;text-transform:uppercase;color:var(--mut);margin:0 0 6px}
.name{font-weight:600;margin:0 0 2px}.meta{font-size:12.5px;color:var(--mut)}
.k{display:inline-block;background:#eef3fa;border-radius:6px;padding:1px 7px;margin:2px 3px 0 0;
font-size:12px;color:#33475e}
.k.good{background:#e5f4ec;color:var(--good)}.k.bad{background:#fbeae9;color:var(--bad)}
.k.warn{background:#faf3d9;color:var(--warn)}
.fail{background:#fff6f5;border:1px dashed #e5b5b1;border-radius:8px;padding:14px;color:var(--bad)}
.badge{font-size:12px;padding:2px 9px;border-radius:99px;background:#eef3fa;color:#33475e}
table{border-collapse:collapse;width:100%}td,th{padding:7px 10px;border-bottom:1px solid var(--line);
text-align:left;font-size:14px}th{color:var(--mut);font-weight:600}
.foot{color:var(--mut);font-size:12.5px;margin-top:26px}
"""

ANGLES = [
    ("Desk · Table · Coffee/Side Table · Stool", "¾ front (30–45° off), elevated ~15–20°",
     "Top surface AND all legs visible — the least for the model to hallucinate."),
    ("Office Chair", "¾ front at seat height",
     "The base is rebuilt parametrically anyway; give the model a clear seat and back."),
    ("Sofa", "¾ front, ~10° up, full length in frame", "Shows seat, arm and back planes."),
    ("Cabinet · Filing Cabinet · Bookshelf", "¾ front ~30°, camera at half height, doors closed",
     "Two crisp faces; open wire cages reconstruct poorly."),
    ("Lamp · Planter", "¾ side against a plain wall, lamp switched OFF",
     "Whole pole/stem visible; a lit lamp breaks segmentation."),
    ("Monitor / Laptop", "Monitor: frontal · Laptop: ¾ front, open ~110°",
     "These become slabs/L-shapes; face detail matters most."),
    ("Mirror · Picture Frame · Clock", "Frontal, tilted 5–10° (mirror: avoid reflecting yourself)",
     "Wall panels are flattened to slabs; frontal maximizes face detail."),
]


def page(title, body, home=True):
    nav = '<p class="sub"><a href="index.html">← All lists</a> · <a href="angles.html">📸 Photo-angle guide</a></p>' if home else ""
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><style>{CSS}</style></head><body>{nav}{body}
<p class="foot">SCS photo→BIM · TripoSR A/B proof · generated locally, app untouched.</p>
</body></html>"""


def kpill(text, cls=""):
    return f'<span class="k {cls}">{text}</span>'


def item_row(list_no, cat, rec, sources):
    name = DISPLAY[cat]
    img_rel = rec.get("image", f"images/{cat}/list{list_no:02d}.jpg")
    src = sources.get(f"{cat}/{Path(img_rel).name}", {})
    src_html = f'<a href="{src.get("page") or src.get("url", "#")}" target="_blank">source</a>' if src else ""
    when = rec.get("started_at", "?")
    dur = rec.get("seconds", "?")
    head = (f'<p class="name">{name}</p>'
            f'<p class="meta">generated {when}<br>{dur}s · {src_html}</p>')
    if rec.get("status") != "ok":
        reason = rec.get("error", "no image found" if rec.get("status") == "no_image" else rec.get("status"))
        return (f'<div class="row"><div class="cell">{head}</div>'
                f'<div class="cell"><p class="lbl">Original photo</p><img loading="lazy" src="{img_rel}"></div>'
                f'<div class="fail" style="grid-column:span 2">generation failed — {reason}</div></div>')
    raw, imp = rec["raw"], rec["improved"]
    rep = imp.get("repair", {})
    def stats(d):
        wt = kpill("watertight ✓", "good") if d.get("watertight") else kpill("not watertight", "bad")
        comps = d.get("components", "?")
        cc = kpill(f"{comps} comp", "good" if comps == 1 else ("warn" if isinstance(comps, int) and comps <= 6 else "bad"))
        iou = d.get("iou", 0)
        clip = d.get("clip", {})
        cl = kpill(f"render reads as: {clip.get('label', '?')}", "good" if clip.get("match") else "warn")
        return (kpill(f"{d.get('faces', 0):,} faces") + cc + wt +
                kpill(f"IoU {iou}") + cl)
    did = []
    if rep.get("symmetry", {}).get("applied") not in (None, "none (asymmetric)"):
        did.append(f"symmetry: {rep['symmetry']['applied']}")
    if rep.get("support") and "healthy" not in str(rep.get("support")):
        did.append(rep["support"])
    if rep.get("panel_flatten"):
        did.append("panel flattened")
    if rep.get("graft"):
        did.append(rep["graft"])
    if rep.get("smooth"):
        did.append(rep["smooth"])
    if rec.get("ifc"):
        i = rec["ifc"]
        did.append("IFC export " + ("✓ valid, %s KB" % i.get("size_kb") if i.get("ok") else "✗ " + i.get("note", "")[:60]))
    done_html = ('<p class="meta" style="margin-top:6px">' + " · ".join(did) + "</p>") if did else ""
    arch = rep.get("archetype", "?")
    # pod engines: any <engine>.png rendered next to the item's GLBs joins the row
    ENGINE_LABEL = {"triposg": "TripoSG", "trellis": "TRELLIS 1.0", "trellis2": "TRELLIS 2.0",
                    "instantmesh": "InstantMesh", "sam3d": "SAM 3D", "sf3d": "Stable Fast 3D"}
    eng_cells = ""
    for ep in sorted((RES / f"list{list_no:02d}" / cat).glob("*.png")):
        if ep.stem in ("raw", "improved"):
            continue
        label = ENGINE_LABEL.get(ep.stem, ep.stem)
        eng_cells += (f'<div class="cell"><p class="lbl">{label}</p>'
                      f'<img loading="lazy" src="results/list{list_no:02d}/{cat}/{ep.name}">'
                      f'<p class="meta"><a href="visualizer.html#list{list_no:02d}/{cat}">spin in 3D →</a></p></div>')
    return (f'<div class="row"><div class="cell">{head}<p class="meta">pack: <b>{arch}</b></p></div>'
            f'<div class="cell"><p class="lbl">Original photo</p><img loading="lazy" src="{img_rel}"></div>'
            f'<div class="cell"><p class="lbl">TripoSR today</p><img loading="lazy" src="results/list{list_no:02d}/{cat}/raw.png">'
            f'<div>{stats(raw)}</div></div>'
            f'<div class="cell"><p class="lbl">Our improvement</p><img loading="lazy" src="results/list{list_no:02d}/{cat}/improved.png">'
            f'<div>{stats(imp)}</div>{done_html}</div>{eng_cells}</div>')


def build_list_page(list_no, sources):
    ldir = RES / f"list{list_no:02d}"
    if not ldir.exists():
        return None
    summary = {}
    sp = ldir / "summary.json"
    if sp.exists():
        summary = json.loads(sp.read_text(encoding="utf-8"))
    rows, ok = [], 0
    for cat in CATEGORIES:
        mp = ldir / cat / "metrics.json"
        if mp.exists():
            rec = json.loads(mp.read_text(encoding="utf-8"))
        else:
            rec = {"category": cat, "status": "pending"}
        if rec.get("status") == "ok":
            ok += 1
        rows.append(item_row(list_no, cat, rec, sources))
    window = ""
    if summary.get("started_at"):
        window = f'{summary["started_at"].replace("T", " ")} → {summary.get("finished_at", "…").replace("T", " ")} local'
    body = (f'<h1>List {list_no} — 17 items</h1>'
            f'<p class="sub">Generated {window or "(in progress)"} · {ok}/17 ok · '
            f'columns: original internet photo → what TripoSR ships today → our repair-pack improvement</p>'
            f'<div class="card">{"".join(rows)}</div>')
    (HERE / f"list{list_no:02d}.html").write_text(page(f"List {list_no} — TripoSR A/B", body), encoding="utf-8")
    return {"list": list_no, "ok": ok, "window": window}


def build_angles():
    rows = "".join(f"<tr><td><b>{a}</b></td><td>{b}</td><td class='meta'>{c}</td></tr>"
                   for a, b, c in ANGLES)
    body = (
        "<h1>📸 Photo-angle guide</h1>"
        "<p class='sub'>TripoSR is single-view — it hallucinates everything the camera doesn't see. "
        "The best photo shows two faces + the top and lets the symmetry repair rebuild the rest.</p>"
        "<div class='card'><p><b>Universal rules:</b> one item, fully in frame with ~10% margin · plain "
        "contrasting background · even diffuse light, no harsh shadows · no occlusion · camera at about "
        "half the object's height.</p>"
        f"<table><tr><th>Items</th><th>Ideal angle</th><th>Why</th></tr>{rows}</table></div>")
    (HERE / "angles.html").write_text(page("Photo-angle guide", body), encoding="utf-8")


def aggregate_stats():
    """Aggregate the campaign so the index documents the improvement at a glance."""
    recs = []
    for mp in RES.glob("list*/*/metrics.json"):
        try:
            r = json.loads(mp.read_text(encoding="utf-8"))
            if r.get("status") == "ok":
                recs.append(r)
        except Exception:
            pass
    if not recs:
        return ""
    n = len(recs)
    def avg(f):
        vals = [f(r) for r in recs if f(r) is not None]
        return sum(vals) / max(len(vals), 1)
    faces_raw = avg(lambda r: r["raw"]["faces"])
    faces_imp = avg(lambda r: r["improved"]["faces"])
    wt_raw = sum(1 for r in recs if r["raw"].get("watertight")) / n * 100
    wt_imp = sum(1 for r in recs if r["improved"].get("watertight")) / n * 100
    iou_raw = avg(lambda r: r["raw"].get("iou"))
    iou_imp = avg(lambda r: r["improved"].get("iou"))
    solid_raw = sum(1 for r in recs if 0 < r["raw"].get("components", 99) <= 6) / n * 100
    solid_imp = sum(1 for r in recs if 0 < r["improved"].get("components", 99) <= 6) / n * 100
    rebuilt = sum(1 for r in recs
                  if "rebuilt" in str(r["improved"].get("repair", {}).get("support", "")))
    ifcs = [r["ifc"] for r in recs if r.get("ifc")]
    ifc_ok = sum(1 for i in ifcs if i.get("ok"))
    rows = [
        ("Mean faces", f"{faces_raw:,.0f}", f"{faces_imp:,.0f}", "smaller = faster viewer & lighter IFC"),
        ("Watertight items", f"{wt_raw:.0f}%", f"{wt_imp:.0f}%", "closed solids (what clean IFC export needs)"),
        ("Coherent object (≤6 parts)", f"{solid_raw:.0f}%", f"{solid_imp:.0f}%", "vs hundreds of floating fragments"),
        ("Silhouette IoU vs photo", f"{iou_raw:.3f}", f"{iou_imp:.3f}", "best-of-8-viewpoints match to the cutout"),
        ("Broken bases rebuilt", "—", f"{rebuilt}", "evidence-driven legs/pedestal/trestle/plinth grafts"),
    ]
    trs = "".join(f"<tr><td>{a}</td><td>{b}</td><td><b>{c}</b></td><td class='meta'>{d}</td></tr>"
                  for a, b, c, d in rows)
    return (f"<div class='card'><h2 style='margin-top:0'>Campaign result — {n} items generated</h2>"
            f"<table><tr><th>Metric</th><th>TripoSR today</th><th>Our improvement</th><th></th></tr>{trs}</table>"
            f"<p class='meta'>IFC spot-proofs: {ifc_ok}/{len(ifcs)} valid mesh-geometry IFC4 exports "
            f"via the app's own exporter.</p></div>")


def build_index(infos):
    cards = []
    for i in range(1, 12):
        info = next((x for x in infos if x and x["list"] == i), None)
        extra = " · all-AI grand comparison" if i == 11 else ""
        if info:
            cards.append(f'<div class="card"><p class="name"><a href="list{i:02d}.html">List {i}</a> '
                         f'<span class="badge">{info["ok"]}/17 ok</span>{extra}</p>'
                         f'<p class="meta">{info["window"] or "in progress"}</p></div>')
        else:
            cards.append(f'<div class="card"><p class="name">List {i}</p><p class="meta">queued…</p></div>')
    windows = [x["window"] for x in infos if x and x["window"]]
    campaign = f"{windows[0].split(' → ')[0]} → {windows[-1].split(' → ')[-1]}" if windows else "starting…"
    body = (
        "<h1>TripoSR A/B proof — 10 lists × 17 items</h1>"
        f"<p class='sub'>Campaign window: {campaign} · Each row: internet photo (never from the catalog) → "
        "the mesh TripoSR ships in the app today → the same mesh after our archetype repair packs. "
        "Every item carries its exact generation timestamp. "
        "<a href='angles.html'>📸 Photo-angle guide</a> · "
        "<a href='visualizer.html'>🎛 Candidate visualizer (interactive 3D, pick the winner)</a></p>"
        + aggregate_stats() +
        "<div class='card'><b>Why post-repair (continuity):</b> the June-23 study measured the single-view "
        "ceiling (Chamfer 0.169 / F-score 0.155, precision 0.81 / recall 0.09) and diagnosed 4 structural "
        "failure modes: asymmetric legs, hallucinated backs, noisy topology, fragmentation. The repair packs "
        "target exactly those: detected-plane symmetry, panel flattening, watertight+decimate, and "
        "evidence-driven support rebuild — clean parametric primitives (the BIM-correct route from the "
        "June-21 research) grafted onto what the generator gets right.</div>"
        f"<div class='grid'>{''.join(cards)}</div>")
    (HERE / "index.html").write_text(page("TripoSR A/B proof", body, home=False), encoding="utf-8")


def main():
    sources_path = HERE / "images" / "sources.json"
    sources = json.loads(sources_path.read_text(encoding="utf-8")) if sources_path.exists() else {}
    infos = [build_list_page(i, sources) for i in range(1, 12)]   # list11 = all-AI grand comparison
    build_angles()
    build_index(infos)
    print("gallery rebuilt:", sum(1 for i in infos if i), "list pages")


if __name__ == "__main__":
    main()
