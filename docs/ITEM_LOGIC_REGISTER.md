# Item Logic Register — every item, its distribution logic, its purpose

How distribution works: the room type + area suggest the item list (counts grow with space; Dense staffs offices toward the ASR legal floor). Placement then runs in five layers: special pre-passes claim their spots first (presentation front zone, door flanks), the CP-SAT solver places all free-standing items with per-item clearances and preferences (wall / corner / open-centre), companion items attach to their parents (in-front / on-top / beside / ring), and wall decor mounts at human heights. Anything that cannot sit legally is refused and reported — never forced.

> German-standard status (confirmed): no rule below conflicts with ASR. Values marked ASR are cited from the legal text (verbatim quotes live in rule_packs.py, verified against the BGN-hosted full texts); values marked STRICTER exceed the legal minimum on purpose; values marked PRACTICE are ergonomic design rules (Neufert, Panero, modern workplace standards) that ASR does not regulate — they operate inside the ASR envelope, never against it.

## 1 · Workstation cluster — where work happens

| Item | Distribution logic | Purpose / meaning | Standard basis |
|---|---|---|---|
| **Desk (1.40×0.70 m)** | Backs toward walls; reserves the ASR Bewegungsflaeche in front (>=1.5 m², >=1.0 m deep — scales with desk width) | The workstation itself; anchor of the whole cluster; count = ASR staffing rules | ASR A1.2 §5(3) staffing + 5.1.1/5.1.2 Bewegungsflaeche (cited) |
| **Office chair** | In front of its desk, tucked into the reserved zone, rotated to face it | The worker's seat; proves the desk is usable, not decorative | inside the ASR workstation zone |
| **Monitor** | On the desk surface, screen rotated toward the chair | Screen work; the facing rule = a human must be able to read it | PRACTICE (screen ergonomics) |
| **Laptop** | On the desk, hinge at the rear, screen to the sitter | Same as monitor; second surface slot | PRACTICE (screen ergonomics) |
| **Lamp (desk context)** | Third surface slot on the desk | Task lighting at the workplace | PRACTICE |
| **Waste bin** | Beside the desk, edge 0.10 m off the side panel; only a 0.05 m halo because it is EASILY MOVABLE (user rule); no desk in room -> opposite door flank from the coat rack | Arm's-reach disposal; the flank rule keeps coats away from garbage | PRACTICE; clearance honesty |
| **Partition (divider)** | One per ~4 desks in open plans, screening between desk pairs | Visual/acoustic privacy in Grossraum offices | PRACTICE (Grossraum acoustics) |

## 2 · Social rings — where people gather

| Item | Distribution logic | Purpose / meaning | Standard basis |
|---|---|---|---|
| **Table (dining/work)** | Prefers OPEN floor when ringed (social pieces do not hide at walls) | The gathering point; hosts rings and appliances | PRACTICE; ASR routes still enforced around it |
| **Chair (regular, 0.45×0.52 m)** | Rings its table radially at chord-safe spacing, facing it, skipping any occupied front sector; never used as an office chair (user rule) | Dining/meeting seating — human bodies around a shared surface | PRACTICE (Neufert seating circulation) |
| **Stool** | Rings the coffee table or table, same petal maths | Casual perching; fills the ring where chairs would crowd | PRACTICE |
| **Sofa** | Back flush to a wall (perimeter set) | The lounge core; couches stay FIRST in every living list (user-approved) | PRACTICE |
| **Coffee table** | 0.46 m in front of the sofa (the '18-inch rule' — shin clearance) | Within reach of a seated person | PRACTICE (Panero 0.46 m) |
| **Armchair** | IN A ROW (user rule): two side by side facing the same way; four as two opposed pairs facing each other; side table with the cluster's plant rides along; placed wherever a legal gap exists, walkways kept clear by the solver | Human seating groups — breakout zones, reception waiting | PRACTICE |
| **Side table** | Directly beside its armchair | A cup/book within arm's reach of whoever sits | PRACTICE |

## 3 · Storage — the walls' occupants

| Item | Distribution logic | Purpose / meaning | Standard basis |
|---|---|---|---|
| **Cabinet (1.2×0.6×1.8 m)** | Back flush to wall; count scales ~1 per 22 m² | General storage / wardrobe; wall placement keeps floor routes free | PRACTICE; keeps ASR routes clear |
| **Bookshelf** | Wall-flush, ~1 per 30 m² | Reference storage | PRACTICE |
| **Filing cabinet** | Wall-flush, workspace-heavy rooms | Document storage — the 'workspace' room type's identity | PRACTICE |
| **Locker** | Wall-flush, ~1 per 26-34 m² | Personal storage (German offices expect them) | PRACTICE |
| **Server rack** | Wall-flush, workspace >52 m² | IT infrastructure for technical workrooms | PRACTICE |
| **Fridge** | Wall-flush perimeter, kitchens + break rooms >14 m² | Cold storage; belongs to kitchen / Pausenraum only (user rule) | PRACTICE |

