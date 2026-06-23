"""
catalog.py — turn user item picks + a room type into an anchored scene spec.

The app shows the 400-item ABO catalog by category; the user selects how many of
each (<=20 total). This module instantiates those objects with ergonomic
dimensions + real ABO meshes, and AUTO-ASSIGNS functional relationships from the
room-type rule pack (e.g. office: chair->desk in-front, monitor/lamp->desk on-top;
living: coffee-table->sofa, stool->coffee-table) so the layout makes human sense.
"""
from __future__ import annotations

import json
from pathlib import Path

import rule_packs

REPO = Path(__file__).resolve().parents[2]
ABO_DIR = REPO / "data" / "mesh_library_abo"
_MANIFEST = None

# category -> (ifc_class, (height, width, depth) ergonomic dims, colour_rgb)
CATALOG_META = {
    "desk":           ("IfcTable",                 (0.74, 1.4, 0.7),  [0.55, 0.38, 0.25]),
    "office_chair":   ("IfcChair",                 (1.10, 0.6, 0.6),  [0.15, 0.15, 0.18]),
    "cabinet":        ("IfcFurniture",             (1.20, 1.0, 0.45), [0.72, 0.72, 0.74]),
    "filing_cabinet": ("IfcFurniture",             (1.32, 0.45, 0.6), [0.60, 0.60, 0.62]),
    "bookshelf":      ("IfcFurniture",             (1.50, 0.9, 0.4),  [0.60, 0.45, 0.30]),
    "sofa":           ("IfcFurniture",             (0.85, 2.0, 0.9),  [0.30, 0.35, 0.45]),
    "table":          ("IfcTable",                 (0.74, 1.2, 0.8),  [0.50, 0.35, 0.22]),
    "coffee_table":   ("IfcTable",                 (0.45, 1.1, 0.6),  [0.50, 0.35, 0.22]),
    "side_table":     ("IfcTable",                 (0.55, 0.5, 0.5),  [0.50, 0.35, 0.22]),
    "stool":          ("IfcFurniture",             (0.45, 0.4, 0.4),  [0.40, 0.30, 0.25]),
    "lamp":           ("IfcFurniture",             (1.60, 0.4, 0.4),  [0.85, 0.80, 0.60]),
    "monitor":        ("IfcAudioVisualAppliance",  (0.45, 0.55, 0.18),[0.10, 0.10, 0.10]),
}
# categories with real ABO meshes; the rest fall back to procedural primitives
ABO_CATEGORIES = {"desk", "office_chair", "cabinet", "bookshelf", "sofa", "table", "stool", "lamp"}
# categories without their own ABO mesh borrow a visually-similar one (scaled to their
# own ergonomic dims), so they render as real furniture instead of plain placeholders.
# (monitor stays a clean procedural box — there is no sensible ABO stand-in.)
MESH_BORROW = {"coffee_table": "table", "side_table": "table", "filing_cabinet": "cabinet"}


# hand-picked clean default mesh per category (avoids e.g. open wire-frame bookshelves
# that render as airy cages). Used as index 0 for that category.
PREFERRED = {"bookshelf": "bookshelf_B07PPNNCM2.glb"}


def _manifest():
    global _MANIFEST
    if _MANIFEST is None:
        _MANIFEST = json.loads((ABO_DIR / "manifest.json").read_text(encoding="utf-8"))
    return _MANIFEST


def list_catalog():
    """Pickable categories with whether they're ABO-backed + how many ABO meshes exist."""
    counts = {}
    for e in _manifest():
        counts[e.get("category", "?")] = counts.get(e.get("category", "?"), 0) + 1
    out = []
    for c, (ifc, dims, _col) in sorted(CATALOG_META.items()):
        src = c if c in ABO_CATEGORIES else MESH_BORROW.get(c)
        out.append({"category": c, "label": c.replace("_", " ").title(), "ifc_class": ifc,
                    "abo": src is not None, "abo_count": counts.get(src or c, 0),
                    "dims_hwd": dims})
    return out


def _abo_glb(category, idx):
    items = [e for e in _manifest() if e.get("category") == category]
    if not items:
        return None
    pref = PREFERRED.get(category)
    if pref:   # float the hand-picked clean mesh to index 0
        items = sorted(items, key=lambda e: 0 if e["glb"] == pref else 1)
    return str(ABO_DIR / items[idx % len(items)]["glb"])


def build_scene_spec(room: dict, picks: list) -> dict:
    """picks: [{category, count}] -> anchored scene_spec using the room-type groups."""
    pack = rule_packs.get_pack(room.get("type", "office"), bool(room.get("ada", False)))
    objs, inst, abo_idx = [], {}, {}
    for p in picks:
        cat = p["category"]
        meta = CATALOG_META.get(cat)
        if not meta:
            continue
        ifc, (h, w, d), col = meta
        for k in range(int(p.get("count", 1))):
            oid = f"{cat}-{k + 1}"
            o = {"id": oid, "name": cat.replace("_", " ").title(), "category": cat,
                 "ifc_class": ifc, "dimensions": {"height": h, "width": w, "depth": d},
                 "colour_rgb": col, "source": "SCS primitive", "license": "Apache-2.0"}
            src = cat if cat in ABO_CATEGORIES else MESH_BORROW.get(cat)
            if src:
                i = abo_idx.get(src, 0); abo_idx[src] = i + 1
                glb = _abo_glb(src, i)
                if glb:
                    o["glb"] = glb
                    o["source"] = "Amazon Berkeley Objects (ABO)"; o["license"] = "CC-BY-4.0"
            objs.append(o)
            inst.setdefault(cat, []).append(oid)

    # auto-assign functional anchors from the room-type rule pack
    by_id = {o["id"]: o for o in objs}
    on_top_count = {}   # anchor_id -> how many things already on top (to spread them)
    for child_cat, anchor_cat, rel in pack.get("groups", []):
        anchors = inst.get(anchor_cat, [])
        if not anchors:
            continue
        for i, cid in enumerate(inst.get(child_cat, [])):
            if by_id[cid].get("anchor"):
                continue
            aid = anchors[i % len(anchors)]
            anchor = {"to": aid, "relation": rel}
            if rel == "on_top":
                n = on_top_count.get(aid, 0); on_top_count[aid] = n + 1
                anchor["offset"] = [0.0, -0.18] if n == 0 else [-0.55, -0.20]
            by_id[cid]["anchor"] = anchor

    return {"room": dict(room), "objects": objs}
