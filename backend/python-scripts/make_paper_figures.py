"""
make_paper_figures.py — automated figure set for the research paper.

Generates a systematic battery of room layouts (one per evaluation criterion),
renders each server-side (matplotlib/Agg, no GPU/WebGL), and collects a flat set
of paper-ready PNGs plus an index describing what each figure demonstrates.

Criteria (one axis varied at a time):
  C1 functional grouping & seat-facing   C5 obstacle + door constraints
  C2 wall-affinity + open circulation     C6 ADA accessibility mode
  C3 room-type generalization             C7 feasibility boundary (overpacked)
  C4 density / scaling

Run:  python backend/python-scripts/make_paper_figures.py
Out:  paper_figures/  (flat PNGs: figNN_<name>_plan.png + _3d.png) + index.md
"""
from __future__ import annotations

import json
import shutil
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))

import catalog              # noqa: E402
import build_room_scene     # noqa: E402
import render_scene         # noqa: E402

OUT = REPO / "paper_figures"

# (name, criteria, room, picks, caption)
VARIATIONS = [
    ("office_single", "C1",
     {"width": 5, "depth": 4, "type": "office"},
     [{"category": "desk", "count": 1}, {"category": "office_chair", "count": 1},
      {"category": "monitor", "count": 1}, {"category": "lamp", "count": 1}],
     "Single workstation: chair auto-anchored in front of the desk and turned to "
     "face it; monitor + lamp placed on the desk surface."),

    ("office_team", "C1+C2+C4",
     {"width": 8, "depth": 6, "type": "office"},
     [{"category": "desk", "count": 3}, {"category": "office_chair", "count": 3},
      {"category": "monitor", "count": 3}, {"category": "bookshelf", "count": 1},
      {"category": "cabinet", "count": 1}, {"category": "lamp", "count": 1}],
     "Three-workstation office: each desk gets a facing chair + monitor; storage "
     "(bookshelf, cabinet) hugs the walls and the centre stays open for circulation."),

    ("office_obstacles", "C5",
     {"width": 8, "depth": 6, "type": "office",
      "obstacles": [{"x": 3.7, "z": 2.6, "width": 0.5, "depth": 0.5, "kind": "column"}],
      "doors": [{"x": 3.2, "z": 5.0, "width": 0.9, "depth": 1.0}]},
     [{"category": "desk", "count": 3}, {"category": "office_chair", "count": 3},
      {"category": "monitor", "count": 3}, {"category": "cabinet", "count": 1},
      {"category": "bookshelf", "count": 1}],
     "Same office with a structural column and a door keep-clear zone: no furniture "
     "overlaps the obstacle and the door swing stays unblocked."),

    ("office_ada", "C6",
     {"width": 8, "depth": 6, "type": "office", "ada": True},
     [{"category": "desk", "count": 3}, {"category": "office_chair", "count": 3},
      {"category": "monitor", "count": 3}, {"category": "cabinet", "count": 1}],
     "ADA accessibility mode: wider aisles (>=0.915 m route) and door clearances "
     "applied, spreading the same furniture for wheelchair circulation."),

    ("living_room", "C3",
     {"width": 6, "depth": 5, "type": "living"},
     [{"category": "sofa", "count": 1}, {"category": "coffee_table", "count": 1},
      {"category": "stool", "count": 2}, {"category": "bookshelf", "count": 1},
      {"category": "side_table", "count": 1}],
     "Living-room rule pack: different functional groups (coffee-table in front of "
     "sofa, stools beside the coffee-table) and tighter circulation than the office."),

    ("workspace_dense", "C3+C4",
     {"width": 9, "depth": 7, "type": "workspace"},
     [{"category": "desk", "count": 4}, {"category": "office_chair", "count": 4},
      {"category": "monitor", "count": 4}, {"category": "cabinet", "count": 2},
      {"category": "bookshelf", "count": 2}],
     "Workspace variant (heavier storage, wider aisles) at higher density: four "
     "workstations plus storage, testing how the solver scales."),

    ("office_overpacked", "C7",
     {"width": 4, "depth": 3, "type": "office"},
     [{"category": "desk", "count": 4}, {"category": "office_chair", "count": 4},
      {"category": "monitor", "count": 4}, {"category": "cabinet", "count": 3},
      {"category": "bookshelf", "count": 2}],
     "Feasibility boundary: deliberately overpacked small room. The solver reports "
     "infeasible rather than producing an overlapping (invalid) layout."),
]


