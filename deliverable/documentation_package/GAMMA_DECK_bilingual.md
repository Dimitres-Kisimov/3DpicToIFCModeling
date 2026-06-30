<!--
GAMMA IMPORT INSTRUCTIONS
1. Gamma.app → Create new → Import → Paste text / Markdown → paste this whole file.
2. Each slide is separated by "---". Keep "Generate" on a clean template.
3. Images: each slide ends with `Image: doc_assets/<file>.png`. After Gamma builds the deck,
   drag that image from the doc_assets/ folder onto the matching slide (Gamma can't pull local files).
4. Bilingual: each slide has a 🇩🇪 Deutsch block and a 🇬🇧 English block — Gamma renders them as two
   columns nicely. Delete one language if you want a single-language deck.
5. Presenters: Part 1 = Gülriz (analytical), Part 2 = Dimitrius (technical).
-->

# Vom Foto zum BIM-Modell / From Photo to BIM Model

KI-gestützte Raummöblierung & Foto→3D-Pipeline für IFC/BIM
AI room population & photo→3D pipeline for IFC/BIM

Gülriz · Dimitrius — 23. Juni 2026

Image: doc_assets/results_plate.png

---

# Zusammenfassung / Executive Summary

**🇩🇪 Deutsch**
- Retrieval-+-Layout-Pipeline: Foto → sauberes Katalog-Mesh → KI-Raumlayout → IFC/BIM-Export
- 400 echte Produktmodelle (ABO, CC-BY-4.0), Matching via DINOv2 + FAISS
- Funktionales Layout auf den Zentimeter verifiziert
- Einzelbild-3D-Grenze gemessen: Präzision ~0,81 ≫ Recall ~0,09
- €0 Lizenzgebühren · ~€185/Monat · <€0,02/Raum

**🇬🇧 English**
- Retrieval-+-layout pipeline: photo → clean catalog mesh → AI room layout → IFC/BIM export
- 400 real product models (ABO, CC-BY-4.0), matched via DINOv2 + FAISS
- Functional layout verified to the centimetre
- Single-view 3D ceiling measured: precision ~0.81 ≫ recall ~0.09
- €0 royalties · ~€185/month · <€0.02/room

---

# Teil 1 — Analyse & Ansatz / Part 1 — Analysis & Approach

Gülriz

---

# Das Problem / The Problem — Single-view limits

**🇩🇪 Deutsch**
- Einzelbild-Rekonstruktion ist mathematisch unterbestimmt
- Asymmetrische Beine (kein Symmetrie-Prior)
- Halluzinierte Rück-/Unterseite
- Nicht-deterministisch: gleiches Foto, andere Meshes
- Verrauschte Topologie · Mesh ≠ semantisches IFC

**🇬🇧 English**
- Single-view reconstruction is mathematically ill-posed
- Asymmetric legs (no symmetry prior)
- Hallucinated back / underside
- Non-deterministic: same photo, different meshes
- Noisy topology · mesh ≠ semantic IFC

---

# Ziel & Umfang / Objective & Scope

**🇩🇪 Deutsch**
- Bild→IFC-Pipeline für Büromöbel (kein Gebäude-BIM)
- Einzelraum, 10–15 Möbelstücke, funktionales Layout
- Nur kommerziell sichere Werkzeuge (keine AGPL, keine Umsatzgrenzen)
- Saubere, wiederholbare Meshes über einen Katalog

**🇬🇧 English**
- Image→IFC pipeline for office furniture (not building BIM)
- Single room, 10–15 items, functional layout
- Only commercially-safe tools (no AGPL, no revenue caps)
- Clean, repeatable meshes via a catalog

---

# Energie & Kosten / Energy & Cost

**🇩🇪 Deutsch**
- Strom (Baden-Württemberg 2026): €0,25/kWh
- GPU ~0,45–0,6 kW × 24/7 ≈ 324–432 kWh/Monat → €80–108
- Hetzner GEX44 €184/Monat · On-Prem ~€175/Monat
- Pro Raum ~€0,019 bei 10.000 Räumen/Monat
- Lizenzgebühren €0 – für immer

**🇬🇧 English**
- Electricity (Baden-Württemberg 2026): €0.25/kWh
- GPU ~0.45–0.6 kW × 24/7 ≈ 324–432 kWh/month → €80–108
- Hetzner GEX44 €184/month · on-prem ~€175/month
- Per room ~€0.019 at 10,000 rooms/month
- Licence royalties €0 — forever

---

# KI-Ansätze / AI Approaches at a Glance

**🇩🇪 Deutsch**
- Retrieval-first: nur bei Katalog-Miss generieren
- Retrieval: DINOv2 / SigLIP 2
- Erkennung + Segmentierung: Grounding DINO + SAM 2.1
- Tiefe/Maßstab: Depth Anything V2 Small
- Generative Reserve: SAM 3D / Stable Fast 3D / TRELLIS / TripoSR

**🇬🇧 English**
- Retrieval-first: generate only on a catalog miss
- Retrieval: DINOv2 / SigLIP 2
- Detection + segmentation: Grounding DINO + SAM 2.1
- Depth/scale: Depth Anything V2 Small
- Generative fallback: SAM 3D / Stable Fast 3D / TRELLIS / TripoSR

---

# HuggingFace & Lizenzen / HuggingFace & Licences

**🇩🇪 Deutsch**
- Sichere HF-Modelle: Apache-2.0 / MIT / SAM-Lizenz
- Fallen: Hunyuan3D-2 (EU ausgeschlossen), YOLOv8 (AGPL)
- Depth Anything Base/Large (CC-BY-NC – nur Small ist Apache)
- Stable Fast 3D: Grenze bei $1 Mio. Umsatz
- Prinzip: SCS verkauft Ergebnisse, nicht Gewichte

**🇬🇧 English**
- Safe HF models: Apache-2.0 / MIT / SAM license
- Traps: Hunyuan3D-2 (EU-excluded), YOLOv8 (AGPL)
- Depth Anything Base/Large (CC-BY-NC — only Small is Apache)
- Stable Fast 3D: $1M revenue cap
- Principle: SCS sells outputs, not weights

---

# Der Strategiewechsel / The Pivot — Retrieval + Layout

**🇩🇪 Deutsch**
- Statt halluzinieren: Foto → nächstes sauberes Katalog-Mesh
- DINOv2 + FAISS über 400 echte ABO-Modelle
- Deterministisch, professionell, wiederholbar
- Generierung nur als Reserve

**🇬🇧 English**
- Instead of hallucinating: photo → nearest clean catalog mesh
- DINOv2 + FAISS over 400 real ABO models
- Deterministic, professional, repeatable
- Generation only as a fallback

Image: doc_assets/fig00_overview.png

---

# Teil 2 — System & Ergebnisse / Part 2 — System & Results

Dimitrius

---

# Systemüberblick / System Overview

**🇩🇪 Deutsch**
- Foto → Objekttabelle → Layout → IFC/BIM + 3D-Betrachter
- Alle Ergebnisse auf einen Blick

**🇬🇧 English**
- Photo → object table → layout → IFC/BIM + 3D viewer
- All results at a glance

Image: doc_assets/results_plate.png

---

# Der 400-Objekt-Katalog / The 400-item Catalog

**🇩🇪 Deutsch**
- Amazon Berkeley Objects: 400 echte Modelle, 8 Kategorien × 50
- Lizenz CC-BY-4.0, echte metrische Maße
- Retrieval: DINOv2 + FAISS
- Einzelauswahl mit farbigen Vorschaubildern

**🇬🇧 English**
- Amazon Berkeley Objects: 400 real models, 8 categories × 50
- Licence CC-BY-4.0, real metric dimensions
- Retrieval: DINOv2 + FAISS
- Per-item picker with colored previews

Image: doc_assets/catalog_office_chair.png

---

# Layout-Engine — 3 Schichten / Layout Engine — 3 Layers

**🇩🇪 Deutsch**
- Schicht 1: Regelpakete (Neufert 6 m²/AP, ADA 0,915 m, Tür 0,90 m)
- Schicht 2: CP-SAT-Packung, 10-cm-Raster, Wand-Affinität
- Schicht 3: funktionale Verankerung + Sitzausrichtung
- Auf den Zentimeter verifiziert

**🇬🇧 English**
- Layer 1: rule packs (Neufert 6 m²/ws, ADA 0.915 m, door 0.90 m)
- Layer 2: CP-SAT packing, 10 cm grid, wall-affinity
- Layer 3: functional anchoring + seat-facing
- Verified to the centimetre

Image: doc_assets/fig01_office_single_montage.png

---

# Layout in Aktion / Layout in Action

**🇩🇪 Deutsch**
- Drei Arbeitsplätze: Stühle zum Schreibtisch
- Monitore auf den Tischen, Lager an den Wänden
- Mitte frei für Zirkulation

**🇬🇧 English**
- Three workstations: chairs face desks
- Monitors on desks, storage on walls
- Centre open for circulation

Image: doc_assets/fig02_office_team_montage.png

---

# Randbedingungen & Barrierefreiheit / Constraints & Accessibility

**🇩🇪 Deutsch**
- Säule + Türfreiraum werden respektiert
- ADA-Modus: breitere Gänge

**🇬🇧 English**
- Column + door keep-clear respected
- ADA mode: wider aisles

Image: doc_assets/fig03_office_obstacles_montage.png  (and fig04_office_ada_montage.png)

---

# Verallgemeinerung / Generalization

**🇩🇪 Deutsch**
- Wohnzimmer-Regelpaket (andere Gruppen)
- Dichter Arbeitsraum (mehr Lager, breitere Gänge)

**🇬🇧 English**
- Living-room rule pack (different groups)
- Dense workspace (more storage, wider aisles)

Image: doc_assets/fig05_living_room_montage.png  (and fig06_workspace_dense_montage.png)

---

# Kapazitätsgrenze / Capacity Boundary

**🇩🇪 Deutsch**
- 4×3 m → 2 · 5×4 m → 3 · 6×5 m → 4 · 8×6 m → 6 Arbeitsplätze
- Skaliert mit der Fläche; sonst „nicht machbar"

**🇬🇧 English**
- 4×3 m → 2 · 5×4 m → 3 · 6×5 m → 4 · 8×6 m → 6 workstations
- Scales with area; otherwise reports "infeasible"

Image: doc_assets/fig08_capacity_sweep.png

---

# Die Web-App / The Web App

**🇩🇪 Deutsch**
- Flask + xeokit (WebGL)
- Auswählen → Generieren → Vorschau → Export
- Export: CSV / GLB / IFC4
- Flüchtig: nichts gespeichert bis Export

**🇬🇧 English**
- Flask + xeokit (WebGL)
- Pick → Generate → preview → Export
- Export: CSV / GLB / IFC4
- Ephemeral: nothing saved until export

---

# Genauigkeit — Methode / Accuracy — Method

**🇩🇪 Deutsch**
- ABO-Meshes als Ground Truth
- Foto rendern → rekonstruieren → vergleichen
- Chamfer-Distanz + F-Score (τ=0,02), Multi-Seed-ICP
- Kalibrierung: Identität F=1,0 · anderes Objekt F=0,18

**🇬🇧 English**
- ABO meshes as ground truth
- Render photo → reconstruct → compare
- Chamfer distance + F-score (τ=0.02), multi-seed ICP
- Calibration: identity F=1.0 · different object F=0.18

---

# Genauigkeit — Ergebnis / Accuracy — Result

**🇩🇪 Deutsch**
- TripoSR: Mittel Chamfer 0,169 · F-Score 0,155
- Präzision ~0,81 ≫ Recall ~0,09
- Sichtbare Fläche gut, Rückseite fehlt → die Einzelbild-Grenze

**🇬🇧 English**
- TripoSR: mean Chamfer 0.169 · F-score 0.155
- Precision ~0.81 ≫ recall ~0.09
- Visible surface good, back missing → the single-view ceiling

Image: doc_assets/fig09_accuracy_triposr.png

---

# Ergebnisse & Ausblick / Outcomes & Roadmap

**🇩🇪 Deutsch**
- Funktionierendes Retrieval-+-Layout-System
- Einzelbild-Grenze gemessen, nicht nur behauptet
- Nächste: 4-Wege-Vergleich, Foto→Retrieval, Multi-View, Maßstab, Desktop-App

**🇬🇧 English**
- Working retrieval-+-layout system
- Single-view limit measured, not just asserted
- Next: 4-way bake-off, photo→retrieval, multi-view, scale, desktop app
