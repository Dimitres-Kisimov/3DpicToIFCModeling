# RUNBOOK — Remaining-AI Pod Run (TRELLIS.2 · SF3D · SAM 3D re-run · TripoSG re-verify)

**Goal:** score the untested generators on the SAME 10 single front-view images,
ground truths, scorer and seed as the Research-tab 5-AI study; test the app's
pipeline against each AI's output; bring EVERYTHING home before the pod dies.

**Pod:** RunPod → **A100 80 GB** (preferred; the manuals' endorsed config) or
**RTX A6000 48 GB** (cheaper) → template *RunPod PyTorch 2.x (CUDA ≥ 12.4)* →
**disk 120 GB**. Cost: ~4 h ≈ $3–8. A 24 GB 4090 is borderline for SAM 3D +
TRELLIS.2 — only use it if nothing bigger is available.

**Operator note:** every step below is copy-paste; run them in order. If a step
fails, the per-model manual in `manuals/` has the fix table.

## 0. From the LOCAL machine — upload bundle + repo (bundle is gitignored!)

```bash
cd /c/Users/dimik/3DpicToIFCModeling
tar czf /tmp/cloud_bundle.tar.gz -C deliverable cloud_bundle
scp -P <PORT> /tmp/cloud_bundle.tar.gz root@<POD>:/workspace/
ssh -p <PORT> root@<POD> "cd /workspace && tar xzf cloud_bundle.tar.gz && \
  git clone --depth 1 https://github.com/Dimitres-Kisimov/3DpicToIFCModeling.git"
```

## 1. On the pod — install (parallel, ~20–40 min)

```bash
cd /workspace/cloud_bundle
# HF login only needed for sf3d (gated weights — accept licence on the model page first)
huggingface-cli login   # optional, sf3d only
MODELS="trellis2 sf3d sam3d triposg" bash install_models.sh
tail -f logs/install_trellis2.log   # watch the risky one; manuals/TRELLIS2.md has the fix table
```

## 2. Generate — same inputs, seed 42, one model at a time on the GPU

```bash
python run_cloud_benchmark.py --models trellis2,sf3d,sam3d,triposg
# outputs: out/<model>/<key>.glb  (10 items each; skip-exists → safe to re-run)
```

Segmentation variants (where the model accepts an external cutout): re-run with
pre-segmented inputs into a separate model name so both get scored:

```bash
python run_cloud_benchmark.py --models sf3d --out out_seg   # sf3d does its own rembg; raw vs cutout A/B
```

## 3. Score — identical metric to the Research-tab table

```bash
python score_all.py --out out              # Chamfer + F@0.02, ICP, vs the same ABO gt
cat out/cloud_scores.csv
```

## 4. App-pipeline test — "what works and what doesn't inside the product"

```bash
pip install trimesh pymeshfix fast_simplification scipy ifcopenshell
python app_pipeline_test.py out/ apptest/ --repo /workspace/3DpicToIFCModeling
cat apptest/report.csv                     # repair + real IFC4 export per model x item
```

## 5. Package + download EVERYTHING (pod is ephemeral!)

```bash
# results (small): meshes, scores, app-test, logs
tar czf /workspace/results_$(date +%Y%m%d).tar.gz out out_seg apptest logs
# weights archive (~30–40 GB): HF cache + venv freeze lists (NOT the venvs themselves)
for v in /workspace/envs/*; do "$v/bin/pip" freeze > "$v-freeze.txt" 2>/dev/null; done
tar czf /workspace/weights_$(date +%Y%m%d).tar.gz \
  ~/.cache/huggingface /workspace/envs/*-freeze.txt
```

From the LOCAL machine:

```bash
scp -P <PORT> root@<POD>:/workspace/results_*.tar.gz  /c/Users/dimik/3DpicToIFCModeling/deliverable/
scp -P <PORT> root@<POD>:/workspace/weights_*.tar.gz  /d/scs_weights/   # or any 40GB+ disk
```

**Verify both tarballs open locally (`tar tzf`) BEFORE shutting the pod down.**

## 6. Shutdown checklist

- [ ] results tarball downloaded AND verified locally
- [ ] weights tarball downloaded AND verified locally
- [ ] cloud_scores.csv rows present for every model × 10 items
- [ ] apptest/report.csv present
- [ ] THEN: RunPod console → Stop → Terminate pod (billing ends)

## 7. Back home — integrate

```bash
# scores + meshes into the benchmark visualizer as extra candidates:
#   drop out/<model>/<key>.glb into benchmark/results/... as <model>.glb, then
python benchmark/build_candidates.py && python benchmark/build_gallery.py
# gallery/Research tab table update + docs/HUGGINGFACE_MODEL_NARROWING.md stage-5 flip to "tested"
```

## Known landmines (from the H200 session — don't rediscover)

| Symptom | Fix |
|---|---|
| `torchvision::nms does not exist` | `--no-deps` xformers (TRELLIS manual #1) |
| nvdiffrast/diffoctreerast build fail | `--no-build-isolation`, CUDA_HOME set (manual #6/#7) |
| SAM 3D flash-attn ABI crash | force sdpa backend (SAM3D.md) |
| TRELLIS.2 loads nothing with v1 code | it's a SEPARATE repo/package — trellis2 + o_voxel (TRELLIS2.md) |
| sf3d weights 403 | accept licence on hf.co/stabilityai/stable-fast-3d + `huggingface-cli login` |
| `utils3d` attribute error | install the pinned commit from the repo's setup (manual #8) |
