"""
rule_packs.py — per-room-type ergonomic dimensioning, from established standards.

Sources baked in (see docs/FINDINGS.md feasibility report):
  * ASR — Technische Regeln fuer Arbeitsstaetten (Germany, DEFAULT for workplaces):
      A1.2 Raumabmessungen & Bewegungsflaechen — >=1.5 m2 free movement per
      workstation, >=1.00 m user-area depth at the desk; 8-10 m2/workstation
      (Zellenbuero), 12-15 m2 (Grossraumbuero); A1.8 Verkehrswege — route widths
      by occupancy, >=0.60 m access to each workstation. Kill-switch: SCS_ASR=0.
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

ASR = {  # Arbeitsstaettenrichtlinie — Technische Regeln fuer Arbeitsstaetten (DE)
    # ASR A1.2 sect. 5 Abs. 3 — Grundflaeche von Arbeitsraeumen (LEGAL MINIMUM):
    #   "mindestens 8 m2 fuer einen Arbeitsplatz zuzueglich mindestens 6 m2
    #    fuer jeden weiteren"
    "area_first_ws": 8.0,
    "area_addl_ws": 6.0,
    # ASR A1.2 sect. 5.1.1 Abs. 2 / 5.1.2 — Bewegungsflaeche am Arbeitsplatz:
    #   ">= 1,50 m2", "Tiefe und Breite ... muessen mindestens 1,00 m betragen"
    "user_area_depth": 1.00,
    "user_area_min_m2": 1.50,
    # ASR A1.2 sect. 5 Abs. 4 — Richtwerte fuer Bueroraeume (guidance values):
    #   Zellenbuero 8-10 m2/AP inkl. Moeblierung + anteilige Verkehrsflaechen,
    #   Grossraumbuero 12-15 m2/AP
    "area_per_ws_cell": 10.0,
    "area_per_ws_open": 12.5,
    "open_plan_from_m2": 50.0,
    # ASR A1.8 sect. 4.2 Tabelle 2 — Verkehrswege fuer Fussgaengerverkehr:
    "route_upto_5": 0.90,
    "route_upto_20": 1.00,
    "route_upto_100": 1.20,
    # ASR A1.8 Tabelle 2 Zeile 8 — "Gaenge zu persoenlich zugewiesenen
    # Arbeitsplaetzen": 0,60 m (enforced MORE strictly by the A3 circulation
    # walk, which requires a 0.90 m person-path to every placed item)
    "ws_access": 0.60,
}
ASR_ROOM_TYPES = {"office", "workspace", "meeting"}   # desk workstations: full A1.2 staffing rules
# every OTHER room is still a workplace people move through — ASR A1.8 route
# widths apply by expected occupancy (user directive: the WHOLE app follows ASR;
# residential types get the route envelope as a conservative floor)
ASR_ROUTE_BY_TYPE = {
    "presentation": "route_upto_100",   # lecture audiences: 1.20 m
    "reception":    "route_upto_100",   # public circulation: 1.20 m
    "break":        "route_upto_20",    # Pausenraum serves a floor: 1.00 m
    "quiet":        "route_upto_5",     # Ruheraum, few users: 0.90 m
}


def asr_enabled(flag=None):
    """ASR is the DEFAULT standard for workplace rooms; SCS_ASR=0 disables."""
    import os
    if flag is not None:
        return bool(flag)
    return os.environ.get("SCS_ASR", "1") != "0"

_CLEARANCES = {
    "default": 0.15, "chair": 0.10, "office_chair": 0.10, "desk": 0.15,
    "table": 0.15, "coffee_table": 0.15, "side_table": 0.10, "sofa": 0.20,
    "stool": 0.10, "bookshelf": 0.10, "cabinet": 0.20, "filing_cabinet": 0.20,
    "lamp": 0.10, "monitor": 0.05, "plant": 0.10, "laptop": 0.05,
    "planter": 0.10, "mirror": 0.05, "clock": 0.05, "picture_frame": 0.05,
    # easily moveable objects (user rule): a person just nudges them aside, so
    # they claim no real movement clearance — unlike fixed furniture
    "waste_bin": 0.05,
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
                      "bookshelf", "sofa", "side_table", "printer", "locker",
                      "mirror", "picture_frame", "clock", "planter"},
        "groups": [   # (child_category, anchor_category, relation)
            ("office_chair", "desk", "in_front"),
            ("monitor", "desk", "on_top"),
            ("laptop", "desk", "on_top"),
            ("lamp", "desk", "on_top"),
            ("waste_bin", "desk", "beside"),  # the human spot: at arm's reach
            ("stool", "table", "beside"),    # stools cluster around the side table
            ("chair", "table", "beside"),
            ("planter", "side_table", "on_top", 1),   # the cluster plant (user rule)
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
            ("chair", "table", "beside"),   # dining corner: REGULAR chairs ring the table
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
            ("waste_bin", "desk", "beside"),  # arm's reach, same as the office pack
            ("stool", "table", "beside"),
        ],
    },
    "meeting": {        # Besprechungsraum: the table core, every seat FACING it
        **_BASE,
        "area_per_person": 2.5,
        "min_aisle": 1.00,
        "perimeter": {"cabinet", "presentation_screen", "whiteboard", "locker",
                      "planter", "water_dispenser", "flipchart", "sofa"},
        "groups": [
            ("office_chair", "table", "beside"),   # ring the table, facing it
            ("chair", "table", "beside"),
            ("stool", "table", "beside"),
            ("flipchart", "lectern", "beside"),
        ],
    },
    # ---- extended spaces pack (additive room types) --------------------------
    "presentation": {   # lecture hall / Hoersaal: front zone + audience rows
        **_BASE,
        "area_per_person": 1.4,     # seated audience (lecture seating density)
        "min_aisle": 1.00,          # row aisles are enforced by the row layout itself
        "perimeter": {"presentation_screen", "whiteboard", "locker", "cabinet"},
        "groups": [("flipchart", "lectern", "beside")],   # speaker's flipchart at hand
    },
    "quiet": {          # Ruheraum / focus room: sparse, generous clearances
        **_BASE,
        "area_per_person": 8.0,
        "min_aisle": 0.90,
        "gap": {"in_front": 0.50, "beside": 0.20},
        "perimeter": {"armchair", "sofa", "bookshelf", "locker", "planter"},
        "groups": [("planter", "side_table", "on_top", 1)],
    },
    "break": {          # Pausenraum (ASR A4.2 requires one for >10 employees)
        **_BASE,
        "area_per_person": 3.5,
        "min_aisle": 0.90,
        "perimeter": {"cabinet", "locker", "water_dispenser", "planter", "sofa", "fridge"},
        "groups": [
            ("chair", "table", "beside"),
            ("stool", "table", "beside"),
            ("coffee_machine", "table", "on_top"),
            ("microwave", "table", "on_top"),   # appliances never on the floor (user rule)
        ],
    },
    "kitchen": {        # cabinets + cold corner + eat-in table
        **_BASE,
        "area_per_person": 4.0,
        "min_aisle": 1.00,          # work aisle between counters (Neufert kitchen)
        "perimeter": {"cabinet", "fridge", "locker", "water_dispenser", "planter"},
        "groups": [
            ("chair", "table", "beside"),
            ("stool", "table", "beside"),
            ("microwave", "table", "on_top"),   # big appliances live ON a unit (user rule)
            ("coffee_machine", "table", "on_top"),
        ],
    },
    "reception": {      # Empfang / front desk + waiting seats
        **_BASE,
        "area_per_person": 5.0,
        "min_aisle": 1.20,          # public circulation
        "perimeter": {"desk", "cabinet", "planter", "armchair", "sofa"},
        "groups": [
            ("office_chair", "desk", "in_front"),
            ("monitor", "desk", "on_top"),
            ("planter", "side_table", "on_top", 1),
        ],
    },
}


def get_pack(room_type: str = "office", ada: bool = False, asr=None) -> dict:
    """Return the rule pack for a room type. ADA minimums applied on request;
    ASR (German workplace rules) applied BY DEFAULT for workplace room types."""
    pack = dict(ROOM_TYPES.get(room_type, ROOM_TYPES["office"]))
    if ada:
        pack["min_aisle"] = max(pack["min_aisle"], ADA["route_width"])
        pack["door_keep_clear"] = max(pack["door_keep_clear"], ADA["door_clear"])
        pack["turning_circle"] = ADA["turning_circle"]
    if asr_enabled(asr):
        if room_type in ASR_ROOM_TYPES:
            # ASR A1.2 sect.5 Abs.4 Richtwert replaces the (denser) Neufert value
            pack["area_per_person"] = max(pack.get("area_per_person", 6.0),
                                          ASR["area_per_ws_cell"])
            # ASR A1.8 Tab.2: route width for <=20 users; workstation access floor
            pack["min_aisle"] = max(pack["min_aisle"], ASR["route_upto_20"])
            pack["ws_access"] = ASR["ws_access"]
            # ASR A1.2 sect.5 Abs.3 legal minimum: 8 m2 first + 6 m2 each further AP
            pack["area_first_ws"] = ASR["area_first_ws"]
            pack["area_addl_ws"] = ASR["area_addl_ws"]
            pack["standard"] = "ASR A1.2 / A1.8 (Arbeitsstaettenrichtlinie)"
        elif room_type in ASR_ROUTE_BY_TYPE:
            # non-desk workplace rooms: A1.8 Verkehrswege by expected occupancy
            # + the 0.60 m access floor to every reachable spot
            pack["min_aisle"] = max(pack["min_aisle"], ASR[ASR_ROUTE_BY_TYPE[room_type]])
            pack["ws_access"] = ASR["ws_access"]
            pack["standard"] = "ASR A1.8 Verkehrswege (Arbeitsstaettenrichtlinie)"
        else:
            # residential / unknown: ASR route width for few users (0.90 m) as a
            # conservative envelope — the whole app follows one standard
            pack["min_aisle"] = max(pack["min_aisle"], ASR["route_upto_5"])
            pack["standard"] = "ASR A1.8 route envelope (applied app-wide)"
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
    # extended spaces pack (additive): presentation + wellbeing categories
    "lectern": "worksurface", "presentation_screen": "wall_mounted",
    "whiteboard": "wall_mounted", "projector": "free_accent",
    "water_dispenser": "appliance", "coffee_machine": "on_surface", "locker": "storage",
    # tier-2 office realism (additive): ASR-relevant approach/clearance via archetypes
    "printer": "appliance",             # standing approach >= 0.60 m (ASR access floor)
    "phone_booth": "appliance",         # walk-in: entry approach kept clear
    "partition": "divider",             # a solid the solver routes around, no wall pull
    "coat_rack": "free_accent", "flipchart": "free_accent", "waste_bin": "free_accent",
    "fire_extinguisher": "wall_mounted", "first_aid_cabinet": "wall_mounted",
    "server_rack": "storage",
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
    # tier-2: free-standing solid (acoustic partition) — pure obstacle, mid-room OK
    "divider":        {"zones": {},                                      "faces": None,     "wall": None},
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


def placement_profile(category: str, dims=None, ada: bool = False, asr=None) -> dict:
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
    # ASR A1.2 5.1.1/5.1.2: the workstation's Bewegungsflaeche must satisfy BOTH
    # >= 1.50 m2 AND >= 1.00 m depth/width. The zone is desk-wide, so the depth
    # scales with the actual desk width (a 1.40 m desk needs 1.50/1.40 = 1.08 m).
    # Applies to desks (workstations), not dining/coffee tables. SCS_ASR=0 off.
    if _norm(category) == "desk" and asr_enabled(asr) and "front" in zones:
        w = 1.40
        if isinstance(dims, dict):
            w = float(dims.get("width", w) or w)
        elif dims:
            vals = list(dims) + [0, w, 0]
            w = float(vals[1]) or w
        depth_needed = max(ASR["user_area_depth"], ASR["user_area_min_m2"] / max(w, 0.8))
        zones["front"] = max(zones["front"], round(depth_needed, 2))
    # either-or zone groups (e.g. a bed needs at LEAST one long side reachable)
    zones_any = [[direction, _depth(key)] for direction, key in arch.get("zones_any", [])]
    return {"archetype": name, "zones": zones, "zones_any": zones_any,
            "faces": arch["faces"], "wall": arch["wall"]}