## 4 · Appliances — on surfaces, never the floor

| Item | Distribution logic | Purpose / meaning | Standard basis |
|---|---|---|---|
| **Microwave** | ON the table/counter (on_top link, elev ~0.74 m) in kitchens and break rooms — never floor-placed (user rule) | Heating food at working height | PRACTICE (working height) |
| **Coffee machine** | On the table in break rooms / kitchens | The social magnet of every Pausenraum | PRACTICE |
| **Water dispenser** | Perimeter; offices >50 m², break rooms >12 m² | Hydration point (workplace welfare) | workplace welfare (ArbStaettV spirit) |
| **Printer** | On its stand (never the ground — user rule), wall-side, 1 per ~8 workstations, second >75 m² | Shared MFP; central so everyone reaches it | PRACTICE |

## 5 · Presentation kit — the lecture geometry

| Item | Distribution logic | Purpose / meaning | Standard basis |
|---|---|---|---|
| **Presentation screen** | Front wall, centre, mounted at 0.80 m | The projection surface everyone must see | PRACTICE (DIN-style ergonomics) |
| **Whiteboard** | Front wall left of the screen, 0.90 m; becomes the projector's target only when no screen exists | Writing surface at standing-arm height | PRACTICE |
| **Projector** | CEILING at 2.2 m (ASR headroom kept below), throw distance 1.2× image width, lens aimed at the display — in ANY room type | Projects onto its display; the aim is a machine-checked throws_onto link | ASR A1.8 headroom >=2.00 m — ours 2.20 (STRICTER) |
| **Lectern** | Front zone, rotated 180° to face the audience | The speaker's station | PRACTICE |
| **Flipchart** | Beside the lectern | The speaker's second surface, at hand | PRACTICE |
| **Chair rows (audience)** | Parallel rows CENTRED on the display axis (partial last row too), facing it; first row at ~1.5× image width; row pitch >=0.90 m (ASR aisle) | Everyone sees the screen at legal viewing/egress spacing (user rule: 'never forget this') | row pitch 0.90 m = ASR A1.8 Tab.2 (0.875 rounded STRICTER); viewing distance PRACTICE |

## 6 · Entry & safety — the door's neighbourhood and the law's items

| Item | Distribution logic | Purpose / meaning | Standard basis |
|---|---|---|---|
| **Coat rack** | Wall immediately left or right of the door | Where a human hangs a coat on entry (user rule) | PRACTICE |
| **Fire extinguisher** | Wall-mounted 1.00 m + a HARD 0.90 m access strip in front that no furniture may enter, at any density | ASR A2.2 — freely accessible at all times | ASR A2.2; grip 1.00 m inside the 0.80-1.20 m band |
| **First-aid cabinet** | Wall-mounted 1.35 m + the same protected 0.90 m access strip | Eye-level emergency access, never blocked (ASR A4.3) | presence per ASR A4.3; height PRACTICE (eye level) |
| **Phone booth** | Free-standing box; offices >62 m² | Call privacy in open plans (modern workplace standard) | PRACTICE |

## 7 · Ambience & residential

| Item | Distribution logic | Purpose / meaning | Standard basis |
|---|---|---|---|
| **Planter** | CORNERS (solver drives both nearest-wall gaps to zero) or queued along the wall when corners fill — never mid-room (user rule) | Greenery without stealing circulation | PRACTICE; keeps ASR routes clear |
| **Lamp (floor)** | Free accent near seating | Ambient light in living/quiet rooms | PRACTICE |
| **Bed (1.60×2.05 m)** | Listed FIRST in bedrooms (essentials-first: the solver keeps it over accents); needs one long side reachable | The bedroom's reason to exist | residential — ASR n/a (A1.8 envelope applied anyway) |
| **Mirror** | Left wall, face height 1.50 m | Dressing check — full length at human eye line | PRACTICE |
| **Clock** | 2.05 m high on the wall the SEATED person faces (computed from the chair's gaze) | Readable from the working position | PRACTICE |
| **Picture frame** | Wall at 1.55 m eye level, avoiding doors and other decor | Decor at gallery height | PRACTICE |

## Cross-cutting rules

Cross-cutting rules: clearances are per-item (default 0.15 m; seating 0.10; storage 0.20; the movable waste bin 0.05) and unknown/custom categories get a footprint-derived gap automatically. Routes follow ASR A1.8 by occupancy (0.90 / 1.00 / 1.20 m) with a 0.90 m person-path walked to every placed item — items only reachable through narrower gaps are reported UNREACHABLE. Door swings keep 0.90-1.2 m clear. Density tiers (Light / Medium / Dense) scale counts but never breach the legal envelope. Every companion placement is exported as a machine-checked link (in_front_of, on_top_of, beside, ring_around, throws_onto, audience_row_facing, door_flank, mounted_on, faces).
