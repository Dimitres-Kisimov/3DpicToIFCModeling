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
# user-generated furniture dropped into the app (photo->3D->IFC pipeline output).
# Overlaid on top of the ABO catalog, flagged so the UI can badge them.
GEN_DIR = REPO / "data" / "generated_assets"
GEN_MANIFEST = GEN_DIR / "manifest.json"
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
    "stool":          ("IfcFurniture",             (0.50, 0.42, 0.42), [0.40, 0.30, 0.25]),
    "lamp":           ("IfcFurniture",             (1.60, 0.4, 0.4),  [0.85, 0.80, 0.60]),
    "monitor":        ("IfcAudioVisualAppliance",  (0.45, 0.55, 0.18),[0.10, 0.10, 0.10]),
    "laptop":         ("IfcAudioVisualAppliance",  (0.25, 0.34, 0.24),[0.20, 0.20, 0.22]),
    "planter":        ("IfcFurniture",             (0.60, 0.40, 0.40),[0.25, 0.45, 0.25]),
    "mirror":         ("IfcFurniture",             (1.20, 0.60, 0.05),[0.80, 0.85, 0.90]),
    "clock":          ("IfcFurniture",             (0.30, 0.30, 0.05),[0.90, 0.90, 0.90]),
    "picture_frame":  ("IfcFurniture",             (0.50, 0.40, 0.04),[0.45, 0.32, 0.20]),
    # extended spaces pack (procedural — no ABO source)
    "lectern":             ("IfcFurniture",            (1.15, 0.60, 0.50), [0.45, 0.33, 0.23]),
    "presentation_screen": ("IfcAudioVisualAppliance", (1.50, 2.40, 0.12), [0.92, 0.92, 0.94]),
    "whiteboard":          ("IfcFurniture",            (1.20, 1.80, 0.10), [0.95, 0.95, 0.96]),
    "projector":           ("IfcAudioVisualAppliance", (0.15, 0.40, 0.30), [0.25, 0.26, 0.28]),
    "armchair":            ("IfcFurniture",            (0.95, 0.80, 0.80), [0.38, 0.42, 0.50]),
    "water_dispenser":     ("IfcElectricAppliance",    (1.10, 0.35, 0.35), [0.70, 0.78, 0.85]),
    "coffee_machine":      ("IfcElectricAppliance",    (0.45, 0.30, 0.40), [0.18, 0.18, 0.20]),
    "locker":              ("IfcFurniture",            (1.80, 0.40, 0.50), [0.52, 0.56, 0.62]),
    # tier-2 office realism
    "printer":             ("IfcElectricAppliance",         (1.10, 0.60, 0.60), [0.85, 0.85, 0.87]),
    "partition":           ("IfcFurniture",                 (1.60, 1.50, 0.06), [0.62, 0.66, 0.72]),
    "phone_booth":         ("IfcFurniture",                 (2.20, 1.05, 1.05), [0.30, 0.34, 0.40]),
    "fridge":              ("IfcElectricAppliance",         (1.75, 0.60, 0.65), [0.88, 0.89, 0.91]),
    "microwave":           ("IfcElectricAppliance",         (0.30, 0.50, 0.38), [0.75, 0.76, 0.78]),
    "coat_rack":           ("IfcFurniture",                 (1.75, 0.50, 0.50), [0.35, 0.28, 0.22]),
    "flipchart":           ("IfcFurniture",                 (1.90, 0.70, 0.65), [0.90, 0.90, 0.92]),
    "waste_bin":           ("IfcFurniture",                 (0.70, 0.35, 0.35), [0.35, 0.38, 0.42]),
    "fire_extinguisher":   ("IfcFireSuppressionTerminal",   (0.60, 0.18, 0.16), [0.78, 0.12, 0.12]),
    "first_aid_cabinet":   ("IfcFurniture",                 (0.45, 0.35, 0.15), [0.95, 0.95, 0.97]),
    "server_rack":         ("IfcElectricDistributionBoard", (2.00, 0.60, 0.80), [0.15, 0.16, 0.18]),
}
# categories with real ABO meshes; the rest fall back to procedural primitives
ABO_CATEGORIES = {"desk", "office_chair", "cabinet", "bookshelf", "sofa", "table", "stool", "lamp",
                  "planter", "mirror", "clock", "picture_frame"}
