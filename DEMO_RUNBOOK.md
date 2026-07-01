# 🎬 SCS Demo Runbook — Presentation Day

**Goal of the demo:** show *photo → AI 3D → BIM-compliant furniture → populated building*, backed by a
real 5-model benchmark. Everything below is local and reliable — **no cloud GPU, no internet needed.**

> **The one thing to remember:** the live app's "Generate" uses fast **object detection + primitives**
> (runs on CPU, always works). The photorealistic **AI meshes** (TripoSR / SAM 3D / TRELLIS…) are shown
> in the **gallery** and used in the **building** — those were generated ahead of time. So nothing in the
> live demo depends on a GPU finishing on stage.

---

## ✅ 30 MINUTES BEFORE (pre-flight — do this once, calmly)

Open a terminal in the project folder (`C:\Users\dimik\3DpicToIFCModeling`) and run these **one at a time**.
Each should print what's noted. If one fails, see **🛟 Fallbacks** — you still have a full demo.

```bash
# 1) Start the app (leave this terminal open the whole time)
npm start
#    -> "Server running on http://localhost:3000"   ... then open that URL in Chrome.

# 2) In a SECOND terminal, health check:
curl http://localhost:3000/api/health
#    -> {"success":true,"message":"Server is running"}

# 3) IMPORTANT — warm up + pre-generate (the generate step is ~60 s on the GPU, longer the FIRST
#    time because it downloads model weights). Do this now so weights are cached and you have a
#    ready result:
#    In the browser at localhost:3000 -> "Use Sample" -> "Generate 3D".
#    First run may take 2-5 min (downloading DETR + Depth-Anything + TripoSR weights); after that
#    each generate is ~60 s. Run it 2x so the second is warm. LEAVE the last result on screen.

# 4) Open the model-comparison gallery (double-click, or):
python deliverable/cloud_gallery/serve.py
#    -> a browser tab opens with 5 AI models spinning side by side.

# 5) Confirm the building files exist (the "at scale" act):
#    deliverable/building/SCS_Office_Complex/building_summary.json   (47 instances / 9 meshes)
#    deliverable/building/SCS_Office_Complex/SCS_Office_Complex.ifc   (~14 MB BIM file)
```

If all five worked, **you are ready.** Keep the app terminal and both browser tabs open.

---

## 🎬 THE DEMO (3 short acts, ~8 minutes total)

### ACT 1 — Live: a photo becomes BIM furniture  *(~3 min, the "wow")*
**Browser tab:** `http://localhost:3000`

> **⏱️ The generate takes ~60 seconds. Don't stand in silence — narrate the pipeline while it runs
> (that IS the impressive part).** Best approach: **start ONE live generate to prove it's real, talk
> through it for the 60 s, THEN show the pre-generated result from pre-flight** so you're not waiting twice.

1. Click **"Use Sample"** (or drag in a furniture photo) → **"Generate 3D"**. While it runs (~60 s), say:
   > *"Right now it's doing four things: **detecting** the furniture with an object detector, **measuring
   > its real-world size** from monocular depth, **generating** a full 3D mesh with the TripoSR AI model,
   > and **matching** it against a real catalogue for accuracy. One photo in — a dimensioned 3D object out."*
2. When the model appears: **click a piece** in the 3D view, then **Snap to Ground / Reset** —
   *"a reviewer can hand-adjust any placement."*
3. Click **"Export IFC"** → *"and it exports as a standard BIM file — opens directly in Revit or ArchiCAD."*

> **Say to close Act 1:** *"No manual CAD modelling — one photo becomes a measured, BIM-ready object."*

### ACT 2 — The research: 5 AI models, measured  *(~2 min, credibility)*
**Browser tab:** the gallery (from pre-flight step 4)

1. Scroll the grid — every row is one furniture type; each column a different AI model, all spinning.
2. Point at the F-scores. **Say:** *"We benchmarked five state-of-the-art AI models against real BIM
   meshes on identical inputs. TripoSG scored best overall (0.393), SAM 3D second (0.368) — but no single
   model wins every category, and all trail a real mesh ~2.5×. That's why our system is built to pick the
   best model per item, and to prefer real/retrieved geometry where it matters."*

### ACT 3 — At scale: a whole building  *(~2 min, the vision)*
**Terminal** (or show the pre-built files):

```bash
python backend/python-scripts/build_building.py deliverable/building_spec_example.json
```
- **Say:** *"The same room logic scales to a whole complex. This spec — two floors, five rooms — populates
  automatically into **47 furniture instances built from just 9 unique meshes**. That reuse is what lets a
  full building render smoothly and export to a single BIM file"* — open
  `deliverable/building/SCS_Office_Complex/building_summary.json` to show the numbers, and mention
  `SCS_Office_Complex.ifc` (the 14 MB BIM export) loads in any IFC viewer / xeokit.

**Close with:** *"So: one photo per item → measured-best AI 3D → human-reviewable placement → BIM-compliant
IFC → a whole populated building. All of it reproducible and license-clean."*

---

## 🛟 IF SOMETHING BREAKS (you always have a full demo)

| If this fails… | Do this instead |
|---|---|
| **App won't start** (`npm start` errors) | Run `npm install` once, then `npm start` again. Still stuck? Skip Act 1; lead with the **gallery** (Act 2) + **building files** (Act 3) — both are standalone. |
| **"Generate" is slow (~60 s) or the room goes quiet** | Expected — narrate the 4-step pipeline while it runs (see Act 1). If it genuinely errors: you have the **pre-generated result from pre-flight** already on screen — just talk to that. Never wait in silence. |
| **First generate takes minutes** | It's downloading model weights (one-time). This is why pre-flight step 3 matters — do it well before the audience so weights are cached. |
| **Gallery won't open via serve.py** | Double-click `deliverable\cloud_gallery\serve.bat`. Or just open `deliverable\cloud_gallery\index.html` in Chrome (it's fully offline — model-viewer is bundled). |
| **No internet in the room** | Doesn't matter — everything here is local/offline. |
| **Projector/second screen issues** | Zoom the browser to 110–125% (Ctrl +) so furniture + scores read from the back. |

---

## 🧹 AFTER THE DEMO
- Stop the app: `Ctrl + C` in the `npm start` terminal.
- Nothing else to clean up. All outputs stay in `deliverable/`.

---

### Quick reference — the only commands you need
```bash
npm start                                                   # the app  -> localhost:3000
python deliverable/cloud_gallery/serve.py                   # the 5-model gallery
python backend/python-scripts/build_building.py deliverable/building_spec_example.json   # the building
```
