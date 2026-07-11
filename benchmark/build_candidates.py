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


def main():
    items = []
    for ldir in sorted(RES.glob("list*")):
        for cdir in sorted(p for p in ldir.iterdir() if p.is_dir()):
            order = {"raw": 0, "improved": 1}          # baseline left, ours right, extras after
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
                variants.append({
                    "key": key,
                    "label": VARIANT_LABELS.get(key, key),
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
