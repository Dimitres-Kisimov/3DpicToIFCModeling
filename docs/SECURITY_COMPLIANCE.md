# Security & Compliance

**Project:** 3DpicToIFCModeling (SCS) — photograph → 3D reconstruction → IFC/BIM export
**Date:** 2026-07-11 · **Audience:** final paper (dedicated section) + engineering reference.
Every control below is implemented in the repository or documented process — nothing aspirational.

---

## 1. License compliance framework

The project's single largest legal surface is AI model licensing. The governing
rules (team in Germany/EU, commercial deliverable, zero budget):

1. **Royalty-free commercial grant required for BOTH code and weights.** The two
   are routinely licensed differently (verified examples: CraftsMan3D — MIT
   README, AGPL weights; Pi3 — BSD code, CC-BY-NC weights).
2. **Dependency licenses are traced transitively.** An Apache-tagged model that
   hard-requires an NC component is NC in practice. Caught this way: InstantMesh
   (needs Zero123++, CC-BY-NC), Kiss3DGen (needs FLUX.1-dev, NC), TRELLIS's
   texture path (nvdiffrast + Inria rasterizers, NC — geometry path is clean),
   LSM (Apache code, DUSt3R-contaminated), stock COLMAP binaries (bundled AGPL
   LSD compiled in by default + research-only SiftGPU).
3. **Verbatim verification.** Every license claim in our docs quotes the actual
   LICENSE file or HF model-card tag, dated. Popularity ≠ permission: the most
   downloaded model in the HF image-to-3d tag (Hunyuan3D) is unusable for us.
4. **Three status tiers** (enforced in the app):
   - **Production** — may ship in the engine selector (TripoSR, TripoSG, SAM 3D,
     TRELLIS geometry path, catalog retrieval).
   - **Benchmark-only** — used in accuracy studies, never in the product:
     SF3D/SPAR3D (Stability $1M revenue cap), InstantMesh (NC dependency).
   - **Banned** — not even benchmarked: Hunyuan3D (license not granted in the
     EU **for any purpose** — a territory exclusion has no research carve-out,
     unlike ordinary NC licenses; we cite its published numbers instead), plus
     the full NC/AGPL lists in [HUGGINGFACE_MODEL_NARROWING.md](HUGGINGFACE_MODEL_NARROWING.md)
     and [MULTI_IMAGE_RESEARCH.md](MULTI_IMAGE_RESEARCH.md).
5. **Asset licensing.** Catalog meshes are Amazon Berkeley Objects (CC-BY-4.0)
   with per-item attribution recorded in `data/mesh_library_abo/manifest.json`.
   All 187 benchmark photos come from free-license sources (Wikimedia Commons /
   Openverse CC) with URL, source, and fetch timestamp per photo in
   `benchmark/images/sources.json` — full provenance, re-checkable.

## 2. Data protection (GDPR posture)

- **No personal data by design.** Inputs are photographs of furniture. The
  CLIP screening stage (`benchmark/validate_images.py`) rejects photos whose
  primary subject is a person, a room scene, or an artwork — both for benchmark
  quality and to keep people out of the dataset.
- **Local-first processing.** The product runs entirely on the user's machine
  (localhost); photos never leave it in normal operation. No telemetry, no
  external calls at runtime.
- **Cloud processing is transient and minimal.** Benchmark runs on rented GPU
  pods use only the project's own photo set; the pod is treated as a disposable
  processor: results are downloaded, verified locally (`tar tzf`), and the pod
  is terminated — nothing persists at the provider afterward.

## 3. Credential & secret hygiene

- **No secrets in the repository** — verified; the HuggingFace token exists only
  in local/pod HF config files (mode 600), was transferred by stdin pipe (never
  in a command line, process list, or log), and is a **read-scoped** token.
- **Standing rule: revoke the token** (huggingface.co/settings/tokens) once the
  benchmark pod is terminated.
- Pod access is via ed25519 SSH keys; the pod is IP+port scoped and dies with
  the rental.
- Explicit user consent was obtained before the token ever left the local
  machine (2026-07-11 session).

## 4. Supply-chain controls

- **Model weights** come only from the official publisher's HuggingFace org
  (microsoft/, facebook/, VAST-AI/, stabilityai/, TencentARC/) — never mirrors —
  and use `safetensors` where the publisher provides it (pickle-format weights
  are a code-execution vector).
- **Python dependencies**: one virtualenv per engine (a broken or malicious dep
  in one engine cannot touch another); `pip freeze` snapshots are exported per
  env before teardown (`*-freeze.txt`) so every result is reproducible against
  a pinned dependency set. Known-good version pins are documented per engine in
  `deliverable/manuals/` (e.g. SAM 3D's numpy==1.26.4 pin).
- **Third-party model code** (repos like TRELLIS, SAM3D) runs inside the pod or
  a dedicated venv, not in the app process.

## 5. Output integrity (the anti-fabrication controls)

Added after a real incident (2026-07-11): a best-effort inference script
fell back to copying a repo asset on failure and reported success — fabricating
180 identical "results" in 2 minutes. Controls now standing:

1. **Preflight gate** — every engine must generate ONE real mesh (>50 KB) from a
   known input before any batch run (`queue3_verified.sh`). A broken engine
   costs one minute, not an hour of fake output (and fake money).
2. **Identical-output postcheck** — >10 outputs with <3 distinct file sizes
   flags the batch as fabricated (`Q3_SUSPECT`).
3. **No silent fallbacks** — inference scripts either produce the item's own
   mesh or log FAIL and produce nothing (rewritten `infer_sam3d.py`).
4. **IFC compliance gate** — nothing enters the app catalog without passing the
   real repair → `saveIFC` → IFC4 validation chain
   (`benchmark/ingest_pod_results.py`); rejected meshes are reported, not
   silently included. Per-engine IFC evidence is filed under `benchmark/ifc/<engine>/`.

## 6. Application security (localhost product)

- The app binds to localhost; it is not an internet-facing service. No
  authentication surface, no third-party analytics.
- Upload handling: images and IFC files are type-checked; generated assets are
  stored under `data/generated_assets/` with a manifest, not executed.
- The engine selector is **VRAM-gated**: engines whose requirements exceed the
  machine are not offered — preventing the "select → crash the laptop" failure
  class rather than handling it after the fact.

## 7. EU AI Act positioning (brief)

The system integrates third-party general-purpose AI models downstream; the
provider-side obligations (training-data transparency, model documentation)
rest with the model publishers. Our downstream duties — knowing what we run,
under which license, from which source, with what data — are discharged by the
license audit trail (Stages 1–8 of the narrowing funnel), the provenance
manifests, and this document. No biometric, emotion-recognition, or other
high-risk Annex III use is present: the system reconstructs furniture.

---

*Cross-references: [HUGGINGFACE_MODEL_NARROWING.md](HUGGINGFACE_MODEL_NARROWING.md)
(license funnel, Stages 1–8) · [MULTI_IMAGE_RESEARCH.md](MULTI_IMAGE_RESEARCH.md)
(multi-image audit) · [COMPARATIVE_ANALYSIS.md](COMPARATIVE_ANALYSIS.md) (studies) ·
`benchmark/images/sources.json` (photo provenance) · `deliverable/manuals/` (per-engine
pins and recipes).*
