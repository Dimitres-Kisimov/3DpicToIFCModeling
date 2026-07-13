# ASR Compliance — Arbeitsstättenrichtlinie in the Layout Engine

**Status: implemented and DEFAULT for workplace rooms** (office, workspace, meeting) since 2026-07-13.
Kill-switch: `SCS_ASR=0` (restores the previous Neufert-only behaviour).
Verified against the published rule texts (sources below), not summaries.

## What the regulation is

The **Arbeitsstättenverordnung (ArbStättV)** is the German workplace ordinance; the
**Technischen Regeln für Arbeitsstätten (ASR)** concretize it. The layout-relevant
rules for offices are **ASR A1.2** (Raumabmessungen und Bewegungsflächen) and
**ASR A1.8** (Verkehrswege).

## Implemented rules, with exact citations

| Rule | Legal text | Where enforced |
|---|---|---|
| **Grundfläche (legal minimum)** — *"mindestens 8 m² für einen Arbeitsplatz zuzüglich mindestens 6 m² für jeden weiteren"* | ASR A1.2 sect. 5 Abs. 3 | `smart_furnish`: hard cap on workstations per room — **no density tier can exceed 1 + (area − 8 m²)/6 m²** |
| **Bewegungsfläche am Arbeitsplatz** — *"mindestens 1,50 m²"*, *"Tiefe und Breite … mindestens 1,00 m"* | ASR A1.2 sect. 5.1.1 Abs. 2 / 5.1.2 | `placement_profile('desk')`: the desk's user-side clear zone is ≥ 1.00 m deep **and** scales so width × depth ≥ 1.50 m² (a 1.40 m desk gets a 1.07 m zone). The CP-SAT solver treats this zone as inviolable; the 2D editor draws it and blocks drags into it |
| **Büroraum-Richtwerte** — Zellenbüro *"8 bis 10 m² je Arbeitsplatz einschließlich Möblierung und anteiliger Verkehrsflächen"*, Großraumbüro *"12 bis 15 m²"* | ASR A1.2 sect. 5 Abs. 4 | Staffing targets per density tier: **Medium** staffs at the Richtwert (10 m²/AP cellular, 12.5 m²/AP for rooms > 50 m²); **Dense** staffs down to the *legal* floor of Abs. 3, never below; **Light** staffs well above |
| **Verkehrswege widths** — ≤ 5 persons 0,90 m · ≤ 20 persons 1,00 m · ≤ 100 persons 1,20 m | ASR A1.8 sect. 4.2 Tabelle 2 | Rule-pack `min_aisle` = 1.00 m for workplace rooms (covers ≤ 20 users/room); the A3 circulation check walks a person-width path to every item |
| **Gänge zu persönlich zugewiesenen Arbeitsplätzen** — 0,60 m | ASR A1.8 Tabelle 2, Zeile 8 | Recorded in the pack (`ws_access`); enforced **more strictly** by the circulation walk, which requires a 0.90 m path to every placed item — items only reachable through a narrower gap are reported as *unreachable* |
| **Door keep-clear** (egress spirit) | ASR A1.8 / A2.3 | 1.2 m keep-clear at every door, doorless opening and wall gap — nothing blocks a walking path (see the walking-path engine) |

## Interaction with density tiers

Light / Medium / Dense staff office rooms **within** the ASR envelope:

| Room | Light | Medium | Dense (= legal floor) |
|---|---|---|---|
| 36 m² office | 1 WS | 3 WS (12 m²/AP) | 5 WS (7.2 m²/AP — Abs. 3 allows 8+4×6 = 32 m² ≤ 36) |
| 80 m² office | 3 WS | 6 WS (13.3 m²/AP, Richtwert Großraum) | 10 WS (8 m²/AP, ≤ legal cap 13) |

## Explicitly out of scope (documented, not silently skipped)

- **Lichte Raumhöhe** (A1.2 sect. 5.2: ≥ 2.50 m up to 50 m² …): most IFC exports carry no
  reliable ceiling data per room; not evaluated.
- **ASR A2.3 Fluchtwege**: full escape-route calculation (lengths, capacities) is a
  fire-safety analysis beyond furniture layout; the door/passage keep-clears cover the
  layout-side obligations only.
- **ASR A3.4 Beleuchtung / Tageslicht**: lighting is outside geometric layout.

## Sources

- [ASR A1.2 sect. 5 full text (BGN Branchenwissen)](https://vorschriften.bgn-branchenwissen.de/daten/tr/asr_a1_2/5.htm)
- [ASR A1.8 sect. 4 Tabelle 2 (BGN Branchenwissen)](https://vorschriften.bgn-branchenwissen.de/daten/tr/asr_a1_8/4.htm)
- [BAuA — ASR A1.2 official page](https://www.baua.de/DE/Angebote/Regelwerk/ASR/ASR-A1-2)
- Implementation: `backend/python-scripts/rule_packs.py` (ASR constants + overlays),
  `backend/python-scripts/populate_building.py` (office staffing).