def _pick_3d_view(rdir: Path) -> Path | None:
    # prefer the coloured real-mesh render; fall back to the abstract massing views
    for name in ("furniture3d.png", "view_02.png", "view_01.png"):
        p = rdir / name
        if p.exists():
            return p
    return None


def _font(size):
    from PIL import ImageFont
    for name in ("arialbd.ttf", "arial.ttf", "DejaVuSans-Bold.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _montage(plan: Path, view: Path, out: Path, title: str):
    """Stitch the floor plan (left) + 3D view (right) into one titled paper panel."""
    from PIL import Image, ImageDraw
    imgs = [Image.open(p).convert("RGB") for p in (plan, view) if p and p.exists()]
    if not imgs:
        return False
    h = min(im.height for im in imgs)
    imgs = [im.resize((int(im.width * h / im.height), h)) for im in imgs]
    pad, bar = 24, 46
    W = sum(im.width for im in imgs) + pad * (len(imgs) + 1)
    canvas = Image.new("RGB", (W, h + pad + bar), "white")
    d = ImageDraw.Draw(canvas)
    d.rectangle([0, 0, W, bar], fill="#23272f")
    d.text((pad, bar // 2), title, fill="white", font=_font(22), anchor="lm")
    x = pad
    for im in imgs:
        canvas.paste(im, (x, bar)); x += im.width + pad
    canvas.save(out)
    return True


def _contact_sheet(panels, out: Path, cols=2):
    """Tile the per-figure montages into a single overview sheet (paper 'Figure 1')."""
    from PIL import Image
    imgs = [Image.open(p).convert("RGB") for p in panels if Path(p).exists()]
    if not imgs:
        return False
    w = min(im.width for im in imgs)
    imgs = [im.resize((w, int(im.height * w / im.width))) for im in imgs]
    rows = (len(imgs) + cols - 1) // cols
    rh = max(im.height for im in imgs); pad = 18
    canvas = Image.new("RGB", (cols * w + pad * (cols + 1), rows * rh + pad * (rows + 1)), "white")
    for i, im in enumerate(imgs):
        r, c = divmod(i, cols)
        canvas.paste(im, (pad + c * (w + pad), pad + r * (rh + pad)))
    canvas.save(out)
    return True


def capacity_sweep(out_png: Path):
    """Feasibility grid: for several room sizes x workstation counts, does the solver
    place everything? Visualises the capacity boundary (the 'real space limit')."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rooms = [("4x3", 4, 3), ("5x4", 5, 4), ("6x5", 6, 5), ("8x6", 8, 6)]
    counts = list(range(1, 7))   # workstations (desk + chair + monitor each)
    grid = []
    tmp = OUT / "_work" / "_sweep"
    for label, w, d in rooms:
        row = []
        for n in counts:
            picks = [{"category": "desk", "count": n}, {"category": "office_chair", "count": n},
                     {"category": "monitor", "count": n}]
            room = {"width": w, "depth": d, "type": "office", "height": 3.0, "name": "sweep"}
            try:
                spec = catalog.build_scene_spec(room, picks)
                res = build_room_scene.build(spec, tmp)
                row.append(1 if res.get("solver") == "ortools-cpsat" else 0)
            except Exception:
                row.append(0)
        grid.append(row)
        print(f"  capacity {label}: {''.join('OK ' if v else 'no ' for v in row)}")

    fig, ax = plt.subplots(figsize=(7, 4))
    ax.imshow(grid, cmap="RdYlGn", vmin=0, vmax=1, aspect="auto")
    ax.set_xticks(range(len(counts))); ax.set_xticklabels(counts)
    ax.set_yticks(range(len(rooms))); ax.set_yticklabels([r[0] + " m" for r in rooms])
    ax.set_xlabel("Workstations requested (desk + chair + monitor each)")
    ax.set_ylabel("Room size")
    ax.set_title("Layout capacity boundary — feasible (green) vs overpacked (red)",
                 fontweight="bold")
    for i in range(len(rooms)):
        for j in range(len(counts)):
            ax.text(j, i, "OK" if grid[i][j] else "X", ha="center", va="center",
                    color="black", fontsize=9, fontweight="bold")
    fig.tight_layout(); fig.savefig(out_png, dpi=150, bbox_inches="tight"); plt.close(fig)
    return rooms, counts, grid


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    index = ["# Research-paper figure set — automated room layouts",
             "",
             "Generated by `backend/python-scripts/make_paper_figures.py`. Each row varies "
             "one axis of the layout method. Images are server-side renders (matplotlib/Agg, "
             "no GPU/WebGL): a labelled top-down floor plan + a 3D massing view.",
             "",
             "| # | Figure | Criteria | Room | Items | Solver | Demonstrates |",
             "|---|--------|----------|------|-------|--------|--------------|"]
    latex = ["% Auto-generated figure blocks for the paper. \\graphicspath{{paper_figures/}}",
             "% Each montage = labelled floor plan (left) + coloured 3D render (right).", ""]
    panels = []

    for i, (name, crit, room, picks, caption) in enumerate(VARIATIONS, 1):
        tag = f"fig{i:02d}_{name}"
        work = OUT / "_work" / name
        work.mkdir(parents=True, exist_ok=True)
        try:
            room = dict(room)
            room.setdefault("height", 3.0)
            room.setdefault("name", name.replace("_", " ").title())
            spec = catalog.build_scene_spec(room, picks)
            res = build_room_scene.build(spec, work)
            solver = res.get("solver", "?")
            try:
                render_scene.main(work)
            except SystemExit:
                pass
            rdir = work / "renders"
            n_items = len(spec["objects"])
            plan = rdir / "floorplan.png"
            view = _pick_3d_view(rdir)
            if plan.exists():
                shutil.copy(plan, OUT / f"{tag}_plan.png")
            if view:
                shutil.copy(view, OUT / f"{tag}_3d.png")
            mtitle = f"Fig {i} — {name.replace('_', ' ').title()}   ·   {crit}"
            montaged = _montage(OUT / f"{tag}_plan.png", OUT / f"{tag}_3d.png",
                                OUT / f"{tag}_montage.png", mtitle)
            if montaged:
                panels.append(OUT / f"{tag}_montage.png")
            feasible = "OK" if solver == "ortools-cpsat" else f"**{solver}**"
            room_s = f'{room["width"]}x{room["depth"]} {room["type"]}'
            index.append(f"| {i} | `{tag}` | {crit} | {room_s} | {n_items} | {feasible} | {caption} |")
            latex += [
                "\\begin{figure}[t]", "  \\centering",
                f"  \\includegraphics[width=\\linewidth]{{{tag}_montage.png}}",
                f"  \\caption{{{caption} "
                f"(\\textbf{{{crit}}}; {room['width']}$\\times${room['depth']}~m "
                f"{room['type']}, {n_items} objects, solver: {solver}).}}",
                f"  \\label{{fig:{tag}}}", "\\end{figure}", ""]
            print(f"[{i}/{len(VARIATIONS)}] {tag}: solver={solver}, items={n_items}, "
                  f"plan={'y' if plan.exists() else 'n'}, 3d={'y' if view else 'n'}, "
                  f"montage={'y' if montaged else 'n'}")
        except Exception as exc:
            index.append(f"| {i} | `{tag}` | {crit} | - | - | ERROR | {exc} |")
            print(f"[{i}/{len(VARIATIONS)}] {tag} FAILED: {exc}", file=sys.stderr)
            traceback.print_exc()

    # overview contact sheet (paper "Figure 1": all scenes at a glance)
    if _contact_sheet(panels, OUT / "fig00_overview.png", cols=2):
        index.insert(5, "| 0 | `fig00_overview` | all | - | - | - | "
                        "Overview contact sheet: all layout scenes at a glance. |")
        print(f"[overview] contact sheet -> fig00_overview.png ({len(panels)} panels)")

    # extra figure: capacity-boundary sweep (C4/C7, quantitative)
    try:
        print("[sweep] capacity boundary ...")
        capacity_sweep(OUT / "fig08_capacity_sweep.png")
        cap = ("Capacity boundary: for each room size, the largest number of full "
               "workstations the solver can place before it reports infeasible.")
        index.append(f"| 8 | `fig08_capacity_sweep` | C4+C7 | various | sweep | grid | {cap} |")
        latex += ["\\begin{figure}[t]", "  \\centering",
                  "  \\includegraphics[width=0.8\\linewidth]{fig08_capacity_sweep.png}",
                  f"  \\caption{{{cap}}}", "  \\label{fig:fig08_capacity_sweep}",
                  "\\end{figure}", ""]
    except Exception as exc:
        print(f"[sweep] failed: {exc}", file=sys.stderr)

    (OUT / "index.md").write_text("\n".join(index) + "\n", encoding="utf-8")
    (OUT / "figures.tex").write_text("\n".join(latex) + "\n", encoding="utf-8")
    print(f"\nDone -> {OUT}  (index.md + figures.tex + per-figure _plan/_3d/_montage PNGs)")


if __name__ == "__main__":
    main()
