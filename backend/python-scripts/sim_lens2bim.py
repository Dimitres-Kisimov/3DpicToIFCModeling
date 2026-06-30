"""
Lens2BIM — Sim C (Local): Photo -> 3D -> IFC, end-to-end on this PC.

For each input photo this runs the full commercial-safe SCS pipeline *locally*
(fits the 6.4 GB laptop GPU — only TripoSR, no 16/32 GB cloud models):

    photo
      -> SAM2 foreground segmentation (rembg fallback)
      -> TripoSR single-image 3D reconstruction      (run_triposr)
      -> fine-tuned CLIP object classification
      -> Depth-Anything-V2 metric scaling             (the fixed estimate_metric_scale)
      -> IFC4 furniture element                       (createIFCFurniture)

Outputs a per-photo .glb + .ifc plus a run summary.json with timings and the
estimated BIM dimensions.

Usage:
    python sim_lens2bim.py [image1 image2 ...]          # defaults to a sample photo
    python sim_lens2bim.py --out <dir> img1 img2        # custom output dir

All models are cached after first use; nothing is downloaded if already local.
"""
from __future__ import annotations

import sys
import json
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))

from run_triposr import generate_mesh_triposr      # noqa: E402
from createIFCFurniture import create_ifc_furniture  # noqa: E402

SIM_NAME = "Lens2BIM — Sim C (Local): Photo -> 3D -> IFC"

# Sensible default sample: a clear single object that classifies well.
DEFAULT_IMAGES = [REPO / "backend" / "triposr" / "examples" / "chair.png"]


def _parse_args(argv):
    out_dir = None
    images = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--out":
            out_dir = Path(argv[i + 1]); i += 2; continue
        images.append(Path(a)); i += 1
    if not images:
        images = [p for p in DEFAULT_IMAGES if p.exists()]
    if out_dir is None:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_dir = REPO / "outputs" / "sim_lens2bim" / stamp
    return out_dir, images


def run_one(img_path: Path, out_dir: Path) -> dict:
    stem = img_path.stem
    glb_path = str(out_dir / f"{stem}.glb")
    ifc_path = str(out_dir / f"{stem}.ifc")
    rec = {"image": str(img_path), "stem": stem}

    # 1) photo -> 3D (+ SAM2 + CLIP + metric scale)
    t0 = time.perf_counter()
    try:
        gen = generate_mesh_triposr(str(img_path), glb_path)
    except SystemExit as e:            # generate_*_triposr calls error_exit on failure
        rec.update(stage="triposr", ok=False, error=f"exit:{e.code}")
        return rec
    except Exception as e:
        rec.update(stage="triposr", ok=False, error=str(e))
        return rec
    t_gen = time.perf_counter() - t0

    # 2) 3D + metadata -> IFC4 (the gen dict IS the object_info schema)
    t1 = time.perf_counter()
    try:
        ifc = create_ifc_furniture(glb_path, ifc_path, object_info=gen)
    except SystemExit as e:
        rec.update(stage="ifc", ok=False, error=f"exit:{e.code}",
                   faces=gen.get("faces"), glb=glb_path)
        return rec
    except Exception as e:
        rec.update(stage="ifc", ok=False, error=str(e), glb=glb_path)
        return rec
    t_ifc = time.perf_counter() - t1

    rec.update(
        ok=True,
        glb=glb_path,
        ifc=ifc_path,
        device=gen.get("device"),
        faces=gen.get("faces"),
        label=gen.get("object_label"),
        clip_confidence=round(float(gen.get("clip_confidence", 0.0)), 4),
        ifc_class=gen.get("ifc_class"),
        dimensions_m=gen.get("estimated_dimensions_m"),
        ifc_dimensions_mm=ifc.get("dimensions_mm"),
        seconds={"triposr": round(t_gen, 1), "ifc": round(t_ifc, 2)},
    )
    return rec


def main(argv):
    out_dir, images = _parse_args(argv)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n=== {SIM_NAME} ===")
    print(f"output : {out_dir}")
    print(f"images : {len(images)}")
    if not images:
        print("No input images found. Pass image paths or add the sample.")
        return 1

    results = []
    t_run = time.perf_counter()
    for n, img in enumerate(images, 1):
        print(f"\n[{n}/{len(images)}] {img.name}")
        if not img.exists():
            print(f"  ! missing: {img}"); results.append({"image": str(img), "ok": False,
                                                           "error": "missing"}); continue
        rec = run_one(img, out_dir)
        results.append(rec)
        if rec.get("ok"):
            d = rec["dimensions_m"]
            print(f"  OK  {rec['label']} ({rec['clip_confidence']:.0%})  "
                  f"{rec['faces']} faces  ->  {d['height_m']}x{d['width_m']}x{d['depth_m']} m  "
                  f"[{rec['ifc_class']}]  ({rec['seconds']['triposr']}s)")
        else:
            print(f"  FAIL @ {rec.get('stage')}: {rec.get('error')}")
    total = round(time.perf_counter() - t_run, 1)

    summary = {
        "simulation": SIM_NAME,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "output_dir": str(out_dir),
        "image_count": len(images),
        "ok_count": sum(1 for r in results if r.get("ok")),
        "total_seconds": total,
        "results": results,
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"\n=== done: {summary['ok_count']}/{len(images)} ok in {total}s ===")
    print(f"summary: {out_dir / 'summary.json'}")
    return 0 if summary["ok_count"] else 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
