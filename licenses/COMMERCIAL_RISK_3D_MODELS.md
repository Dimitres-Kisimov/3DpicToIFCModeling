# Commercial-Use Risk Sheet — Open-Source Image-to-3D Models

**Purpose:** an audit aid for SCS legal before committing any of these to a shipped product.
**NOT legal advice.** Verify every license against the **first-party** repo's actual LICENSE file
(not HuggingFace tags, not reuploads). Compiled 2026-06-30.

Three risk layers per model: (A) **weights/code license**, (B) **training-data provenance**
(weights-license ≠ data cleared), (C) **dependency tree** (a clean model can pull in restrictive
renderers/sub-models). "Verify" = confirm before shipping.

| Model | First-party repo | (A) License | (B) Training data | (C) Risky deps | Verdict |
|---|---|---|---|---|---|
| **TRELLIS-image-large** | microsoft/TRELLIS-image-large | **MIT** ✅ | Objaverse-XL + ABO + 3D-FUTURE + HSSD (mixed per-asset licenses) — *verify* | **nvdiffrast (NVIDIA custom license)**, spconv, flash-attn, kaolin | Clean license; residual = data + nvdiffrast |
| **TRELLIS.2-4B** | microsoft/TRELLIS.2-4B | **MIT** ✅ | as TRELLIS, larger — *verify card* | as TRELLIS (nvdiffrast) | Clean license; same residual; newest |
| **TripoSR** | stabilityai/TripoSR | **MIT** ✅ | Objaverse — *verify* | light (trimesh MIT, marching-cubes); no nvdiffrast | Lowest-dependency-risk of the set |
| **InstantMesh** | TencentARC/InstantMesh | **Apache-2.0** ✅ | Objaverse; **first stage = Zero123++** (own data lineage) | **nvdiffrast**, FlexiCubes, Zero123++ weights | Clean license; audit Zero123++ + nvdiffrast |
| **TripoSG** | VAST-AI/TripoSG | **MIT** ✅ | curated dataset (TripoSG paper) — *verify* | lighter; *verify* | Clean; verify training set terms |
| **MIDI-3D** | VAST-AI/MIDI-3D | **Apache-2.0** ✅ | *verify card* | *verify* | Clean license; multi-instance |
| **Shap-E** | openai/shap-e | **MIT** ✅ | OpenAI internal 3D dataset (undisclosed) — *verify* | light | Clean license; older/lower quality |
| **SAM 3D Objects** | facebook/sam-3d-objects | **SAM License** (custom, commercial-OK) ⚠️ | **dataset SA-3DAO = CC-BY-NC (do NOT ship dataset)** | pytorch3d, kaolin | Model commercial-OK; dataset NC; custom license |

## Cross-cutting commercial notes
1. **Training-data provenance is the industry-wide unsettled risk** and is ~identical across all
   Objaverse-trained models (TRELLIS, TripoSR, InstantMesh, TripoSG). MIT weights do not by
   themselves clear the data. Document the choice; let counsel weigh it. Risk for furniture is
   low-ish but non-zero in 2026 law.
2. **`nvdiffrast`** (used by TRELLIS, InstantMesh) ships under an **NVIDIA Source Code License** —
   read its commercial terms; it is *not* plain MIT. If it blocks commercial use in your config,
   prefer models that don't require it (TripoSR is the cleanest there).
3. **Reuploads carry no relicensing authority.** Pull only from the first-party repos above; ignore
   `gqk/`, `camenduru/`, `jetx/`, etc. tags.
4. **Attribution/NOTICE:** MIT requires preserving copyright notices; Apache-2.0 requires shipping a
   NOTICE file. Trivial but mandatory. Add to the product's third-party-notices.
5. **No warranty / no indemnity** (all of the above are as-is).
6. **Non-determinism** (all diffusion models: TRELLIS, InstantMesh, SAM 3D, TripoSG) is a *product*
   blocker for a deterministic catalog, not a legal one — separate from this sheet.

## Ranking by *commercial cleanliness* (lower risk first)
1. **TripoSR** (MIT, light deps, no nvdiffrast) — cleanest, but lowest quality.
2. **TripoSG** (MIT) — verify training set + deps; strong quality.
3. **TRELLIS / TRELLIS.2-4B** (MIT) — top quality + adoption; residual = nvdiffrast + Objaverse data.
4. **InstantMesh** (Apache) — clean license; audit Zero123++ + nvdiffrast.
5. **SAM 3D** (custom SAM License, commercial-OK) — strongest on cluttered scenes; custom license +
   NC dataset → needs the most legal attention of the commercial-safe set.

Avoid for shipping (from the wider scout): anything **CC-BY-NC** (54 models incl. Apple/`apple-amlr`),
**OpenRAIL** (use-restricted, 83 models), and anything **Hunyuan3D** (EU/UK excluded).

## Benchmark provenance — research-use declaration (for the paper)
The SCS single-image→3D benchmark (TripoSR · TripoSG · TRELLIS · InstantMesh · SAM 3D vs ABO
ground truth, on a RunPod H200) was run **strictly as research/evaluation**, never as a shipped
product. Two dependencies carry use-restrictions that are immaterial for research but **must be
revisited before any commercial deployment** of the models that need them:
- **`nvdiffrast` (NVIDIA Source Code License)** — required by **TRELLIS** and **InstantMesh** to
  rasterize/extract their meshes. Free for research/evaluation; **commercial use needs an NVIDIA
  agreement.** A productized TRELLIS/InstantMesh pipeline would have to license nvdiffrast, replace
  it, or avoid those models. **TripoSR and TripoSG do NOT use nvdiffrast** (cleaner commercially).
- **SAM 3D** — model under the custom **SAM License** (commercial-OK); benchmark dataset SA-3DAO is **CC-BY-NC**.

> **Reusable paper sentence:** *"All generated meshes were produced for evaluation only. TRELLIS and
> InstantMesh depend on nvdiffrast (NVIDIA Source Code License), which permits research use;
> commercial deployment of those pipelines would require separate licensing. TripoSR and TripoSG
> have no such dependency."*
