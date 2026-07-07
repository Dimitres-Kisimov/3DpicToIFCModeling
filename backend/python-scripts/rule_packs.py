"""
rule_packs.py — per-room-type ergonomic dimensioning, from established standards.

Sources baked in (see docs/FINDINGS.md feasibility report):
  * Neufert, Architects' Data — office ~5.5-6.5 m2/workstation; circulation aisle >=1.0 m
  * Panero & Zelnik, Human Dimension & Interior Space — seating circulation >=0.46 m
  * ADA / US Access Board — route 0.915 m, door clear 0.815 m, turning circle 1.525 m
  * IBC/IFC egress — keep the door swing clear (never blocked)
  * Living-room "18-inch rule" — sofa<->coffee table 0.46 m; >=0.6 m walkway around seating

A rule pack gives the layout engine the numbers that make a layout feel human:
minimum aisle, per-category clearance buffers, the keep-clear depth in front of
doors, relationship spacings, the functional grouping for that room type, and an
optional ADA accessibility mode. Units: metres.
"""
from __future__ import annotations

ADA = {
    "route_width": 0.915,      # 36"
    "door_clear": 0.815,       # 32"
    "turning_circle": 1.525,   # 60" diameter
}

_CLEARANCES = {
    "default": 0.15, "chair": 0.10, "office_chair": 0.10, "desk": 0.15,
    "table": 0.15, "coffee_table": 0.15, "side_table": 0.10, "sofa": 0.20,
    "stool": 0.10, "bookshelf": 0.10, "cabinet": 0.20, "filing_cabinet": 0.20,
    "lamp": 0.10, "monitor": 0.05, "plant": 0.10, "laptop": 0.05,
    "planter": 0.10, "mirror": 0.05, "clock": 0.05, "picture_frame": 0.05,
}

_BASE = {
    "wall_margin": 0.05,
    "door_keep_clear": 0.90,   # >= door leaf depth; never blocked (IBC/IFC)
    "min_aisle": 1.00,         # Neufert circulation min
    "clearances": _CLEARANCES,
    "gap": {"in_front": 0.12, "beside": 0.10},   # anchoring spacings
}

ROOM_TYPES = {
    "office": {
        **_BASE,
        "area_per_person": 6.0,     # 5.5-6.5 m2/workstation (Neufert/BCO)
        "min_aisle": 1.00,
        "perimeter": {"desk", "cabinet", "filing_cabinet", "storage_cabinet",
                      "bookshelf", "sofa", "side_table",
                      "mirror", "picture_frame", "clock", "planter"},
        "groups": [   # (child_category, anchor_category, relation)
            ("office_chair", "desk", "in_front"),
            ("monitor", "desk", "on_top"),
            ("laptop", "desk", "on_top"),
            ("lamp", "desk", "on_top"),
            ("planter", "desk", "beside"),   # greenery flanks the workstation
            ("stool", "table", "beside"),    # stools cluster around the side table
            ("chair", "table", "beside"),
        ],
    },
    "living": {
        **_BASE,
        "area_per_person": 4.0,
        "min_aisle": 0.60,          # >=24" walkway around seating
        "gap": {"in_front": 0.46, "beside": 0.15},   # sofa<->coffee table 0.46 m
        "perimeter": {"sofa", "cabinet", "bookshelf", "side_table", "tv_stand"},
        "groups": [
            ("coffee_table", "sofa", "in_front"),
            ("stool", "coffee_table", "beside"),
        ],
    },
    "workspace": {   # office variant: heavier desks + storage, wider aisles
        **_BASE,
        "area_per_person": 7.0,
        "min_aisle": 1.20,
        "perimeter": {"desk", "cabinet", "filing_cabinet", "bookshelf", "side_table",
                      "mirror", "picture_frame", "clock", "planter"},
        "groups": [
            ("office_chair", "desk", "in_front"),
            ("monitor", "desk", "on_top"),
            ("laptop", "desk", "on_top"),
            ("planter", "desk", "beside"),
            ("stool", "table", "beside"),
        ],
    },
}


