# Building Fleet — Provenance & Licensing

Every IFC in the fleet, where it came from, and what its license allows.
Rule: nothing enters the fleet without a verified, compatible license.

| Building | Source | License | Derivatives OK? | In git? |
|---|---|---|---|---|
| Duplex Apartment (sample) | buildingSMART / Common BIM Files lineage | open sample data | yes | yes |
| Duplex round-trip, Kleine Wohnung, Schependomlaan, rue Marc-Antoine, small house | project uploads (community/open BIM sample files) | open sample data | yes | yes |
| KIT Institute (Buerogebaeude) | [KIT IFC Examples](https://www.ifcwiki.org/index.php?title=KIT_IFC_Examples) | **"for unrestricted use"** (KIT/IAI) | yes | yes |
| Smiley West | [KIT IFC Examples](https://www.ifcwiki.org/index.php?title=KIT_IFC_Examples) | **"for unrestricted use"** (KIT/IAI) | yes | yes |
| SCS Tower (7F, synthetic) | derived from Kleine Wohnung plate via `make_tower_ifc.py` | inherits source (open) | — | yes |
| HHS Office institute | [opensourceBIM/IFC-files](https://github.com/opensourceBIM/IFC-files) | **CC BY-ND** | **NO** — never stack/modify-and-redistribute this one; populated outputs are internal demo artefacts | yes |
| **210 King — Autodesk Toronto office** | [DURAARK research datasets](http://duraark.eu/data-repository/) mirrored at TIB (`tib.eu/data/duraark/BuildingData/03_IFC_E57/Autodesk_210-King_ifc.zip`) | **CC0** — verified via the [re3data registry entry](https://www.re3data.org/repository/r3d100012506) (unrestricted use, no attribution required) | yes | **no — 147 MB exceeds GitHub's 100 MB file limit.** Re-fetch from the TIB URL above; the registry entry (`data/buildings/manifest.json`) is committed. |

| NBU Office Building | DURAARK/TIB (`NBU_OfficeBuilding_ifc.zip`) | **CC0** (same registry verification) | yes | yes |
| SCS Office Tower 8F / Smiley Tower 8F / Duplex Tower 7F | synthesized via `make_tower_ifc.py` from KIT Institute / KIT Smiley West / duplex plates | inherit sources (KIT: unrestricted; duplex: open sample) | — | yes |
| HHS Office institute | see above | CC BY-ND | NO | yes |

## Rejected / skipped candidates (and why)

- **Holter_Tower_10.ifc** (177 MB tower): only available source is a personal Dropbox
  link listed in a third-party index — provenance and license unverifiable → skipped.
- **Revit Advanced Sample (Ifc4_Revit_ARC)**: a house; zero IfcSpace objects → useless
  for room population.
- **AdvancedProject (bim-whale samples)**: 10 storeys but only 8 whole-apartment
  spaces — no room granularity.
- **HiTOS (Tromsø University College)**: FOUND at the TIB DURAARK mirror (CC0) — but its
  architecture model is schema IFC2X2_FINAL (2006), unsupported by the geometry kernel;
  only the space-less MEP models parse. Registered as unusable, kept for the record.

## Notes

- DURAARK ("Durable Architectural Knowledge", EU FP7) published real-world BIM
  datasets; the repository is offline since 2020-02-13 but TIB (Leibniz Information
  Centre for Science and Technology) still serves the files. re3data records the
  repository's data license as **CC0**.
- 210 King Street is Autodesk's own Toronto office ("living laboratory",
  [Autodesk Research paper](https://damassets.autodesk.net/content/dam/autodesk/research/publications-assets/pdf/210-king-street-a.pdf)) —
  6 office levels (up to 53 rooms/level) + basement + 4-level annex, 261 spaces,
  13,638 products, imperial units (unit-scale handled by the pipeline).
