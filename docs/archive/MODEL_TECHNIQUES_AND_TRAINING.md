# How the Single-Image-to-3D Models Work — Technique & Training Deep-Dive

*Compiled 2026-06-30 from the arXiv papers, HuggingFace model cards, and GitHub repos of each model.
This is the "how do they pull this off in real life" reference and the monograph's Background/Related Work.*

**The one-line framing:** all five take a **single 2D image → a 3D object**, but they split into two
generations. The **older LRMs (TripoSR, InstantMesh)** regress geometry feed-forward from synthetic-render
training — fast, but they assume a clean, centred, unoccluded object. The **newer flow/diffusion models
(TripoSG, TRELLIS/TRELLIS.2, SAM 3D)** generate 3D as a *latent flow* and, crucially, **break the "3D data
barrier"** with far larger or real-world-aligned training sets — which is why they survive cluttered photos.
**None of them identifies the object** (that's DETR, a separate stage).

---

## 1. TripoSR (Stability AI / Tripo) — the fast deterministic baseline
- **Paper/licence:** arXiv [2403.02151](https://arxiv.org/abs/2403.02151); **MIT** (code + weights).
- **Technique:** feed-forward **triplane-LRM** transformer regression — **deterministic**, no diffusion. Image → **DINOv1 ViT** encoder → cross-attention image-to-triplane decoder → **triplane-NeRF** → Marching Cubes mesh. Notably **does not condition on camera** (it "guesses" pose), which improves in-the-wild robustness.
- **Training data:** a curated **Objaverse** subset (CC-BY renders); exact count unpublished. Synthetic renders with an "enhanced rendering method" to close the sim-to-real gap.
- **Training method:** single-stage, end-to-end; losses = photometric MSE + **LPIPS (×2.0)** + mask BCE (×0.05); **local 128×128 patch rendering with foreground importance sampling**. Compute: **5 days on 176× A100-40GB** (~21K GPU-hours).
- **Real-life trick:** speed (single feed-forward pass, **<0.5 s on A100**) + no-camera-conditioning robustness.
- **Quality (paper):** best CD/F-score vs One-2-3-45, ZeroShape, TriplaneGaussian, OpenLRM on GSO + OmniObject3D (e.g. GSO CD 0.111, F@0.1 0.651).
- **Inference:** **~6 GB VRAM**, deterministic, vertex-colored or baked-texture mesh. *(This is the model you already run locally.)*

## 2. TripoSG (VAST-AI) — large-scale rectified-flow SDF
- **Paper/licence:** arXiv [2502.06608](https://arxiv.org/abs/2502.06608); **MIT** (weights + code).
- **Technique:** **rectified-flow transformer** (flow matching, **stochastic** — not feed-forward). Dual image encoder (**DINOv2-L local + CLIP-ViT-L global**) → DiT-style flow transformer (21 blocks, 2048-wide, **MoE in the last 6 decoder layers → ~4B params**) → **SDF VAE** latent (C=64, up to 4096 tokens) → Marching Cubes. **Geometry only** (no texture).
- **Training data:** **2 million curated Image-SDF pairs** distilled from **Objaverse-XL + ShapeNet** via a 4-stage pipeline (a CLIP+DINOv2 scoring model trained on ~10K modeler-rated assets → filter → fix orientation/texture → 512³ SDF fields).
- **Training method:** SDF VAE with **hybrid geometry losses** (SDF + surface-normal + eikonal); rectified flow in 3 progressive stages (512→2048→4096 tokens + MoE). Compute: VAE **~12 days on 32× A100**, flow **~3 weeks on 160× A100**.
- **Real-life trick:** SDF (vs occupancy) + straight rectified-flow trajectories + 2M clean watertight pairs → sharp geometry. Normal-FID drops 9.47 → **3.36**.
- **Inference:** **>8 GB VRAM**, stochastic (seed-dependent), GLB mesh; uses RMBG-1.4 for background removal. *(Public checkpoint is the **1.5B/2048-token** model; ~4B MoE is the research config.)*

## 3. InstantMesh (TencentARC) — multiview-diffusion + sparse-view LRM
- **Paper/licence:** arXiv [2404.07191](https://arxiv.org/abs/2404.07191); **Apache-2.0**.
- **Technique:** **two-stage**. (a) **Zero123++** multiview diffusion (**stochastic**, seed-dependent) synthesises 6 views; (b) a **sparse-view LRM** (deterministic) reconstructs via **FlexiCubes** differentiable iso-surface extraction, supervised by **depth + normal** maps directly on the mesh.
- **Training data:** **~270K** high-quality instances filtered from Objaverse's 800K (LVIS + filtered pool); rendered at 512² with depth/normals from 32 viewpoints. (Objaverse ODC-By; weights Apache-2.0.)
- **Training method:** Stage 1 NeRF (MSE + LPIPS×2 + mask×1); Stage 2 FlexiCubes fine-tune (+ depth×0.5, normal×0.2, reg). **8× H800**.
- **Real-life trick / limits:** off-the-shelf multiview diffusion prior aids generalization; **but** 64² triplane is a resolution bottleneck, quality is hostage to **multiview inconsistency**, and FlexiCubes is **weak on thin structures** (legs/casters — matches your TripoSR finding).
- **Quality:** best SSIM/LPIPS/CD/F-score vs TripoSR, LGM, CRM, SV3D on GSO/OmniObject3D (GSO CD 0.180, F 0.880).
- **Inference:** ~10 s; partly stochastic (Zero123++ seed, default 42); OBJ/GLB mesh, optional texmap.

## 4. TRELLIS / TRELLIS.2-4B (Microsoft) — Structured 3D Latents
- **Papers/licence:** TRELLIS arXiv [2412.01506](https://arxiv.org/abs/2412.01506); **TRELLIS.2** arXiv [2512.14692](https://arxiv.org/abs/2512.14692); **MIT** both.
- **Technique (v1):** **SLAT** = sparse 64³ voxel grid + dense **DINOv2 features** (distilled from **150 rendered views** back-projected onto active voxels). **Two rectified-flow transformers**: (a) generates *which* voxels are active (structure), (b) generates the *latent features* on them (appearance). One SLAT → **multiple decoders** (3D Gaussians / radiance fields / **FlexiCubes mesh at 256³**). **Stochastic** (flow); reproducible by seed.
- **Training data:** **TRELLIS-500K** — ~500K assets from **Objaverse-XL + ABO + 3D-FUTURE + HSSD**, aesthetic-filtered; GPT-4o captions; Toys4k held out. Compute: XL on **64× A100, 400K steps, batch 256**.
- **TRELLIS.2-4B (Dec 2025):** **4B params**; new **"O-Voxel" field-free** representation encoding geometry **and** appearance directly — arbitrary topology (open/non-manifold), **no SDF/FlexiCubes**. **Full PBR** (base color + roughness + metallic + opacity). Sparse-Compression VAE (16× downsample, 1024³ → ~9.6K tokens). Resolutions **512³/1024³/1536³**.
- **Real-life trick:** decoupling **structure (geometry) from appearance (latent)** + **DINOv2 foundation features** = robustness + the cleanest geometry of the open set. Best CLIP/FD_dinov2 vs InstantMesh/LGM/Shap-E; large human-preference margin.
- **Inference:** v1 **≥16 GB**, ~10 s, GLB/Gaussian/RF. **v2 ≥24 GB**, H100: **512³≈3 s / 1024³≈17 s / 1536³≈60 s**, **PBR-GLB**. *(Card warns v2 raw meshes may have small holes and is "not aligned to human preference.")*

## 5. SAM 3D Objects (Meta) — the real-world-aligned, occlusion-aware one
- **Paper/licence:** arXiv [2511.16624](https://arxiv.org/abs/2511.16624); **SAM License** (custom, commercial-OK); **dataset SA-3DAO is CC-BY-NC**.
- **Technique:** **flow-matching**, **two-stage coarse-to-fine**. Takes image **+ segmentation mask** (pairs with SAM). (a) ~1.2B **Mixture-of-Transformers** jointly predicts coarse shape (64³/4096 tokens) **and pose/layout (R,t,s)**; (b) ~600M sparse-latent flow adds detail + texture. **DINOv2** encodes **cropped object *and* full scene** + optional depth point-map. Dual VAE → **mesh or 3D Gaussian splat**. Predicts **amodal** (occluded) shape and places it in the camera frame.
- **Training data — the headline:** a **human-and-model-in-the-loop "data engine"** breaks the **3D data barrier**: **~1M real images / ~3.14M meshes**, **>7M pairwise human preference judgments**, hardest cases escalated to **expert 3D artists**. Plus synthetic **Iso-3DO** (2.7M Objaverse-XL) and semi-synthetic **RP-3DO** (~61M render-paste with "Flying Occlusions"). Annotators **rank** model candidates (best-of-N) rather than model from scratch — the flywheel.
- **Training method (LLM-style):** pretrain (flow matching, ~2.5T tokens) → mid-train on occlusion/layout (~2.7T) → **post-train alignment via Diffusion-DPO** on the 7M preference pairs → **shortcut distillation NFE 25→4** for near-real-time.
- **Real-life trick:** it's **data + alignment, not a bigger net** — real annotated 3D + a DPO sim-to-real stage + full-scene context + joint pose → it survives clutter/occlusion where every other model assumes a clean object.
- **Quality:** **≥5:1 human-preference win** (≈6:1 scene-level) vs TRELLIS/Hunyuan3D/Hi3DGen/Direct3D-S2/TripoSG; on SA-3DAO F1@0.01 **0.234** vs ~0.15, Chamfer **0.040** vs ~0.09.
- **Inference:** **≥32 GB VRAM**, a few seconds, stochastic (seeded), **Gaussian-splat .ply** primary (mesh via mesh VAE).

---

## Comparison table

| Model | 3D representation | Deterministic? | Training data + scale | Key real-world trick | Output | VRAM |
|---|---|---|---|---|---|---|
| **TripoSR** | triplane-NeRF | **Yes** (feed-fwd) | curated Objaverse (CC-BY) | no-camera-conditioning; realistic renders | colored mesh | ~6 GB |
| **TripoSG** | SDF VAE latent | No (rectified flow) | **2M** curated Image-SDF pairs | SDF + normal/eikonal losses; 2M clean pairs | geometry mesh | >8 GB |
| **InstantMesh** | triplane + FlexiCubes | Partly (Zero123++ stochastic) | ~270K Objaverse | multiview-diffusion prior + depth/normal sup. | OBJ/GLB | ~8–16 GB |
| **TRELLIS / .2-4B** | SLAT / **O-Voxel (PBR)** | No (rectified flow) | **500K** (Obj-XL+ABO+3D-FUTURE+HSSD) | structure⊥appearance + DINOv2 features | Gaussian/RF/**PBR-GLB** | 16 / **24** GB |
| **SAM 3D** | mesh / Gaussian splat | No (flow + DPO) | **~1M real imgs / 3.14M meshes** + 7M prefs | real-world DPO alignment + full-scene + pose | splat/mesh | **≥32 GB** |

## Why the newer models beat the old LRMs on real photos — the "3D data barrier"
High-quality **real-world** 3D ground truth is scarce, so the early LRMs (TripoSR, InstantMesh) trained almost
entirely on **clean synthetic objects on blank backgrounds** — they assume a fully visible, centred, unoccluded
object and degrade on cluttered photos, odd poses, and occlusion. The newer models attack the *data*, three ways:
- **TripoSG** — brute-force **data quality** (a 4-stage curation pipeline → 2M clean watertight Image-SDF pairs).
- **TRELLIS** — a **better representation** (SLAT/O-Voxel) over foundation-model (DINOv2) features + 500K curated assets.
- **SAM 3D** — **real-world data + alignment**: ~1M annotated real images via a ranking-based human/model flywheel, plus a **Diffusion-DPO** post-training stage that explicitly closes the sim-to-real gap — hence its ≥5:1 human-preference lead on in-the-wild objects.

**Licensing thread (ties to the risk sheet):** every model has **MIT/Apache weights** *except* SAM 3D (custom SAM
License), **but all are trained on Objaverse-derived or third-party assets** — the weights are clean, the *training
data* provenance is the unresolved commercial-use caveat. SAM 3D additionally ships a **CC-BY-NC** benchmark dataset
(do not ship the dataset). This is exactly why the project's product core stays **retrieval over CC-BY ABO**, with
these generators as a benchmarked, flagged option.
