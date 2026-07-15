"""make_roomtype_gallery.py — one showcase per SELECTABLE room type (all 18):
the engine's own ✨suggestion solved by the real layout API, rendered four ways:

  <type>_plan_asr.png   annotated 2D: items + hatched clearance zones + ASR panel
  <type>_plan.png       the solver's own floorplan render
  <type>_3d.png         the solver's own 3D render
  <type>_xray.jpg       3D X-ray (shell ghosted) via headless Chrome

    python scripts/make_roomtype_gallery.py     (server running)
Out: docs/room_type_gallery/ + index.html gallery + manifest.json
"""
import json
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, FancyArrow
import trimesh
from PIL import Image

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "docs" / "room_type_gallery"
ROOM_OUT = REPO / "demo" / "app_out"
BASE = "http://localhost:3000"
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

sys.path.insert(0, str(REPO / "backend" / "python-scripts"))
import rule_packs  # noqa: E402  — the SAME numbers the solver enforces

# type -> (label, width, depth): human-realistic sizes per type
ROOMS = {
    "office":       ("Office — Zellenbüro", 5.0, 4.0),
    "workspace":    ("Workspace — heavy storage", 5.0, 4.0),
    "meeting":      ("Meeting — Besprechungsraum", 5.0, 4.0),
    "presentation": ("Presentation hall — Seminarraum", 8.0, 7.0),
    "reception":    ("Reception — Empfang", 5.0, 4.0),
    "break":        ("Break room — Pausenraum", 5.0, 4.0),
    "quiet":        ("Quiet room — Ruheraum", 3.5, 3.5),
    "living":       ("Living room — Wohnzimmer", 5.0, 5.0),
    "lounge":       ("Lounge", 4.5, 4.0),
    "bed":          ("Bedroom — Schlafzimmer", 4.0, 3.5),
    "dining":       ("Dining — Esszimmer", 4.5, 4.0),
    "kitchen":      ("Kitchen — Küche", 5.0, 4.0),
    "storage":      ("Storage — Lager/Keller", 4.0, 3.0),
    "wardrobe":     ("Wardrobe — Garderobe", 4.0, 3.0),
    "entry":        ("Entry — Foyer/Eingang", 5.0, 3.0),
    "balcony":      ("Balcony — Balkon", 4.0, 2.5),
    "print":        ("Print room — Kopierraum", 3.5, 3.0),
    "it":           ("IT/server — EDV-Raum", 4.0, 3.5),
}


def api(path, body=None, timeout=600):
    req = urllib.request.Request(
        BASE + path, data=json.dumps(body).encode() if body else None,
        method="POST" if body else "GET",
        headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=timeout))


