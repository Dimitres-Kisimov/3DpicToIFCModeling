"""make_presentation_shots.py — the presentation pack: numbered JPEGs telling
the project story start -> finish. Live page screenshots (headless Chrome) +
curated evidence renders, all as JPEG with descriptive filenames + INDEX.txt.

    python scripts/make_presentation_shots.py     (server running)
Out: deliverable/local_only/presentation_shots/
"""
import shutil
import subprocess
import time
from pathlib import Path

from PIL import Image

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "deliverable" / "local_only" / "presentation_shots"
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
B = "http://localhost:3000"

# (filename, url, window WxH, descriptor for INDEX.txt)
SHOTS = [
    # --- the three app tabs, in depth -------------------------------------
    ("10_tab1_generate_object", f"{B}/", "1600,1000",
     "TAB 1 - Generate object: photo -> 3D. Quality presets, declared object "
     "type, chair-base styles, engine installs. Where every catalog item is born."),
    ("11_tab2_build_a_room", f"{B}/#room", "1600,1000",
     "TAB 2 - Build a room: office-first room types, size presets, "
     "Light/Medium/Dense, Suggest button, 38-category catalog with variant "
     "picker - solved by CP-SAT under ASR."),
    ("12_tab3_building", f"{B}/#building", "1600,1000",
     "TAB 3 - Building: drop any IFC, floors dissected, per-room picks and "
     "blueprints, populate, export back to IFC/GLB for Revit."),
    # --- research evidence: start -> finish -------------------------------
    ("20_research_hub_7_steps", f"{B}/hub.html", "1600,1800",
     "The Research hub - the whole pipeline as 7 interactive steps with arrows; "
     "every evidence page explained."),
    ("21_benchmark_ab_lists", f"{B}/benchmark/index.html", "1600,1400",
     "WHERE WE STARTED: A/B lists over 187 internet photos - raw TripoSR vs "
     "our repair packs vs every cloud AI, with measured stats."),
    ("22_multi_ai_visualizer", f"{B}/benchmark/visualizer.html", "1600,1000",
     "Multi-AI candidate visualizer - up to 9 variants per item in 3D, "
     "engine emblems, winner voting."),
    ("23_item_register_rules", f"{B}/item_register.html", "1600,1800",
     "The Item Logic Register - every item's distribution rule, purpose, and "
     "standing vs the German standard (ASR-cited / stricter / practice)."),
    ("24_live_layout_visualizer", f"{B}/layout_visualizer.html", "1600,1100",
     "Live Layout Visualizer - pick type x size x density, the real solver "
     "answers with a 2D clearance plan + 3D render."),
    ("25_showroom_all_items", f"{B}/showroom.html", "1600,1400",
     "The Showroom - one of EVERY catalog item in a single 16x12 m ASR office "
     "(41 pieces placed, zero refused)."),
    ("26_human_layouts_densities", f"{B}/human_layouts.html", "1600,1800",
     "Human Layouts - six room types at dense/denser/densest through the real "
     "solver; relational placement + full ASR envelope."),
    ("27_xray_fleet", f"{B}/xray_building.html", "1600,1000",
     "X-RAY: all 15 buildings, shells ghosted to 22% - every solver-placed "
     "piece visible through the walls."),
    ("28_fleet_report_connections", f"{B}/fleet_report.html", "1600,1600",
     "Fleet Generation Report - 15 buildings, ~5,000 pieces, ~2,000 "
     "machine-checked human connections (chair->desk, projector->screen...)."),
    ("29_building_explorer_3d", f"{B}/building_explorer.html", "1600,1000",
     "Interactive 3D Building Explorer - the whole licensed fleet."),
    ("30_roadmap_dated", f"{B}/research_roadmap.html", "1600,1800",
     "The dated research roadmap - every milestone from 2026-04-21 to the "
     "v1.0.0 release, with the test passes marked."),
    # --- the release tag ---------------------------------------------------
    ("40_github_release_v1_tag",
     "https://github.com/Dimitres-Kisimov/3DpicToIFCModeling/releases/tag/v1.0.0",
     "1600,1400",
     "OUR TAG: the public v1.0.0 GitHub release - install instructions + the "
     "510 MB downloadable app bundle."),
]

# curated existing renders to convert: (src, dest name, descriptor)
COPIES = [
    ("docs/human_layouts/office_dense_plan.png", "31_2d_office_dense_plan",
     "2D solver floor plan - office at DENSE with green people-space clearances."),
    ("docs/human_layouts/office_dense_3d.png", "32_3d_office_dense_render",
     "3D render of the same dense office - real catalog meshes, AI-placed."),
    ("docs/human_layouts/office_densest_plan.png", "33_2d_office_densest_plan",
     "2D plan - office at DENSEST: 5 workstations + everything, still legal."),
    ("docs/human_layouts/office_densest_3d.png", "34_3d_office_densest_render",
     "3D render - the densest office; capacity guard trims what cannot fit."),
    ("docs/human_layouts/meeting_densest_3d.png", "35_3d_meeting_densest",
     "3D render - meeting room at densest: table core + presentation gear."),
    ("docs/human_layouts/break_densest_3d.png", "36_3d_break_densest",
     "3D render - Pausenraum at densest: eat, store, recycle per ASR A4.2."),
    ("demo/app_out/showroom_plan.png", "37_2d_showroom_all_items_plan",
     "2D plan of the Showroom - all 38 categories numbered, clearances visible."),
    ("demo/app_out/showroom_3d.png", "38_3d_showroom_all_items_render",
     "3D render of the Showroom - every item placed by the engine."),
]


def shoot(name, url, size, jpg_dir):
    png = jpg_dir / (name + ".png")
    subprocess.run([CHROME, "--headless=new", "--disable-gpu",
                    "--enable-unsafe-swiftshader", f"--screenshot={png}",
                    f"--window-size={size}", "--virtual-time-budget=25000",
                    "--hide-scrollbars", url],
                   capture_output=True, timeout=300)
    return png


def to_jpg(png, name):
    im = Image.open(png).convert("RGB")
    im.save(OUT / (name + ".jpg"), "JPEG", quality=90)
    png.unlink(missing_ok=True)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    index = ["SCS STUDIO - PRESENTATION SHOT PACK",
             "how we started -> where we got  (all JPEG, numbered in story order)",
             "=" * 66, ""]
    for name, url, size, desc in SHOTS:
        try:
            png = shoot(name, url, size, OUT)
            to_jpg(png, name)
            print("shot", name, flush=True)
        except Exception as e:
            print("FAIL", name, str(e)[:100], flush=True)
            continue
        index.append(f"{name}.jpg\n    {desc}\n")
        time.sleep(0.3)
    for src, name, desc in COPIES:
        p = REPO / src
        if not p.exists():
            print("missing", src, flush=True)
            continue
        Image.open(p).convert("RGB").save(OUT / (name + ".jpg"), "JPEG", quality=90)
        index.append(f"{name}.jpg\n    {desc}\n")
        print("copy", name, flush=True)
    (OUT / "INDEX.txt").write_text("\n".join(index), encoding="utf-8")
    print(f"\n{len(list(OUT.glob('*.jpg')))} JPEGs -> {OUT}", flush=True)


if __name__ == "__main__":
    main()
