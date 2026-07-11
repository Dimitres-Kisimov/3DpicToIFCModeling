"""make_bench170_manifest.py — build the 170-item manifest (10 lists x 17 categories)
from the committed internet-photo set benchmark/images/<category>/listNN.jpg.

These are the SAME photos as the local TripoSR A/B gallery (localhost:8000), so every
pod model's output drops straight into the gallery/visualizer as a labelled candidate.
No ground truth (internet photos) — do NOT run score_all.py on this manifest; the
comparison is visual (gallery) + app-pipeline (repair + IFC export).

  python make_bench170_manifest.py /workspace/repo3d/benchmark/images bench170_manifest.json
"""
import sys, json
from pathlib import Path

images_root = Path(sys.argv[1] if len(sys.argv) > 1 else "../benchmark/images").resolve()
out_path = sys.argv[2] if len(sys.argv) > 2 else "bench170_manifest.json"

items = []
for cat_dir in sorted(p for p in images_root.iterdir() if p.is_dir()):
    cat = cat_dir.name
    for img in sorted(cat_dir.glob("list*.*")):
        if img.suffix.lower() not in (".jpg", ".jpeg", ".png"):
            continue
        items.append({
            "key": f"{img.stem}_{cat}",          # e.g. list01_bookshelf
            "type": cat,
            "source_id": f"internet:{img.name}",
            "input": str(img),                    # absolute — os.path.join(BUNDLE, abs) == abs
        })

json.dump(items, open(out_path, "w", encoding="utf-8"), indent=1)
print(f"bench170 manifest: {len(items)} items -> {out_path}")
