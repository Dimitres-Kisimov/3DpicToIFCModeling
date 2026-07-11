# RUNBOOK — Census-Trio Pod Run (SceneGen · Cupid · 3DTopia-XL) — 🟡 DRAFT 2026-07-11

**Goal:** benchmark the three license-verified challengers from the HF census
(`docs/HF_CENSUS_2026-07.md`) against TripoSG: score them on the SAME research-10
inputs/gt/scorer/seed as Studies A/C, and generate the 170/187 internet-photo set for the
visual gallery. If all three lose, the census headline is proven: *no untested permissive
HF model beats the current stack.*

**Pod (CHEAP — this run does not need the A100):** RunPod → **RTX A5000 24 GB** or
**RTX 4090 24 GB**, community cloud, **~$0.40–0.70/h** → template *RunPod PyTorch 2.x
(CUDA ≥ 12.1)* → **disk 80–100 GB**. All three models state ≤16 GB VRAM (3DTopia-XL unstated
— treat its first run as the measurement), so 24 GB has headroom.
**Budget: ~6–8 h ≈ $3–4 total.**

**⚠️ Licence note before you start:** SceneGen's checkpoints include `facebook/VGGT-1B`
(**CC-BY-NC-4.0**) — downloading and running it here is research benchmarking ONLY; SceneGen
cannot ship in the app unless the pod run proves inference works without VGGT
(manuals/SCENEGEN.md, licence section). Cupid and 3DTopia-XL are clean (MIT / Apache-2.0).

**Operator note:** every step is copy-paste; run in order. If a step fails, the per-model
manual (`manuals/SCENEGEN.md`, `CUPID.md`, `TOPIA_XL.md`) has the anticipated-issues table.

## 0. From the LOCAL machine — upload bundle + clone repo (bundle is gitignored!)

```bash
cd /c/Users/dimik/3DpicToIFCModeling
tar czf /tmp/cloud_bundle.tar.gz -C deliverable cloud_bundle
scp -P <PORT> /tmp/cloud_bundle.tar.gz root@<POD>:/workspace/
ssh -p <PORT> root@<POD> "cd /workspace && tar xzf cloud_bundle.tar.gz && \
  git clone --depth 1 https://github.com/Dimitres-Kisimov/3DpicToIFCModeling.git"
```

## 1. On the pod — install the three (parallel, ~30–60 min)

```bash
cd /workspace/cloud_bundle
bash install_models.sh censustrio          # scenegen + cupid + 3dtopiaxl, one venv each
tail -f /workspace/logs/install_cupid.log  # watch the risky one (pytorch3d + TRELLIS-family builds)
```

No HF token needed — none of the trio is gated.

## 2. Run the gated queue (masks → preflight → research-10 → score → 170 sweep)

```bash
mkdir -p /workspace/logs
nohup bash queue_trio.sh >/dev/null 2>&1 &
tail -f /workspace/logs/queue_trio.log
```

The queue is two-phase **on purpose** (cheap-pod budget guard):

- **Phase A** — per model: 1-item preflight gate (>50 KB real mesh or the batch is skipped),
  then the research-10, then `score_all.py` → `out/cloud_scores.csv`. *If the pod dies here,
  the scored deliverable already exists.*
- **Phase B** — the 170/187 internet-photo sweep (`bench170_manifest.json`, built on the pod
  from `benchmark/images/`; `make_bench170_manifest.py` picks up every `listNN` photo present)
  into `out170/`, cheapest model first, fabrication postcheck, HF-cache eviction between models.

Do NOT score out170 — internet photos have no gt; they feed the visual gallery +
app-pipeline test only (make_bench170_manifest.py docstring).

## 3. Time & cost estimates (A5000 @ ~$0.50/h; all pre-run estimates — record actuals)

| Model | Install | Research-10 | 170-sweep | Basis |
|---|---|---|---|---|
| 3dtopiaxl | ~20 min (4 compiled deps, small) | ~5 min | **~0.5–1 h** | ~5 s/item claimed + rembg/unwrap overhead |
| scenegen | ~30 min (TRELLIS-family parade) | ~15 min | **~1.5–2.5 h** | TRELLIS-class two-sampler feedforward, ~30–60 s/item |
| cupid | ~40 min (parade + pytorch3d + moge) | ~20 min | **~2.5–4 h** | two-stage (coarse + pose-conditioned refine), ~60–90 s/item |
| **Total** | ~1 h wall (parallel) | ~40 min + scoring | ~4.5–7.5 h | **≈ 6–8 h ≈ $3–4** |

If the budget cap approaches during Phase B, kill the queue after the current model — Phase A
results are complete and every batch is skip-exists resumable on a fresh pod.

## 4. Package + download EVERYTHING (pod is ephemeral!)

```bash
tar czf /workspace/results_trio_$(date +%Y%m%d).tar.gz out out170 out_preflight logs \
  $(ls out/*/**.pose.json 2>/dev/null)      # cupid's camera-pose sidecars ride along
for v in /workspace/envs/*; do "$v/bin/pip" freeze > "$v-freeze.txt" 2>/dev/null; done
tar czf /workspace/freeze_trio_$(date +%Y%m%d).tar.gz /workspace/envs/*-freeze.txt
```

From the LOCAL machine:

```bash
scp -P <PORT> root@<POD>:/workspace/results_trio_*.tar.gz /c/Users/dimik/3DpicToIFCModeling/deliverable/
scp -P <PORT> root@<POD>:/workspace/freeze_trio_*.tar.gz  /c/Users/dimik/3DpicToIFCModeling/deliverable/
```

**Verify both tarballs open locally (`tar tzf`) BEFORE shutting the pod down.**

## 5. Shutdown checklist

- [ ] results tarball downloaded AND verified locally
- [ ] `out/cloud_scores.csv` has rows for every gated model × 10 items
- [ ] preflight verdict per model recorded (OK / FAIL + reason) — a FAIL is a paper result too
- [ ] SceneGen VGGT question answered: does inference import/require `checkpoints/VGGT-1B`?
      (→ decides deployable-vs-benchmark-only; update SCENEGEN.md licence section)
- [ ] THEN: RunPod console → Stop → Terminate pod (billing ends)

## 6. Back home — integrate

```bash
# drop out/<model>/<key>.glb + out170 meshes into the gallery as labelled candidates:
python benchmark/build_candidates.py && python benchmark/build_gallery.py
# flip docs/COMPARATIVE_ANALYSIS.md Study-D trio rows from "kit ready" to scores,
# promote the three manuals from DRAFT with the real fix chains,
# and update docs/HF_CENSUS_2026-07.md §2 with the verdicts.
```

## Known landmines (inherited — don't rediscover)

| Symptom | Fix |
|---|---|
| setup.sh tries to make a conda env | run without `--new-env` inside the venv (SCENEGEN.md #1 / CUPID.md #1) |
| flash-attn ABI crash in a TRELLIS-family repo | `ATTN_BACKEND=sdpa` (both drafts pin it already) |
| spconv wrong-CUDA wheel | `spconv-cu120`/`cu118` retry (TRELLIS lesson) |
| pytorch3d build failure (cupid) | stable tag + `--no-build-isolation` + CUDA_HOME (SAM3D lesson) |
| 3DTopia-XL `make` fails in dva/mvp extensions | nvcc on PATH, `TORCH_CUDA_ARCH_LIST=8.6` (A5000/4090) |
| preflight mesh <50 KB | model produced a stub — read `cloud_bundle/logs/<model>.log`, fix, re-run queue (skip-exists) |
| scenegen: empty/garbage masks | re-run `precompute_masks.py`; check `masks/<key>.png` exists per item |
