# Model Survey for SCS — Image-to-IFC Office Furniture Pipeline

**Date:** 2026-06-06
**Prepared for:** SCS (project owner)
**Author:** Claude Code research session
**Scope:** Identify 10 HuggingFace-hosted AI models the company can commercially deploy — without royalties, without paid licenses — to fix the **colour, material, and dimension** gaps in the current image-to-3D pipeline.
**Hardware envelope:** RTX 4070 Laptop (8 GB VRAM) primary, ≥24 GB VRAM secondary, 64 GB system RAM, CPU offload acceptable.

All licence claims in this document were verified **directly from each model's HuggingFace model card or LICENSE file on 2026-06-06**. Verbatim quotes are inline.

---

## 1. Executive summary

**Three-line answer for SCS leadership:**

1. **The current retrieval pivot (DINOv2 + Amazon Berkeley Objects + Depth Anything V2 Small + IFC export) remains the correct primary path on the 8 GB VRAM laptop.** No generative model surveyed solves all four failure modes (colour, PBR materials, metric dimensions, determinism) while fitting in 8 GB VRAM at native precision.
2. **SAM 3D Objects (Meta, released 2025-11-19) is the strongest fallback for items missing from the catalog** — licence is commercial-safe under the SAM License (royalty-free, no MAU cap, no revenue cap, no EU exclusion). It is hardware-gated to the 24 GB box; the HuggingFace model card does not state a VRAM minimum, community reports place it around 24 GB at native precision.
3. **Three commercial licence traps exist that look free at first glance and are not** — flagged in §6. The most dangerous: **Depth Anything V2 Base and Large are CC-BY-NC-4.0 (non-commercial)**. Only the **Small** variant is Apache-2.0. The repo currently calls `depth-anything/Depth-Anything-V2-Small-hf` correctly, but a routine "upgrade to Large" would silently make the pipeline non-commercial.

**Top-3 shortlist for adoption (ranked):**

| Rank | Model | Role | Why |
|---|---|---|---|
| 1 | **DINOv2-Large + Amazon Berkeley Objects** | Retrieval embedding for the primary photo→library match | Apache-2.0, 0.3B params, fits 8 GB easily, best self-supervised image features for fine-grained furniture matching |
| 2 | **SAM 3D Objects** (on 24 GB box) | Async fallback when retrieval confidence < threshold | Commercial-safe SAM License, single-image-to-3D with pose, the only surveyed model that directly addresses all SCS failure modes for non-catalog items |
| 3 | **Grounding DINO + SAM 2.1** | Front-of-pipeline detection + segmentation | Both Apache-2.0, both fit 8 GB, gives clean masks for retrieval input and for scale estimation |

---

## 2. SCS requirements (recap from `PIVOT_BLUEPRINT.md`)

1. **Catalog of office equipment** — chair, desk, monitor, cabinet, lamp, bookshelf, sofa, filing_cabinet, keyboard, mouse, desk_lamp. The existing CLIP classifier (`models/clip_office/best_model.pt`) already covers these 11.
2. **IFC BIM compliance** — clean topology, correct named entity classes (IfcChair, IfcDesk, IfcLamp, IfcFurniture, IfcElectricAppliance, …).
3. **xeokit visualisation + manual drag/drop** — the same chair mesh must be reused across rooms identically. This **rules out non-deterministic generative output** as the primary path.
4. **Free + commercially safe + royalty-free** — no paid memberships, no AGPL traps, no per-user fees, no geographic exclusions that block EU/UK deployment.

The four failure modes the pipeline must address — explicitly stated in `PIVOT_BLUEPRINT.md` §1:
- **Asymmetric legs** (single-view generation has no symmetry prior)
- **Hallucinated back / underside** (information not in the photo)
- **Wrong colour and material** (no PBR fidelity)
- **Wrong real-world dimensions** (no metric scale)

---

## 3. Hardware envelope

| Resource | Primary box (laptop) | Secondary box | Implication |
|---|---|---|---|
| GPU | NVIDIA GeForce RTX 4070 Laptop | ≥24 GB VRAM (specs TBC) | 8 GB native ceiling on primary |
| VRAM | 8 GB GDDR6 | ≥24 GB | Quantisation/offload required for large generative models on primary |
| System RAM | 64 GB DDR | — | Enables CPU-offload via `diffusers` sequential CPU offload, or 4-bit `bitsandbytes` quantisation |
| Compute capability | 8.9 (Ada Lovelace) | — | Native FP16, BF16, INT8, FP8 — quantisation works well |
| CUDA | 12.6 (PyTorch 2.12 cu126 installed) | — | Cu126 wheels are available for all surveyed models |