# categories without their own ABO mesh borrow a visually-similar one (scaled to their
# own ergonomic dims), so they render as real furniture instead of plain placeholders.
# (monitor + laptop stay clean procedural meshes — ABO has no electronics: its 3D subset
#  is furniture/home-goods, so there are 0 monitor/laptop/keyboard meshes to fetch.)
MESH_BORROW = {"coffee_table": "table", "side_table": "table", "filing_cabinet": "cabinet"}


# hand-picked clean default mesh per category (avoids e.g. open wire-frame bookshelves
# that render as airy cages). Used as index 0 for that category.
PREFERRED = {"bookshelf": "bookshelf_B07PPNNCM2.glb"}

# Some ABO pools mix related product types (the "sofa" category holds 8 BENCHes and
# 27 OTTOMANs next to 15 real SOFAs). Entries matching the category's TRUE type sort
# first, so a count-based pick gets an actual sofa — not a storage bench — and the
# ⋯ picker shows the real thing at the top.
_PT_PREFER = {"sofa": ("SOFA",), "cabinet": ("CABINET", "DRESSER"), "lamp": ("LAMP",)}


def _manifest():
    global _MANIFEST
    if _MANIFEST is None:
        _MANIFEST = json.loads((ABO_DIR / "manifest.json").read_text(encoding="utf-8"))
    return _MANIFEST


def list_catalog():
    """Pickable categories with whether they're ABO-backed + how many ABO meshes exist,
    plus how many user-generated items exist per category (so the UI can offer the
    ⋯ picker even for categories with no ABO mesh)."""
    counts = {}
    for e in _manifest():
        counts[e.get("category", "?")] = counts.get(e.get("category", "?"), 0) + 1
    gen_counts = {}
    for e in _gen_manifest_items():
        gc = e.get("category", "?")
        gen_counts[gc] = gen_counts.get(gc, 0) + 1
    out = []
    for c, (ifc, dims, _col) in sorted(CATALOG_META.items()):
        src = c if c in ABO_CATEGORIES else MESH_BORROW.get(c)
        out.append({"category": c, "label": c.replace("_", " ").title(), "ifc_class": ifc,
                    "abo": src is not None, "abo_count": counts.get(src or c, 0),
                    "generated_count": gen_counts.get(c, 0),
                    "dims_hwd": dims})
    # USER-DECLARED categories (uploaded furniture IFCs) overlay additively:
    # they exist purely in the generated manifest and place via the
    # geometry-inferred archetype fallback
    for c in sorted(gen_counts):
        if c not in CATALOG_META:
            out.append({"category": c, "label": c.replace("_", " ").title(),
                        "ifc_class": "IfcFurniture", "abo": False, "abo_count": 0,
                        "generated_count": gen_counts[c], "dims_hwd": None,
                        "custom": True})
    return out


def _cat_items(category):
    items = [e for e in _manifest() if e.get("category") == category]
    types = _PT_PREFER.get(category)
    if types:  # true-type entries first (stable: keeps manifest order within groups)
        items = sorted(items, key=lambda e: 0 if (e.get("product_type") or "").upper() in types else 1)
    pref = PREFERRED.get(category)
    if pref:   # float the hand-picked clean mesh to index 0
        items = sorted(items, key=lambda e: 0 if e["glb"] == pref else 1)
    return items


def _abo_glb(category, idx):
    items = _cat_items(category)
    if not items:
        return None
    return str(ABO_DIR / items[idx % len(items)]["glb"])


def _glb_by_id(category, mesh_id):
    """Resolve a specific mesh by its ASIN/source_id (or glb name) within a category."""
    for e in _cat_items(category):
        if mesh_id in (e.get("source_id"), e.get("glb"), e.get("id")):
            return str(ABO_DIR / e["glb"])
    return None


def _gen_manifest_items():
    """Raw entries from the generated-assets manifest; [] if missing/unreadable."""
    try:
        data = json.loads(GEN_MANIFEST.read_text(encoding="utf-8"))
        return data.get("items", []) if isinstance(data, dict) else []
    except Exception:
        return []


