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


def clearance(pack: dict, category: str) -> float:
    cl = pack.get("clearances", _CLEARANCES)
    return cl.get(category, cl.get("default", 0.15))


def capacity_hint(pack: dict, room_w: float, room_d: float) -> int:
    """Rough max workstations/seats the room area supports (for feasibility hints)."""
    app = pack.get("area_per_person", 6.0)
    return max(1, int((float(room_w) * float(room_d)) / app))