def asr_lines(rtype, room, sched):
    """The compliance panel, from the same rule_packs the solver runs."""
    pack = rule_packs.get_pack(rtype)
    aisle = pack.get("min_aisle", 0.90)
    app_ = pack.get("area_per_person")
    area = room["width"] * room["depth"]
    lines = [f"room {room['width']}×{room['depth']} m = {area:.1f} m²",
             f"walk route kept ≥ {aisle:.2f} m (ASR A1.8)"]
    if app_:
        lines.append(f"occupancy basis {app_:.0f} m²/person")
    if rtype in ("office", "workspace"):
        cap = 1 + max(0, int((area - 8.0) // 6.0)) if area >= 8 else 0
        lines.append(f"§5(3) ArbStättV cap: ≤ {cap} workstations"
                     f" (8 m² + 6 m²/further)")
        lines.append("≥1.5 m² movement area per desk (A1.2)")
    circ = sched.get("circulation") or {}
    ok = circ.get("ok", circ.get("feasible"))
    lines.append(f"circulation check: {'PASS' if ok in (True, None) else circ}")
    unp = sched.get("unplaced") or []
    lines.append(f"placed {len(sched['items'])} · refused {len(unp)}"
                 + (f" ({', '.join(str(u) for u in unp[:3])})" if unp else ""))
    return lines


def draw_plan(rtype, label, sched, dest):
    room = sched["room"]
    W, D = float(room["width"]), float(room["depth"])
    zones = sched.get("zones") or {}
    fig_w = 6.2 + 3.4
    fig, ax = plt.subplots(figsize=(fig_w, 6.2 * (D / W) if D < W else 6.8))
    ax.set_xlim(-0.35, W + 0.35)
    ax.set_ylim(-0.35, D + 0.35)
    ax.set_aspect("equal")
    ax.add_patch(Rectangle((0, 0), W, D, fill=False, lw=3, ec="#1f2733"))
    # clearance zones first (under the furniture)
    for iid, rects in zones.items():
        for (zx, zz, zw, zd) in rects:
            ax.add_patch(Rectangle((zx, zz), zw, zd, fc="#2fa36b", alpha=0.14,
                                   ec="#2fa36b", lw=0.8, hatch="///", zorder=1))
    for it in sched["items"]:
        w, d = float(it["width_m"]), float(it["depth_m"])
        rot = float(it.get("rotation_deg", 0))
        if int(round(rot / 90.0)) % 2 == 1:
            w, d = d, w
        x, z = float(it["x"]), float(it["z"])
        wallish = float(it.get("elevation", 0)) > 0.01
        ax.add_patch(Rectangle((x - w / 2, z - d / 2), w, d,
                               fc=it.get("material_hex") or "#9aa4b2",
                               ec="#1f2733", lw=1.0, alpha=0.55 if wallish else 0.92,
                               ls="--" if wallish else "-", zorder=3))
        # facing tick for rotated/seating pieces
        if it["category"] in ("chair", "office_chair", "armchair", "stool", "sofa",
                              "projector") or rot:
            import math
            a = math.radians(rot)
            ax.add_patch(FancyArrow(x, z, 0.22 * math.sin(a), 0.22 * math.cos(a),
                                    width=0.015, head_width=0.08,
                                    color="#1f2733", zorder=4))
        ax.text(x, z - d / 2 - 0.06, it["id"], ha="center", va="top",
                fontsize=5.2, color="#39424e", zorder=5)
    ax.set_title(f"{label} — engine suggestion (medium), clearance zones + ASR",
                 fontsize=10, color="#1f2733")
    ax.set_xlabel("m")
    ax.set_ylabel("m")
    ax.tick_params(labelsize=7)
    # ASR panel to the right of the room
    panel = "\n".join("• " + ln for ln in asr_lines(rtype, room, sched))
    ax.text(1.02, 0.98, "GERMAN ASR CRITERIA\n" + panel, transform=ax.transAxes,
            fontsize=7.6, va="top", ha="left", color="#1f2733",
            bbox=dict(fc="#f2f5f9", ec="#c8d2de", boxstyle="round,pad=0.5"))
    ax.text(1.02, 0.02, "hatched green = solver clearance zone\n"
            "dashed = wall-/counter-mounted (no floor footprint)\n"
            "arrow = facing direction", transform=ax.transAxes,
            fontsize=6.8, va="bottom", ha="left", color="#6b7688")
    fig.savefig(dest, dpi=170, bbox_inches="tight")
    plt.close(fig)


def xray_shot(rtype, label, pieces):
    """Ghost the room-* shell in scene.glb, screenshot via _shot_viewer.html."""
    scene = trimesh.load(str(ROOM_OUT / "scene.glb"))
    if not isinstance(scene, trimesh.Scene):
        scene = trimesh.Scene(scene)
    for name, g in scene.geometry.items():
        if not name.startswith("room-"):
            continue
        mat = getattr(g.visual, "material", None)
        if mat is None:
            continue
        if getattr(mat, "baseColorFactor", None) is not None:
            c = [float(v) for v in mat.baseColorFactor]
            if max(c) > 1.0:
                c = [v / 255.0 for v in c]
            c[3] = 0.20
            mat.baseColorFactor = c
        if hasattr(mat, "alphaMode"):
            mat.alphaMode = "BLEND"
    glb = f"xray_room_{rtype}.glb"
    scene.export(str(ROOM_OUT / glb))
    url = (BASE + "/_shot_viewer.html?src=" + urllib.parse.quote("/out/" + glb) +
           "&label=" + urllib.parse.quote(f"{label} — {pieces} pieces (X-ray)"))
    png = OUT / f"{rtype}_xray.png"
    subprocess.run([CHROME, "--headless=new", "--disable-gpu",
                    "--enable-unsafe-swiftshader", f"--screenshot={png}",
                    "--window-size=1500,950", "--virtual-time-budget=20000",
                    "--hide-scrollbars", url], capture_output=True, timeout=300)
    if png.exists():
        Image.open(png).convert("RGB").save(OUT / f"{rtype}_xray.jpg",
                                            "JPEG", quality=90)
        png.unlink()
        return True
    return False


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = []
    for rtype, (label, w, d) in ROOMS.items():
        t0 = time.time()
        try:
            sug = api(f"/api/room/suggest?type={rtype}&w={w}&d={d}&density=medium")
            counts = Counter(sug.get("items") or [])
            if not counts:
                print(f"SKIP {rtype}: empty suggestion")
                continue
            items = [{"category": c, "count": n} for c, n in counts.items()]
            r = api("/api/room/layout",
                    {"room": {"width": w, "depth": d, "type": rtype,
                              "name": label}, "items": items})
            sched = json.loads((ROOM_OUT / "schedule.json").read_text(encoding="utf-8"))
            draw_plan(rtype, label, sched, OUT / f"{rtype}_plan_asr.png")
            for src, suffix in (("renders/floorplan.png", "_plan.png"),
                                ("renders/furniture3d.png", "_3d.png")):
                p = ROOM_OUT / src
                if p.exists():
                    shutil.copy(p, OUT / (rtype + suffix))
            xr = xray_shot(rtype, label, len(sched["items"]))
            manifest.append({
                "type": rtype, "label": label, "room": f"{w}×{d} m",
                "suggested": sum(counts.values()), "placed": len(sched["items"]),
                "refused": len(sched.get("unplaced") or []),
                "xray": xr, "secs": round(time.time() - t0)})
            print(f"OK   {rtype:13s} {sum(counts.values()):3d} suggested, "
                  f"{len(sched['items'])} placed  ({time.time()-t0:.0f}s)", flush=True)
        except Exception as e:
            print(f"FAIL {rtype}: {e}", flush=True)
            manifest.append({"type": rtype, "label": label, "ok": False,
                             "error": str(e)})
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=1),
                                       encoding="utf-8")

    # ---- gallery page ------------------------------------------------------
    cards = []
    for m in manifest:
        if m.get("ok") is False:
            continue
        t = m["type"]
        cards.append(f"""
  <section class="card">
    <h2>{m['label']} <span class="dim">{m['room']} · {m['placed']} placed"""
                     + (f" · {m['refused']} refused" if m['refused'] else "")
                     + f"""</span></h2>
    <div class="row">
      <figure><img src="{t}_plan_asr.png"><figcaption>2D — clearance zones + ASR criteria</figcaption></figure>
      <figure><img src="{t}_xray.jpg"><figcaption>3D X-ray (shell ghosted)</figcaption></figure>
      <figure><img src="{t}_3d.png"><figcaption>solver 3D render</figcaption></figure>
    </div>
  </section>""")
    (OUT / "index.html").write_text("""<!doctype html><meta charset="utf-8">
<title>SCS Studio — every selectable room type</title>
<style>
 body{font-family:Segoe UI,system-ui,sans-serif;margin:24px;background:#f6f8fb;color:#1f2733}
 h1{font-size:22px} .dim{color:#6b7688;font-size:13px;font-weight:400}
 .card{background:#fff;border:1px solid #dfe6ee;border-radius:10px;padding:14px 18px;margin:14px 0}
 .row{display:flex;gap:12px;flex-wrap:wrap}
 figure{margin:0;flex:1 1 340px;min-width:300px}
 img{width:100%;border:1px solid #e3e9f0;border-radius:6px}
 figcaption{font-size:12px;color:#6b7688;margin-top:4px}
</style>
<h1>Every selectable room type — engine suggestion → CP-SAT layout → ASR check</h1>
<p class="dim">Generated through the live API at medium density. Author: Dimitres Kisimov.</p>
""" + "\n".join(cards), encoding="utf-8")
    ok = sum(1 for m in manifest if m.get("ok") is not False)
    print(f"\n{ok}/{len(ROOMS)} room types rendered -> {OUT}\\index.html")


if __name__ == "__main__":
    main()