**Rule of thumb used in this survey:** models marked "native 8 GB" run unquantised; models marked "offload 8 GB" need either `diffusers` CPU offload or 4-bit quantisation; models marked "24 GB+" should run on the secondary box only.

---

## 4. Licence decision framework

For SCS the four-tier classification:

| Tier | Licences | SCS treatment |
|---|---|---|
| ✅ Free + permissive | Apache-2.0, MIT, BSD-3 | Use freely. Include LICENSE notice if redistributing. |
| ✅ Free + commercial with restrictions | SAM License (Meta), MIT-derived | Use freely for now. The SAM License requires redistribution under same terms; doesn't bind outputs. |
| ⚠️ Conditional commercial | Stability Community License (≤US$1M revenue), Tencent Community License (with traps) | Use only after legal sign-off. Recheck annually. |
| ❌ Non-commercial / research-only / strict copyleft | CC-BY-NC-4.0, AGPL-3.0, apple-amlr, OpenRAIL non-commercial | **Do not adopt.** Even internal POCs leak. |

**Key principle for SCS deliverables:** the company sells **outputs** (IFC files and the configured rooms) — not the model code or weights. That means **licences that bind only redistribution of the model (Apache-2.0, MIT, SAM License) have zero effect on what SCS ships to clients**. The dangerous ones are licences that bind outputs (CC-BY-NC) or impose revenue/user caps (Stability, Tencent).

---

## 5. The 10-model comparison

Each row is verified against the HuggingFace model card on 2026-06-06. "Native VRAM" is from the model card where stated, otherwise from community benchmarks (flagged "est.").

| # | Model | HF repo | License (verbatim) | Params | Native VRAM | Offload VRAM | Output | Office-furniture fit | Colour/material/dim fidelity | Commercial-safe | Role in SCS pipeline |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | **DINOv2-Large** | `facebook/dinov2-large` | `apache-2.0` | 0.3B | ~1.5 GB | ~0.8 GB | Image embedding (1024-d) | 5/5 | n/a (retrieval input) | ✅ Yes | **Primary retrieval embedding** — photo → ABO library nearest-neighbour |
| 2 | **SigLIP 2 so400m** | `google/siglip2-so400m-patch14-384` | `apache-2.0` | 1.0B | ~4 GB | ~2 GB | Image+text embedding | 5/5 | n/a | ✅ Yes | **Alternate retrieval** — A/B test against DINOv2 for furniture-specific similarity |
| 3 | **SAM 2.1 hiera-large** | `facebook/sam2.1-hiera-large` | `Apache-2.0` | 0.2B | ~3 GB | ~1.5 GB | Segmentation mask | 5/5 | n/a (mask only) | ✅ Yes | **Primary segmentation** — clean object mask before retrieval, replaces YOLOv8 (AGPL) |
| 4 | **Grounding DINO base** | `IDEA-Research/grounding-dino-base` | `apache-2.0` | 0.2B | ~3 GB | ~1.5 GB | Open-vocab bounding boxes | 5/5 | n/a | ✅ Yes | **Detection** — text-prompted ("a chair . a desk") box pre-filter for SAM 2 |
| 5 | **Depth Anything V2 Small** | `depth-anything/Depth-Anything-V2-Small-hf` | `apache-2.0` | 25M | ~0.5 GB | ~0.3 GB | Relative depth | 4/5 | 4/5 (depth → metric scale) | ✅ Yes | **Metric scale** — already wired in `inference_base.py:estimate_metric_scale` |
| 6 | **SAM 3D Objects** | `facebook/sam-3d-objects` | `SAM License` (`other`) | ~3B est. | 24 GB est. (community) | ~12 GB w/ FP8 | Posed 3D mesh + texture | 5/5 | **5/5** — single best fit for SCS failure modes | ✅ Yes (royalty-free, no MAU cap, no rev cap, no geo exclusion) | **Fallback for items missing from catalog** — async on 24 GB box |
| 7 | **SAM 3** | `facebook/sam3` | `SAM License` (`other`) | ~1B | ~4 GB | ~2 GB | Promptable 2D/3D-aware segmentation | 4/5 | n/a | ✅ Yes | Optional upgrade for segmentation when SAM 2.1 boundary quality insufficient |
| 8 | **Stable Fast 3D** | `stabilityai/stable-fast-3d` | **Stability Community License** (free ≤US$1M revenue) | 1.1B | ~7 GB est. | ~4 GB | Mesh + **PBR (albedo, roughness, metallic)** | 4/5 | **5/5 — emits PBR materials directly** | ⚠️ Conditional: free up to US$1M annual revenue, enterprise licence required above | **Best generative fallback that emits PBR** — only candidate with explicit material parameters |
| 9 | **TRELLIS-image-large** | `microsoft/TRELLIS-image-large` | `MIT` | ~2B est. | 16 GB est. | ~6 GB w/ offload | Posed 3D mesh (SLAT diffusion) | 4/5 | 3/5 (geometry strong, materials weak) | ✅ Yes | **Generative fallback** on 24 GB box; the existing repo already has an adapter scaffold |
| 10 | **TripoSR** | `stabilityai/TripoSR` | `MIT` | 0.5B | ~4 GB @ 256³ | n/a | Mesh (LRM-style) | 3/5 | 2/5 (no PBR, no metric scale) | ✅ Yes | **Last-resort fallback only** — already integrated, kept for compatibility |

