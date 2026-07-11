# HuggingFace image-to-3D Census — 2026-07-11

**Question answered:** across the ENTIRE HuggingFace `image-to-3d` tag, how many
models qualify under our rules (royalty-free commercial, EU-allowed, open
weights, single-image → 3D object mesh), and who are the serious new
competitors to TripoSG for office furniture?

**Method:** full enumeration of the tag via the HF JSON API (paginated, four
sort orders — downloads, likes, created, modified — all converging on the same
set = complete coverage), then license verification of every candidate against
raw LICENSE files, card frontmatter, `base_model` tags, and GitHub.
**Popularity caveat:** HF exposes **no page-view numbers** via any API — the
available signals are 30-day downloads and cumulative likes; downloads
undercount repos with non-standard file layouts, so likes + recency are the
more trustworthy signal.

## 1. The census funnel — the numbers

| Stage | Count |
|---|---|
| Total models in the `image-to-3d` tag | **625** (19 gated) |
| Permissive-tagged (MIT 234 · Apache-2.0 83 · BSD 4 · other 1) | **322** (51.5%) |
| Non-permissive rest: "other"/community 117 · openrail 72 · untagged 49 · CC-NC 46 · apple-research 9 · GPL 3 | 303 |
| After removing mirrors/forks/quantizations (~160 repos are copies of ~10 projects: TRELLIS ×59, LGM ×45, TripoSR ×21, InstantMesh ×12, TripoSG ×5, …) | ≈ **162 distinct projects** |
| Distinct single-image→3D-**object** generators with released weights (excluding multi-view recon, depth, splats-only, human/avatar, scene-video, texture-only, empty repos) | **27 projects** |
| New to us (not in Stages 1–8 of the [narrowing funnel](HUGGINGFACE_MODEL_NARROWING.md)) | **17** |
| **Genuinely royalty-free AND EU-usable after real-license verification** | **11** |
| Serious enough to consider benchmarking | **~5** |
| Worth actually running against TripoSG | **3** |

**Sobering headline:** every 2025–26 quality-frontier newcomer (Pixal3D,
UltraShape, Miro, PhysX-family, Apple Sharp) is license- or EU-blocked.
TRELLIS.2-4B — already in our stack — remains TripoSG's only proven open
challenger. If the three below also lose, we have documented proof that **no
untested permissive HF model beats our current stack.**

## 2. Top 3 new competitors to benchmark vs TripoSG

| # | Model | Org | Likes | License | Why |
|---|---|---|---|---|---|
| 1 | **SceneGen** (`haoningwu/SceneGen`) | SJTU, 3DV '26 | 12 | MIT **verified** end-to-end | Purpose-built for indoor/furniture content; single image → multi-asset scene in one pass; mask-conditioned; textured; **16 GB VRAM stated** — fits our gating. Test single-object crops AND room shots. |
| 2 | **Cupid** (`hbb1/Cupid`) | Binbin Huang (2DGS author) | 0 (new) | MIT **verified** | The only clean-license model chasing the same reconstruction-fidelity frontier as Pixal3D/SAM 3D; TRELLIS-format weights = cheap integration into our harness. High variance — benchmark before investing. |
| 3 | **3DTopia-XL** (`3DTopia/3DTopia-XL`) | NTU | 48 | Apache-2.0 **verified** | Only permissive PBR-native mesh generator; ~5 s inference. Probably loses to TripoSG on F-score but closes the census. |

Notable but excluded: **Pixal3D** (TencentARC, 293 likes, SIGGRAPH '26 —
genuinely MIT-licensed but the HF repo sets `extra_gated_eu_disallowed: true`,
refusing weights to EU users — an MIT license with an EU distribution block is
a NEW pattern for the compliance section) · **TripoSplat** (VAST-AI, MIT —
Gaussian-splat output, no mesh; watch item) · **CRM** (Tsinghua, MIT verified —
mature 2024 baseline, likely below TripoSG) · **Apple Sharp** (6.3k dl/mo, 393
likes — apple research-only license).

## 3. License-tag contradictions caught (tags lie — always verify)

| Repo | Tag | Reality |
|---|---|---|
| `infinith/UltraShape` (114 likes) | apache-2.0 | GitHub LICENSE is verbatim the **Tencent Hunyuan 2.1 Community License — "THIS LICENSE AGREEMENT DOES NOT APPLY IN THE EUROPEAN UNION"**; `base_model: tencent/Hunyuan3D-2.1` |
| `IntimeAI/Miro` | apache-2.0 | Hunyuan3D-2.1 fine-tune (weight file literally `hunyuan3d-dit-v2-1/model.fp16.ckpt`), gated — EU ban inherited |
| `Caoza/PhysX-Anything`, `PhysX-Omni` | mit | Code is **S-Lab License 1.0 (non-commercial)** |
| `Yiwen-ntu/MeshAnythingV2` | mit | GitHub is S-Lab NC (matches our Stage-7 audit) |
| `TencentARC/Pixal3D` | MIT (genuine!) | `extra_gated_eu_disallowed: true` — HF refuses EU downloads despite MIT |
| `LutaoJiang/DiMeR` | apache-2.0 | **No LICENSE file at all**; single-image mode depends on Kiss3DGen (NC FLUX) |
| `LTT/PRM` | apache-2.0 | Needs an MV-diffusion frontend (Zero123++ NC risk) for single-image use |

## 4. Where the rest of the tag goes

Of 162 distinct permissive projects: the bulk are multi-view reconstruction/NVS/
depth (covered in [MULTI_IMAGE_RESEARCH.md](MULTI_IMAGE_RESEARCH.md)), human/
avatar generation, scene-video/world models, texture/retopo tools, and empty
student repos. Raw census data (all 625 entries + verified cards) is archived
with the session for reproducibility.
