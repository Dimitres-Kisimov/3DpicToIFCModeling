# TripoSR Cleanup Algorithm + Shape Test List

**Date:** 2026-07-06 · Branch: `redesign-generator-ui`

## 1. Spike / hole / debris removal algorithm  (`clean_and_optimize.py`)

Removes the random lines/spikes and holes that TripoSR emits. Each stage is guarded (a failure
degrades to pass-through, never crashes).

| Stage | What it removes / does | Tool |
|-------|------------------------|------|
| **1. Debris + spike removal** | split into connected components; **drop any component < 0.6% of total faces** → deletes stray lines, spikes, floating fragments; keeps body + legs | trimesh `split` |
| **2. Watertight repair** | fills **holes**, joins nearby components, fixes non-manifold + self-intersections | **pymeshfix** (MeshFix, `joincomp=True`) |
| **3. Smoothing** | volume-preserving surface smooth (won't shrink like Laplacian) | trimesh `filter_taubin` ×10–12 |
| **4. Decimation** | reduce to a face budget (smaller/faster) | **fast_simplification** (quadric) |
| **5. Ground + centre** | sit flat on Y=0, centred | trimesh |
| color | original PBR `baseColorFactor` captured before rebuild, re-applied after | trimesh visual |

**Modes:** default (repair, keeps detail) · `--solidify` (voxel remesh → one watertight solid, blobs
detail). **IFC-level:** `optimize_ifc.py` runs the same on every `IfcTriangulatedFaceSet` inside an IFC.

**Honest limit:** removes junk + closes holes + smooths, but **cannot reconstruct geometry TripoSR
never generated** (e.g. a missing 5-star wheelbase). That's a generation problem → stronger model.

**Verified (office chair):** 85,500 → 14,998 faces (−82.5%), 2.8 MB → 670 KB (−76.7%), valid IFC4.

## 2. Shape test list — run each through TripoSR

The 2nd-part (room/building population) catalog = **17 categories**:

| Item | IFC class | Item | IFC class |
|------|-----------|------|-----------|
| bookshelf | IfcFurniture | monitor | IfcAudioVisualAppliance |
| cabinet | IfcFurniture | office_chair | IfcChair |
| clock | IfcFurniture | picture_frame | IfcFurniture |
| coffee_table | IfcTable | planter | IfcFurniture |
| desk | IfcTable | side_table | IfcTable |
| filing_cabinet | IfcFurniture | sofa | IfcFurniture |
| lamp | IfcFurniture | stool | IfcFurniture |
| laptop | IfcAudioVisualAppliance | table | IfcTable |
| mirror | IfcFurniture | | |

Plus **bed** and **chair** from the 10 benchmarked asset-library items:
`bed, bookshelf, cabinet, chair, desk, lamp, office_chair, sofa, stool, table`.

### Expected TripoSR difficulty (from the benchmark)
- **Easy / clean:** stool (0.99), table (0.81), bookshelf, cabinet, planter, picture_frame — simple boxy/solid shapes reconstruct well.
- **Hard for TripoSR:** office_chair, chair, sofa, desk — **thin legs + wheelbases + hidden backs** are where TripoSR fails and cleanup can't save it.