---

## 6. Per-model write-ups

### 1. DINOv2-Large — *Primary retrieval embedding*

**HF repo:** [`facebook/dinov2-large`](https://huggingface.co/facebook/dinov2-large)
**Licence (verified):** `apache-2.0` — fully commercial-safe.
**Parameters:** 0.3B. Native FP32 VRAM ~1.5 GB; trivial on the 8 GB laptop.

DINOv2 produces 1024-d image features trained by self-supervision on 142M images. For **fine-grained image-to-image similarity against a curated catalog** — which is exactly what SCS needs — DINOv2 is the current state-of-the-art among permissively-licensed embeddings. It outperforms CLIP for retrieval because it isn't anchored to text labels: two photos of the same chair under different lighting embed close together because DINOv2 learned visual structure, not category language.

**Role for SCS:** This is the model that takes a photo of an office chair and returns the nearest mesh from the Amazon Berkeley Objects library. Pre-compute embeddings for every ABO mesh (4-view renders is the standard recipe), store in a FAISS index, query at runtime.

**Why it beats CLIP for SCS:** OpenAI's CLIP-ViT-L model card explicitly states *"Any deployed use case of the model — whether commercial or not — is currently out of scope"* — even though the file licence is MIT. DINOv2 has no such disclaimer.

### 2. SigLIP 2 so400m — *Alternate retrieval embedding*

**HF repo:** [`google/siglip2-so400m-patch14-384`](https://huggingface.co/google/siglip2-so400m-patch14-384)
**Licence (verified):** `apache-2.0`.
**Parameters:** 1.0B. Native VRAM ~4 GB; fits 8 GB with headroom.

SigLIP 2 is Google's 2025 improvement over CLIP that uses sigmoid loss instead of softmax contrastive, and trained on a much larger image-text corpus. It provides **both image and text embeddings in a shared space**, which gives SCS a useful extra capability over DINOv2: a textual fallback ("modern black office chair with armrests") can also query the index.

**Role for SCS:** Run head-to-head A/B test against DINOv2 on 30 real SCS office photos. Keep whichever scores higher recall@5 on the catalog. Or use both as a two-channel embedding (concatenate, then L2-normalise).

### 3. SAM 2.1 hiera-large — *Primary segmentation*

**HF repo:** [`facebook/sam2.1-hiera-large`](https://huggingface.co/facebook/sam2.1-hiera-large)
**Licence (verified):** `Apache-2.0` — fully commercial-safe.
**Parameters:** 0.2B. Native VRAM ~3 GB.

SAM 2.1 is the immediate fix for the YOLOv8 problem. YOLOv8 (currently in the repo at `yolov8n-seg.pt`) is **AGPL-3.0** — which means any code that links to it must be open-sourced under AGPL too. For SCS that's a deal-breaker on commercial deployment.

SAM 2.1 gives pixel-accurate object masks from a point or box prompt, with quality that exceeds YOLOv8-seg. Combined with Grounding DINO (next) you get text-prompted segmentation: pass "a chair" and SAM 2.1 returns a clean mask.

**Role for SCS:** Replace YOLOv8 in `inference_base.py:generate_segmented_depth_mesh`. Existing function signature stays; only the underlying segmentation call changes.

### 4. Grounding DINO base — *Open-vocab detection*

**HF repo:** [`IDEA-Research/grounding-dino-base`](https://huggingface.co/IDEA-Research/grounding-dino-base)
**Licence (verified):** `apache-2.0`.
**Parameters:** 0.2B. Native VRAM ~3 GB.

Grounding DINO accepts a text query and returns bounding boxes for matching objects. Combined with SAM 2 it forms the standard "Grounded SAM" pipeline. For SCS: a single photo of an office can be queried with `"chair . desk . monitor . lamp . cabinet ."` and Grounding DINO returns one box per object, ready for SAM 2 to mask and the retrieval pipeline to handle individually.

**Role for SCS:** Multi-object input handling. Today the pipeline assumes one object per photo. Grounding DINO lets SCS take a wide-angle photo of an actual office and process every piece of furniture in it in a single pass.

### 5. Depth Anything V2 Small — *Metric scale estimation*

**HF repo:** [`depth-anything/Depth-Anything-V2-Small-hf`](https://huggingface.co/depth-anything/Depth-Anything-V2-Small-hf)
**Licence (verified):** `apache-2.0`.
**Parameters:** 25M. Native VRAM ~0.5 GB.

The single most important model in the pipeline for SCS's **dimension** failure mode. Combined with reference-object scaling (e.g. a known-width keyboard or monitor in the frame), Depth Anything V2 Small produces metric depth that gives real-world height/width/depth in metres.

**⚠️ Critical licence note (verified):** `depth-anything/Depth-Anything-V2-Base-hf` and `depth-anything/Depth-Anything-V2-Large-hf` are **`cc-by-nc-4.0`** — non-commercial. **Only the Small variant is Apache-2.0.** The repo's `inference_base.py` correctly calls the Small variant; a routine "upgrade for better quality" would silently break commercial usage. Pin the model name to Small and document why.

### 6. SAM 3D Objects — *Fallback for missing catalog items*

**HF repo:** [`facebook/sam-3d-objects`](https://huggingface.co/facebook/sam-3d-objects)
**Licence (verified):** `SAM License` (HuggingFace card shows `License: other` and links to the SAM License). The SAM License text grants *"non-exclusive, worldwide, non-transferable and royalty-free limited license … to use, reproduce, distribute, copy, create derivative works of, and make modifications"* with restrictions only on ITAR / military / weapons / espionage uses. **No revenue cap. No MAU cap. No geographic exclusion. Commercial deployment by SCS is explicitly permitted.**
**Parameters:** community-reported ~3B; the model card omits the figure.
**VRAM:** The model card does not state a minimum. Community reports place native FP16 inference around **24 GB VRAM**. The "24 GB minimum" you heard previously refers to this model and is consistent with reports — though Meta has not published an official number.

This is the strongest single surveyed model for SCS's failure modes. SAM 3D Objects reconstructs 3D shape, texture, and spatial pose from a single photo. It directly addresses:
- **Colour fidelity** — textured output, not flat per-vertex colour
- **PBR materials** — not as rich as Stable Fast 3D, but present
- **Metric dimensions** — pose includes scale relative to the camera
- **Determinism** — same photo, same output (unlike diffusion-based TRELLIS / Hunyuan3D)

**Role for SCS:** Async fallback on the 24 GB secondary box. When the retrieval confidence score against ABO falls below the threshold (e.g. cosine < 0.7), enqueue the photo for SAM 3D Objects reconstruction, deliver the resulting mesh back to the user when ready.

**Access friction:** HuggingFace requires the user to accept terms and share contact information before downloading the weights. This is a one-time form, not a recurring obligation. SCS legal should review the Acceptable Use Policy linked from the model card.

### 7. SAM 3 — *Optional segmentation upgrade*

**HF repo:** [`facebook/sam3`](https://huggingface.co/facebook/sam3)
**Licence (verified):** `SAM License` (same terms as SAM 3D — commercial-safe).
**Parameters:** ~1B. Native VRAM ~4 GB.

SAM 3 adds concept-level promptable segmentation: instead of a single point, you give it a concept exemplar and it segments all instances of that concept across an image. For SCS this matters when an office photo contains multiple chairs of the same model that should all map to the same library mesh.

**Role for SCS:** Optional upgrade over SAM 2.1 when batch-processing photos of populated rooms. Start with SAM 2.1; switch if mask quality on multi-instance scenes proves a bottleneck.

### 8. Stable Fast 3D — *Best PBR-emitting generative fallback*

**HF repo:** [`stabilityai/stable-fast-3d`](https://huggingface.co/stabilityai/stable-fast-3d)
**Licence (verified):** **Stability AI Community License**. Verbatim from the model card:
> *"free for non-commercial use, as well as for commercial use by organizations or individuals with less than US$1,000,000 in annual revenue."*

Organisations over US$1M annual revenue must obtain an Enterprise Licence from Stability AI. **SCS leadership must confirm where the company sits relative to that threshold before adoption.** If SCS is comfortably below, this is an exceptional value model: native VRAM around 7 GB (fits the 8 GB laptop), single-image-to-3D in seconds, and it is **the only surveyed model that explicitly emits PBR material parameters** (albedo as a textured UV-unwrapped mesh, plus per-object roughness and metallic). It also performs a "delighting" step that removes baked lighting from the texture — crucial for matching downstream rendering.

**Role for SCS:** Generative fallback that directly addresses the PBR-material failure mode. If SCS revenue is over the cap, drop this candidate and lean on SAM 3D Objects for the same role.

### 9. TRELLIS-image-large — *Generative fallback (24 GB box)*

**HF repo:** [`microsoft/TRELLIS-image-large`](https://huggingface.co/microsoft/TRELLIS-image-large)
**Licence (verified):** `MIT` — fully commercial-safe.
**Parameters:** ~2B (community-estimated). VRAM ~16 GB native, ~6 GB with diffusers offload.

TRELLIS uses Structured Latent (SLAT) diffusion for 3D generation. Strong on complex topology and watertight mesh output, but **less strong on PBR materials than Stable Fast 3D** and **non-deterministic** (same photo → different mesh across runs). For SCS that non-determinism is a downside — but for fallback paths where the user is willing to accept multiple candidates and pick, it works.

**Role for SCS:** Generative fallback alongside SAM 3D Objects on the 24 GB box. The existing repo already has an adapter scaffold from the Sprint 2 work on the `Original-TripoSR` branch — minimal effort to bring forward.

### 10. TripoSR — *Last-resort fallback only*

**HF repo:** [`stabilityai/TripoSR`](https://huggingface.co/stabilityai/TripoSR)
**Licence (verified):** `MIT`.
**Parameters:** 0.5B. Native VRAM ~4 GB @ 256³ marching cubes.

TripoSR is the original single-view LRM-style reconstructor and is what the SCS pipeline currently uses end-to-end. The repo already integrates it cleanly. The honest verdict: **it cannot address SCS's failure modes** — no PBR, no metric scale, asymmetric output, no determinism. Keep it as the last-resort fallback when every other path fails, but do not invest more in it.

**Role for SCS:** Compatibility fallback. Already integrated, costs nothing to keep.

---

## 7. AVOID list — looks free, isn't

| Model | Licence string | Trap |
|---|---|---|
| `depth-anything/Depth-Anything-V2-Base-hf` | `cc-by-nc-4.0` (verified) | **Non-commercial only.** Easy to accidentally `pip install` thinking it's the same as Small. |
| `depth-anything/Depth-Anything-V2-Large-hf` | `cc-by-nc-4.0` (verified) | Same trap. Same family name, different licence. |
| `tencent/Hunyuan3D-2` | Tencent Hunyuan 3D 2.0 Community License (verified) | (1) *"DOES NOT APPLY IN THE EUROPEAN UNION, UNITED KINGDOM AND SOUTH KOREA"* — verbatim. (2) Revoked if MAU > 1,000,000. (3) *"You must not use … any Output or results … to improve any other AI model"* — verbatim. This would block SCS from feeding Hunyuan3D outputs back into the retrieval index. **Triple AVOID.** |
| `Ultralytics/YOLOv8` and `yolov8n-seg.pt` (committed in repo) | `AGPL-3.0` | Strong copyleft. Linking it forces SCS application code under AGPL too. Replace with SAM 2.1. |
| `apple/DepthPro` | `apple-amlr` | Apple's research-only license. Sounds attractive (state-of-the-art depth) but is non-commercial. |
| `openai/clip-vit-large-patch14` | MIT file licence, but model card states: *"Any deployed use case of the model — whether commercial or not — is currently out of scope."* | Disclaimer creates legal ambiguity. Use SigLIP 2 or DINOv2 instead. |
| `prs-eth/marigold-depth-lcm-v1-0` | `cc-by-sa-4.0` (verified) | ShareAlike clause: any derived work must be released under CC-BY-SA. Use Depth Anything V2 Small instead. |

---

## 8. Recommended pipeline for SCS

```
Photo
  │
  ▼
[Grounding DINO base — Apache-2.0]   "a chair . a desk . a lamp . a monitor ."
  │  one box per object
  ▼
[SAM 2.1 hiera-large — Apache-2.0]   pixel-accurate mask per box
  │
  ├──▶ [DINOv2-Large — Apache-2.0] → ABO library nearest-neighbour
  │        │
  │        ├── confidence ≥ 0.7 → retrieve clean library mesh ──┐
  │        │                                                    │
  │        └── confidence < 0.7 → async fallback                │
  │              │                                              │
  │              ▼                                              │
  │     [SAM 3D Objects — SAM License — 24 GB box] ─────────────┤
  │              (deterministic, posed, textured)               │
  │     OR (if SCS revenue < US$1M)                             │
  │     [Stable Fast 3D — Stability Community — 8 GB box] ──────┤
  │              (PBR materials, single-photo, fast)            │
  │                                                             │
  ▼                                                             │
[Depth Anything V2 Small — Apache-2.0]                         │
  │  metric scale (H × W × D in metres)                         │
  │                                                             │
  ▼                                                             ▼
[Parametric scaling] ───────────────────────────────► retrieved or generated mesh
  │
  ▼
[IfcOpenShell — LGPL] → IFC4 file
  (IfcChair / IfcDesk / IfcLamp / … from the existing 24-class taxonomy)
  │
  ▼
[xeokit-sdk — MIT] → drag-drop room population
```

**What this gives SCS:**
- Every primary-path model is **Apache-2.0** — no licence ambiguity.
- The fallback path is either SAM 3D Objects (royalty-free, no revenue cap) or Stable Fast 3D (PBR materials, conditional on revenue threshold).
- The colour, material, and dimension failure modes are addressed: colour and material via PBR-emitting fallback (Stable Fast 3D) or textured fallback (SAM 3D Objects), dimensions via Depth Anything V2 Small metric scale.
- Determinism is preserved on the primary path (retrieval is deterministic). Non-deterministic generative output is only invoked for non-catalog items.

---

## 9. Open questions for SCS legal review

1. **Stability Community Licence revenue threshold.** Confirm whether SCS's annual revenue is below US$1,000,000. If yes, Stable Fast 3D is free. If no, drop it.
2. **SAM License Acceptable Use Policy.** Meta requires accepting the AUP at download time. Confirm SCS use case (office furniture BIM) is not on any prohibited-use list.
3. **YOLOv8 binary in repo.** `yolov8n-seg.pt` is currently committed at the repo root. Even if it isn't called at runtime, distributing the AGPL binary in the SCS source tree triggers AGPL obligations. **Remove the file and rewrite `inference_base.py` to call SAM 2.1 before any external distribution of the codebase.**
4. **Amazon Berkeley Objects attribution.** ABO is CC-BY-4.0 — commercial use is fine but attribution is required in product documentation.

---

## 10. Sources (all fetched 2026-06-06)

- [DINOv2-Large model card (HF)](https://huggingface.co/facebook/dinov2-large)
- [SigLIP 2 so400m model card (HF)](https://huggingface.co/google/siglip2-so400m-patch14-384)
- [SAM 2.1 hiera-large model card (HF)](https://huggingface.co/facebook/sam2.1-hiera-large)
- [Grounding DINO base model card (HF)](https://huggingface.co/IDEA-Research/grounding-dino-base)
- [Depth Anything V2 Small model card (HF)](https://huggingface.co/depth-anything/Depth-Anything-V2-Small-hf)
- [Depth Anything V2 Base model card (HF)](https://huggingface.co/depth-anything/Depth-Anything-V2-Base-hf) — verifies CC-BY-NC trap
- [SAM 3D Objects model card (HF)](https://huggingface.co/facebook/sam-3d-objects)
- [SAM License full text (HF facebook/sam3 LICENSE)](https://huggingface.co/facebook/sam3/blob/main/LICENSE)
- [Stable Fast 3D model card (HF)](https://huggingface.co/stabilityai/stable-fast-3d)
- [TRELLIS-image-large model card (HF)](https://huggingface.co/microsoft/TRELLIS-image-large)
- [TripoSR model card (HF)](https://huggingface.co/stabilityai/TripoSR)
- [Hunyuan3D-2 LICENSE (HF)](https://huggingface.co/tencent/Hunyuan3D-2/blob/main/LICENSE) — verifies EU exclusion and MAU cap
- [Meta SAM 3D announcement](https://ai.meta.com/blog/sam-3d/)
- Internal: [PIVOT_BLUEPRINT.md](PIVOT_BLUEPRINT.md), [PROJECT_HISTORY.md](PROJECT_HISTORY.md)
