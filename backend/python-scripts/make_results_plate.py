"""
make_results_plate.py — one composite "results plate" tiling every paper figure into a
single multi-panel page (journal-style). Pulls the generated figures from paper_figures/.

Out: paper_figures/results_plate.png
Run after make_paper_figures.py + make_accuracy_figure.py.
"""
from __future__ import annotations

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

REPO = Path(__file__).resolve().parents[2]
FIGS = REPO / "paper_figures"
OUT = FIGS / "results_plate.png"

# (file, panel label) — montages for scenes, then the two analysis figures
PANELS = [
    ("fig01_office_single_montage.png", "(a) Single workstation — seat-facing + anchoring"),
    ("fig02_office_team_montage.png",   "(b) Team office — wall-affinity, open circulation"),
    ("fig03_office_obstacles_montage.png", "(c) Obstacles + door keep-clear"),
    ("fig04_office_ada_montage.png",     "(d) ADA accessibility (wider aisles)"),
    ("fig05_living_room_montage.png",    "(e) Living room — room-type generalization"),
    ("fig06_workspace_dense_montage.png", "(f) Dense workspace"),
    ("fig07_office_overpacked_montage.png", "(g) Overpacked -> infeasible (boundary)"),
    ("fig08_capacity_sweep.png",         "(h) Capacity boundary (room size x workstations)"),
    ("fig09_accuracy_triposr.png",       "(i) Photo->3D accuracy: precision >> recall"),
]
COLS = 2
CELL_W = 900
PAD = 22
LABEL_H = 34
TITLE_H = 70


def _font(sz, bold=True):
    for n in (("arialbd.ttf" if bold else "arial.ttf"), "DejaVuSans-Bold.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(n, sz)
        except Exception:
            continue
    return ImageFont.load_default()


def main():
    panels = [(FIGS / f, lbl) for f, lbl in PANELS if (FIGS / f).exists()]
    if not panels:
        raise SystemExit("no panel images found — run make_paper_figures.py first")

    # scale each to CELL_W, record cell heights (image + label strip)
    imgs = []
    for path, label in panels:
        im = Image.open(path).convert("RGB")
        h = int(im.height * CELL_W / im.width)
        imgs.append((im.resize((CELL_W, h)), label, h + LABEL_H))

    rows = (len(imgs) + COLS - 1) // COLS
    row_h = [max(imgs[r * COLS + c][2] for c in range(COLS) if r * COLS + c < len(imgs))
             for r in range(rows)]
    W = COLS * CELL_W + PAD * (COLS + 1)
    H = TITLE_H + sum(row_h) + PAD * (rows + 1)

    plate = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(plate)
    d.text((PAD, TITLE_H // 2), "AI room population + photo->3D: results overview",
           fill="#1a1a1a", font=_font(30), anchor="lm")

    y = TITLE_H + PAD
    for r in range(rows):
        x = PAD
        for c in range(COLS):
            i = r * COLS + c
            if i >= len(imgs):
                break
            im, label, _ = imgs[i]
            d.text((x, y), label, fill="#23272f", font=_font(18))
            plate.paste(im, (x, y + LABEL_H))
            x += CELL_W + PAD
        y += row_h[r] + PAD

    plate.save(OUT)
    print(f"-> {OUT}  ({len(imgs)} panels, {W}x{H})")


if __name__ == "__main__":
    main()