def _generated_items(category):
    """User-generated meshes for a category, shaped like list_items() entries but flagged
    generated. There is usually no thumbnail render — the frontend badge is the key
    signal, so preview is None and the served GLB path is exposed for placement/preview."""
    out = []
    for e in _gen_manifest_items():
        if e.get("category") != category:
            continue
        dims = e.get("dims_m") or [None, None, None]
        fn = e.get("glb")
        thumb = e.get("thumb")
        out.append({"id": e.get("id"), "thumb": None, "preview": None,
                    "code": e.get("code"),                       # professional numbering
                    "display_name": e.get("display_name"),
                    "engine": e.get("engine"),
                    "thumb_url": ("/api/generated/" + thumb) if thumb else None,   # C2 preview
                    "generated_glb": ("/api/generated/" + fn) if fn else None,
                    "product_type": "GENERATED",
                    "dims_m": list(dims) + [None] * (3 - len(dims)) if len(dims) < 3 else dims,
                    "faces": None, "generated": True})
    return out


def _generated_glb_by_id(mesh_id):
    """Absolute path to a generated asset's GLB by its manifest id; None if not found or
    not a .glb (an .ifc-only generated item has no mesh to place)."""
    for e in _gen_manifest_items():
        if e.get("id") == mesh_id:
            fn = e.get("glb") or ""
            if fn.lower().endswith(".glb"):
                p = GEN_DIR / fn
                if p.exists():
                    return str(p)
    return None


def list_items(category):
    """All selectable meshes in a category (for the per-item picker): id, thumbnail, dims.
    Borrowed categories (coffee_table, side_table, filing_cabinet) show their source
    category's meshes, matching what build_scene_spec instantiates.
    User-generated items for the category are APPENDED after the ABO items."""
    src = category if category in ABO_CATEGORIES else MESH_BORROW.get(category, category)
    out = []
    for e in _cat_items(src):
        md = e.get("mesh_dimensions_m", {}) or {}
        preview = Path(e["glb"]).stem + ".preview.png"   # clean colour render, if present
        out.append({"id": e.get("source_id") or e.get("id"), "thumb": e.get("thumb"),
                    "preview": preview if (ABO_DIR / preview).exists() else None,
                    "product_type": e.get("product_type"),
                    "dims_m": [md.get("x"), md.get("y"), md.get("z")],
                    "faces": e.get("faces")})
    out.extend(_generated_items(category))   # additive overlay — badged in the UI
    return out


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
        src = cat if cat in ABO_CATEGORIES else MESH_BORROW.get(cat)
        ids = p.get("ids") or []          # specific chosen meshes (ASINs)
        count = len(ids) if ids else int(p.get("count", 1))
        for k in range(count):
            oid = f"{cat}-{k + 1}"
            o = {"id": oid, "name": cat.replace("_", " ").title(), "category": cat,
                 "ifc_class": ifc, "dimensions": {"height": h, "width": w, "depth": d},
                 "colour_rgb": col, "source": "SCS primitive", "license": "Apache-2.0"}
            glb = None
            gen_glb = None
            if ids:                        # user chose this exact mesh
                glb = _glb_by_id(src or cat, ids[k])
                if not glb:                # not an ABO id — maybe a user-generated asset
                    gen_glb = _generated_glb_by_id(ids[k])
                o["mesh_id"] = ids[k]
            elif src:                      # auto-assign by index
                i = abo_idx.get(src, 0); abo_idx[src] = i + 1
                glb = _abo_glb(src, i)
            if gen_glb:                    # generated item chosen — use its GLB, flag it
                o["glb"] = gen_glb
                o["generated"] = True
                o["source"] = "SCS generated (photo->3D)"; o["license"] = "user-generated"
            elif glb:
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
                # spread on-top children across the surface — enough distinct slots
                # that monitor + laptop + lamp never stack on the same spot
                _SLOTS = [[0.0, -0.18], [-0.45, -0.15], [0.45, -0.15], [-0.3, 0.12], [0.3, 0.12]]
                n = on_top_count.get(aid, 0); on_top_count[aid] = n + 1
                anchor["offset"] = _SLOTS[n % len(_SLOTS)]
            by_id[cid]["anchor"] = anchor

    return {"room": dict(room), "objects": objs}