def get_pack(room_type: str = "office", ada: bool = False) -> dict:
    """Return the rule pack for a room type, with ADA minimums applied if requested."""
    pack = dict(ROOM_TYPES.get(room_type, ROOM_TYPES["office"]))
    if ada:
        pack["min_aisle"] = max(pack["min_aisle"], ADA["route_width"])
        pack["door_keep_clear"] = max(pack["door_keep_clear"], ADA["door_clear"])
        pack["turning_circle"] = ADA["turning_circle"]
    return pack


def clearance(pack: dict, category: str, dims=None) -> float:
    """Clearance for a category. Known categories use the table; unknown items fall back to a
    FOOTPRINT-DERIVED value (pass dims as {'width','depth'} or (h, w, d)) so mixed catalogues —
    ABO, AI-generated, other sources — get a sensible gap without a fixed category vocabulary."""
    cl = pack.get("clearances", _CLEARANCES)
    if category in cl:
        return cl[category]
    if dims:
        if isinstance(dims, dict):
            w, d = float(dims.get("width", 0.5)), float(dims.get("depth", 0.5))
        else:
            vals = list(dims) + [0.5, 0.5, 0.5]
            w, d = float(vals[1]), float(vals[2])
        return round(min(0.35, max(0.10, 0.10 + 0.12 * (max(w, d) - 0.5))), 3)
    return cl.get("default", 0.15)


def capacity_hint(pack: dict, room_w: float, room_d: float) -> int:
    """Rough max workstations/seats the room area supports (for feasibility hints)."""
    app = pack.get("area_per_person", 6.0)
    return max(1, int((float(room_w) * float(room_d)) / app))


# ---------------------------------------------------------------------------
# Human (anthropometric) constants + object placement archetypes.
# This layer makes the ergonomics engine OBJECT-AGNOSTIC: every category resolves
# to one of a few archetypes, each defining the HUMAN interaction space (legroom,
# seat pull-out, door swing, approach, bed access) that must stay clear around it.
# Unknown categories fall back to geometry, so ANY object gets sensible behaviour.
# ---------------------------------------------------------------------------

ANTHRO = {                     # metres — Neufert / Panero-Zelnik / ADA
    "shoulder":     0.55,      # person shoulder width (the moving body)
    "aisle":        0.90,      # comfortable walking width
    "seat_pullout": 0.55,      # push a chair back and stand up
    "legroom":      0.55,      # seated legroom at a work surface
    "approach":     0.60,      # standing approach at a surface/appliance
    "swing":        0.55,      # cabinet door / drawer pull depth
    "bed_side":     0.60,      # make the bed / get in from a side
    "turning":      1.525,     # wheelchair turning circle (ADA)
}

# normalised category slug -> archetype
_CATEGORY_ARCHETYPE = {
    "desk": "worksurface", "table": "worksurface", "dining_table": "worksurface",
    "conference_table": "worksurface", "coffee_table": "worksurface", "side_table": "worksurface",
    "chair": "seating", "office_chair": "seating", "armchair": "seating", "stool": "seating",
    "sofa": "lounge_seating", "couch": "lounge_seating", "bench": "lounge_seating",
    "cabinet": "storage", "filing_cabinet": "storage", "storage_cabinet": "storage",
    "wardrobe": "storage", "dresser": "storage", "bookshelf": "storage", "shelf": "storage",
    "bed": "bed",
    "refrigerator": "appliance", "fridge": "appliance", "oven": "appliance", "stove": "appliance",
    "microwave": "appliance", "sink": "appliance", "toilet": "appliance", "bathtub": "appliance",
    "monitor": "on_surface", "laptop": "on_surface", "keyboard": "on_surface", "mouse": "on_surface",
    "book": "on_surface", "vase": "on_surface", "cup": "on_surface",
    "mirror": "wall_mounted", "picture_frame": "wall_mounted", "tv": "wall_mounted", "clock": "wall_mounted",
    "lamp": "free_accent", "floor_lamp": "free_accent", "planter": "free_accent", "plant": "free_accent",
}

