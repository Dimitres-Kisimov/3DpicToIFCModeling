# Look-alike product retrieval — findings across three versions

*(v4.2 · Dimitres Kisimov · status: **working, and open for further development** —
this document records what was tried, what each version got wrong, and what the
next developer should do.)*

## The problem, stated honestly

Given a 3D object our AI engines generated from one photo, find a **visually
similar real product** to buy. This sounds like a search query; it is actually
a hard open research problem — general-purpose image embeddings (CLIP) measure
*"looks like the same kind of photo"*, not *"is the same kind of object"* —
and three iterations were needed to get trustworthy results. Each fix below
came from **looking at the output**, not from theory.

## Version 1 — category word + catalog thumbnails

**Approach.** Query = the item's category translated to German retail vocabulary
("stuhl", "bett", "hocker") + a CLIP-detected material modifier; match the
candidates' shop photos against the item's catalog thumbnail; similarity floor
0.55.

**What happened.**

| item | outcome |
|---|---|
| stool | acceptable: IKEA MARIUS at 0.71 |
| bed | **failed**: tiers included a fly screen, wallpaper and a floor lamp — sidebar products leaked through the shops' search pages |
| chair | lucky borderline: matched an armchair (POÄNG) without knowing why |

**Learning.** A price+image extractor over rendered shop pages has high recall
and no discipline — a **category gate** is mandatory (title must name the
category, else the photo must zero-shot-classify as it).

## Version 2 — original input photos + category/accessory gates

**Approach.** Match against the item's **original input photograph** (a real
product photo from the 5-AI benchmark) instead of AI-mesh thumbnails; add the
category gate and accessory negatives (a fitted sheet is titled
"Spann**bett**tuch" — substring matching betrays you).

**What happened.** Similarity jumped **+10–20 points** across all items
(stool 0.85–0.92, chair 0.81–0.82, bed → 0.77). But the chair exposed the
deeper flaw: the item is a **baroque upholstered armchair**, and v2 confidently
returned slim wooden dining chairs at 0.82 cosine. High score, wrong object
character.

**Learning.** CLIP image-image cosine on white-background product shots is
dominated by category and photo layout; it under-weights exactly what a human
sees first — upholstery, ornament, proportions. **The category label is not
the object.**

## Version 3 — sub-type awareness (photo + mesh geometry) + similarity-band tiers

**Approach.** Detect the item's *sub-type* two ways that must corroborate:
CLIP against sub-type prompts, and the **mesh's own proportions** — an armchair
is nearly as wide as tall (w/h≈0.85 vs ≈0.45 for a dining chair); a four-poster
bed is nearly as tall as wide (w/h≈1.3 vs ≥2 for a flat frame). The German
sub-type term becomes the query ("sessel barock", "bett antik", "barhocker
metall"); candidates from another sub-type family are rejected; lighting/
textiles are blacklisted (a floor lamp silhouettes like a bar stool); and tiers
are drawn **only from the top-similarity band** (within 0.12 of the best
match) — visual similarity is the primary criterion, price differentiates
within it.

**What happened (final study numbers).**

| item (engine, benchmark F) | detected sub-type | result |
|---|---|---|
| stool (TripoSG, F=0.99) | tall industrial metal stool | **0.90–0.92** — all true bar stools, incl. a powder-coated Tolix-style clone at 38.85 € landed |
| chair (SAM 3D) | ornate baroque armchair (mesh w/h=0.85) | **0.79–0.83** — all true armchairs (SKÅLBODA 75.98 €, ISMANTORP 105.98 €) |
| bed (TRELLIS, F=0.67) | ornate antique carved bed (w/h=1.27) | **≤0.77** — ornate tall-headboard metal beds; no closer retail analog exists at the scanned shops |

## Where it stands — and why this is marked "further development"

The pipeline is **reliable for common furniture forms** (stools, chairs,
standard beds, desks) and **honest about its limits**: for one-off ornate or
antique pieces (the Gothic bed), the closest purchasable product simply is not
very close, and the report says so with numbers instead of pretending.

Finding look-alikes at human quality remains **extensively hard**. The open
items, in priority order:

1. **Coverage**: free eBay + SerpAPI keys multiply the scanned market at zero
   code cost.
2. **Dimension enforcement**: parse product detail pages, reject outside ±15 %
   of the item's known real dimensions.
3. **Better embeddings**: DINOv2 (already powering the app's catalog
   retrieval) and embedding ensembles capture shape character better than
   CLIP alone; a small learned re-ranker over (CLIP, DINOv2, geometry) is the
   natural next step.
4. **Sub-type coverage**: more categories, finer prompts, learned sub-type
   classification instead of hand-written prompt lists.
5. **Human-in-the-loop**: the tool is a shortlist generator; the buyer's click
   on the product page is—and should remain—the final gate.

## Models used by the app (for the research paper)

- **Photo → 3D (the 5-AI comparison)**: TripoSR (runs locally, product
  default), and on cloud H200 GPUs: **TripoSG, TRELLIS, SAM 3D, InstantMesh** —
  187 internet photos, identical inputs, F-score@0.02 vs ABO ground-truth
  meshes. Mean F: **TripoSG 0.393** (best) · SAM 3D 0.368 · TRELLIS 0.347 ·
  InstantMesh 0.327 · TripoSR·rembg 0.295 · TripoSR·SAM2 0.278. Per-item
  winners vary — stool: TripoSG **0.99**; bed: TRELLIS 0.67; cabinet: SAM 3D
  0.73 — which is why this procurement study sources each item from its best
  engine. Full interactive gallery: `/gallery/index.html`; scores:
  `deliverable/cloud_gallery/cloud_scores.csv`.
- **Visual product matching**: OpenAI **CLIP ViT-B/32** (local, transformers).
- **Catalog retrieval**: **DINOv2** embeddings + FAISS index over the ABO
  library.
- **Photo preprocessing**: rembg / SAM2 segmentation, Ultralytics YOLO
  classification.
- **Placement**: Google **OR-Tools CP-SAT** under German ASR workplace rules.
- **BIM**: ifcopenshell (IFC4 read/write), xeokit (3D viewport).

*Everything in this document is reproducible: the three versions are tagged
v4.0.0 → v4.1.0 → v4.2.0, and each study JSON/XLSX is committed under
`docs/procurement_study/`.*
