"""
build_candidates.py — index every generated mesh variant for the candidate visualizer.

Scans results/list*/<category>/ for *.glb files and writes candidates.json.
The visualizer shows all variants of an item side by side (interactive 3D) and
lets the tester SELECT the winner. Any future variant dropped into an item's
folder (e.g. triposg.glb, trellis2.glb) appears automatically — no code change.

    python build_candidates.py
"""
from __future__ import annotations
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
RES = HERE / "results"

VARIANT_LABELS = {
    "raw": "TripoSR today",
    "improved": "Repair packs (ours)",
}

# Emblem text per variant key — the AI that generated the mesh. Pod sweeps drop
# <engine>.glb files into the item folders; anything unknown shows its filename.
ENGINE_NAMES = {
    "raw": "TripoSR",
    "improved": "TripoSR",
    "triposr": "TripoSR",
    "triposg": "TripoSG",
    "trellis": "TRELLIS 1.0",
    "trellis2": "TRELLIS 2.0",
    "instantmesh": "InstantMesh",
    "sam3d": "SAM 3D",
    "sf3d": "Stable Fast 3D",
}
OURS_KEYS = {"improved"}  # variants that carry the app's repair packs (OURS badge)


def main():
    items = []
    for ldir in sorted(RES.glob("list*")):
        for cdir in sorted(p for p in ldir.iterdir() if p.is_dir()):
            # baseline left, ours next, TripoSG (the pod-comparison baseline) third, extras after
            order = {"raw": 0, "improved": 1, "triposg": 2}
            glbs = sorted(cdir.glob("*.glb"), key=lambda g: (order.get(g.stem, 9), g.stem))
            if not glbs:
                continue
            meta = {}
            mp = cdir / "metrics.json"
            if mp.exists():
                try:
                    meta = json.loads(mp.read_text(encoding="utf-8"))
                except Exception:
                    pass
            variants = []
            for g in glbs:
                key = g.stem
                stats = meta.get(key if key in ("raw", "improved") else "", {})
                base = key[:-9] if key.endswith("_repaired") else key
                variants.append({
                    "key": key,
                    "label": VARIANT_LABELS.get(key, key),
                    "engine": ENGINE_NAMES.get(base, base),
                    "ours": key in OURS_KEYS or key.endswith("_repaired"),
                    "glb": str(g.relative_to(HERE)).replace("\\", "/"),
                    "faces": stats.get("faces"),
                    "watertight": stats.get("watertight"),
                    "iou": stats.get("iou"),
                })
            items.append({
                "list": ldir.name,
                "category": cdir.name,
                "display": meta.get("display", cdir.name),
                "image": meta.get("image"),
                "generated_at": meta.get("started_at"),
                "variants": variants,
            })
    out = HERE / "candidates.json"
    out.write_text(json.dumps({"items": items}, indent=1), encoding="utf-8")
    print(f"candidates.json: {len(items)} items, "
          f"{sum(len(i['variants']) for i in items)} mesh variants")


if __name__ == "__main__":
    main()