# archetype -> {zone direction: anthro key}, facing rule, wall side.
# Directions are LOCAL to the object's facing: front (the side people use), back, left, right.
ARCHETYPES = {
    # worksurface legroom is FRONT-only (user side): a desk's back sits at the wall.
    # Dining/conference tables get people-space via their anchored chairs instead.
    "worksurface":    {"zones": {"front": "legroom"},                    "faces": "open",   "wall": "back"},
    "seating":        {"zones": {"back": "seat_pullout"},                "faces": "anchor", "wall": None},
    # sofas/benches live with their back to a wall and need a standing approach in front
    "lounge_seating": {"zones": {"front": "approach"},                   "faces": "open",   "wall": "back"},
    "storage":        {"zones": {"front": "swing"},                      "faces": "room",   "wall": "back"},
    # bed: foot access is REQUIRED; at least ONE long side must be reachable
    # (a small bedroom legitimately puts the other side against the wall)
    "bed":            {"zones": {"front": "bed_side"},
                       "zones_any": [["left", "bed_side"], ["right", "bed_side"]],
                                                                          "faces": "open",   "wall": "back"},
    "appliance":      {"zones": {"front": "approach"},                   "faces": "room",   "wall": "back"},
    "on_surface":     {"zones": {},                                      "faces": "anchor", "wall": None},
    "wall_mounted":   {"zones": {},                                      "faces": "wall",   "wall": "back"},
    "free_accent":    {"zones": {},                                      "faces": None,     "wall": None},
}


def _norm(category: str) -> str:
    return (category or "").strip().lower().replace(" ", "_")


def archetype_of(category: str, dims=None) -> str:
    """Resolve an object's placement archetype. Known categories use the table; unknown items are
    inferred from geometry (h, w, d) so the engine covers ANY object without a fixed vocabulary."""
    cat = _norm(category)
    if cat in _CATEGORY_ARCHETYPE:
        return _CATEGORY_ARCHETYPE[cat]
    h = w = d = 0.0
    if isinstance(dims, dict):
        h = float(dims.get("height", 0) or 0); w = float(dims.get("width", 0) or 0); d = float(dims.get("depth", 0) or 0)
    elif dims:
        vals = list(dims) + [0, 0, 0]; h, w, d = float(vals[0]), float(vals[1]), float(vals[2])
    if h >= 1.2 and max(w, d) <= 0.7:      # tall & shallow -> storage against a wall
        return "storage"
    if h <= 0.85 and max(w, d) >= 0.9:     # low & broad -> a work/seating surface
        return "worksurface"
    if max(h, w, d) <= 0.4:                # tiny -> sits on a surface
        return "on_surface"
    return "free_accent"


def placement_profile(category: str, dims=None, ada: bool = False) -> dict:
    """The full ergonomic profile for an object, driven by its archetype:
      {archetype, zones:{front/back/left/right: metres}, faces, wall}
    `zones` are the human interaction depths that must stay clear around the object; `faces`/`wall`
    tell the solver how to orient it. Consumed by the CP-SAT solver (A2) and the facing logic (A6)."""
    name = archetype_of(category, dims)
    arch = ARCHETYPES[name]

    def _depth(key):
        depth = ANTHRO.get(key, 0.0)
        if ada:
            depth = max(depth, ADA["route_width"] * 0.6)
        return round(depth, 3)

    zones = {direction: _depth(key) for direction, key in arch["zones"].items()}
    # either-or zone groups (e.g. a bed needs at LEAST one long side reachable)
    zones_any = [[direction, _depth(key)] for direction, key in arch.get("zones_any", [])]
    return {"archetype": name, "zones": zones, "zones_any": zones_any,
            "faces": arch["faces"], "wall": arch["wall"]}
