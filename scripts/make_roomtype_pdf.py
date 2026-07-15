"""make_roomtype_pdf.py — the room-type gallery as a print-ready A4 PDF.
Two pages per room type: (1) a big-text page naming every item included and
the ASR criteria, (2) the 2D clearance plan + the 3D X-ray, full width.
All text sized for A4 paper — nothing squints. Author: Dimitres Kisimov.

    python scripts/make_roomtype_pdf.py     (server running, for item lists)
Out: docs/room_type_gallery/Room_Type_Gallery_A4.pdf
"""
import json
import urllib.request
from collections import Counter
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
from matplotlib.backends.backend_pdf import PdfPages

REPO = Path(__file__).resolve().parents[1]
GAL = REPO / "docs" / "room_type_gallery"
OUT = GAL / "Room_Type_Gallery_A4.pdf"
BASE = "http://localhost:3000"
A4 = (8.27, 11.69)
INK, MUT, BRAND = "#1f2733", "#5b6675", "#2F6BFF"

ROOMS = {  # same sizes the gallery was generated with
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

# one plain-language placement-logic line per item category (the register, short)
LOGIC = {
    "desk": "Workstation anchor — user side kept free, ≥1.5 m² movement area (ASR A1.2)",
    "office_chair": "Belongs to a desk or table, always FACING it",
    "chair": "Regular chair — at tables (max 4 per side, centered); spares park at the wall facing the room",
    "monitor": "ON the desk, screen facing the sitter",
    "table": "Shared surface — chairs gather around it; rectangular tables seat the edges, never a 'petal' ring",
    "cabinet": "Perimeter storage — flat against a wall, doors openable",
    "bookshelf": "Perimeter storage — flat against a wall",
    "filing_cabinet": "Perimeter storage beside the desks",
    "locker": "Wall line-up, typically entrance side",
    "waste_bin": "At arm's reach BESIDE the desk/table (~0.2 m) — movable, minimal clearance",
    "coat_rack": "Near the door / entrance zone",
    "planter": "Corners and window zones only — never mid-room",
    "partition": "Between desk groups; only where desks exist",
    "printer": "Shared wall position, reachable from the aisle",
    "whiteboard": "Wall-mounted at 0.90 m, visibility strip kept clear",
    "presentation_screen": "Owns the front wall (0.80 m mount), visibility strip kept clear",
    "projector": "CEILING-mounted at 2.2 m, aimed at the screen, ASR-safe headroom",
    "lectern": "Front of the room, beside the display axis",
    "flipchart": "Front corner, next to the display wall",
    "sofa": "Lounge anchor — coffee table in front, side table at the end",
    "armchair": "In ROWS: 2 face the same way; 4 = two opposed pairs; never blocking the walkway",
    "side_table": "At the end of a seating row / beside armchairs",
    "coffee_table": "In front of the sofa, sitting distance",
    "stool": "Light seating at small tables / bar height",
    "lamp": "Beside the reading seat",
    "fridge": "Kitchen/break perimeter appliance",
    "microwave": "ON a counter or table — never on the floor",
    "coffee_machine": "ON a counter or table",
    "water_dispenser": "Perimeter, reachable from the aisle",
    "first_aid_cabinet": "Wall-mounted 1.35 m, PROTECTED access strip (nothing may block it)",
    "fire_extinguisher": "Wall-mounted 1.00 m, PROTECTED access strip (ASR A2.2)",
    "mirror": "Wall-mounted, entrance/wardrobe zone",
    "server_rack": "IT room walls, service aisle ≥1.0 m kept free",
    "phone_booth": "Quiet corner, away from desks",
    "bed": "Bedroom anchor — both long sides accessible",
    "wardrobe": "Flat against the bedroom wall",
}


def suggest(rtype, w, d):
    j = json.load(urllib.request.urlopen(
        f"{BASE}/api/room/suggest?type={rtype}&w={w}&d={d}&density=medium",
        timeout=60))
    return Counter(j.get("items") or [])


def cover(pdf, manifest):
    fig = plt.figure(figsize=A4)
    fig.text(0.08, 0.90, "SCS Studio", fontsize=30, fontweight="bold", color=BRAND)
    fig.text(0.08, 0.855, "Every selectable room type — furnished by the engine",
             fontsize=15, color=INK)
    fig.text(0.08, 0.825, "2D plans with clearance zones + German ASR criteria · "
             "3D X-ray renders", fontsize=11, color=MUT)
    y = 0.76
    fig.text(0.08, y, "18 room types in this document:", fontsize=12,
             fontweight="bold", color=INK)
    y -= 0.030
    for rtype, (label, w, d) in ROOMS.items():
        m = next((x for x in manifest if x.get("type") == rtype), {})
        fig.text(0.10, y, f"• {label}", fontsize=11.5, color=INK)
        fig.text(0.62, y, f"{w:g} × {d:g} m — {m.get('placed', '?')} items placed",
                 fontsize=11.5, color=MUT)
        y -= 0.028
    fig.text(0.08, y - 0.02,
             "Every layout: the engine's own ✨suggestion (medium density), solved by\n"
             "the CP-SAT placer under ASR workplace rules and human placement logic.\n"
             "Hatched green = clearance the solver reserves; arrows = facing direction;\n"
             "dashed outlines = wall-/counter-mounted items.",
             fontsize=11, color=INK, va="top")
    fig.text(0.08, 0.06, "Dimitres Kisimov · SCS Studio v3 · generated through the live API",
             fontsize=9, color=MUT)
    pdf.savefig(fig)
    plt.close(fig)


def text_page(pdf, rtype, label, w, d, counts, meta):
    fig = plt.figure(figsize=A4)
    fig.text(0.08, 0.93, label, fontsize=21, fontweight="bold", color=INK)
    fig.text(0.08, 0.895, f"{w:g} × {d:g} m · medium density · "
             f"{meta.get('placed', sum(counts.values()))} items placed · "
             f"{meta.get('refused', 0)} refused", fontsize=12, color=MUT)
    fig.text(0.08, 0.845, "WHAT THE ENGINE PUT IN THIS ROOM — AND WHY",
             fontsize=13, fontweight="bold", color=BRAND)
    y = 0.81
    for cat, n in counts.most_common():
        nice = cat.replace("_", " ")
        fig.text(0.08, y, f"{n} ×", fontsize=13, fontweight="bold", color=INK)
        fig.text(0.145, y, nice, fontsize=13, fontweight="bold", color=INK)
        logic = LOGIC.get(cat, "placed by the general solver rules")
        fig.text(0.145, y - 0.021, logic, fontsize=10.5, color=MUT, wrap=True)
        y -= 0.052
        if y < 0.16:
            break
    fig.text(0.08, 0.10, "German standard applied: ASR A1.2 (areas), A1.8 (routes), "
             "A2.2/A2.3 (safety access),\n§5(3) ArbStättV staffing cap where desks exist. "
             "Full mapping: docs/ASR_COMPLIANCE.md", fontsize=10, color=INK, va="top")
    pdf.savefig(fig)
    plt.close(fig)


def image_page(pdf, rtype, label):
    fig = plt.figure(figsize=A4)
    fig.text(0.08, 0.955, label, fontsize=15, fontweight="bold", color=INK)
    slots = [(0.05, 0.50, 0.90, 0.43, f"{rtype}_plan_asr.png",
              "2D plan — clearance zones + ASR panel"),
             (0.05, 0.035, 0.90, 0.43, f"{rtype}_xray.jpg",
              "3D X-ray — shell ghosted, real placed pieces")]
    for (x, y, ww, hh, fname, cap) in slots:
        p = GAL / fname
        if not p.exists():
            continue
        ax = fig.add_axes([x, y, ww, hh])
        img = mpimg.imread(str(p))
        ax.imshow(img)
        ax.axis("off")
        ax.set_title(cap, fontsize=11, color=MUT, pad=4)
    pdf.savefig(fig)
    plt.close(fig)


def main():
    manifest = json.loads((GAL / "manifest.json").read_text(encoding="utf-8"))
    with PdfPages(OUT) as pdf:
        cover(pdf, manifest)
        for rtype, (label, w, d) in ROOMS.items():
            counts = suggest(rtype, w, d)
            meta = next((x for x in manifest if x.get("type") == rtype), {})
            text_page(pdf, rtype, label, w, d, counts, meta)
            image_page(pdf, rtype, label)
            print("pages:", rtype, flush=True)
    print(f"-> {OUT} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
