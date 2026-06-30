# Cloud 3D-gen benchmark — pod runbook

Fair head-to-head of cloud single-image→3D generators against the SAME inputs + ground-truth
meshes TripoSR was tested on locally, scored by the SAME metric (`eval_accuracy.py`).

**Target pod:** RunPod A100 80 GB, "RunPod PyTorch 2.8" template, **100 GB** disk, SSH enabled.
**Cost:** ~$1.39/hr; full run ~1–2.5 hr depending on model set. Hard-capped by prepaid credit.

## Models (`--models` keys)
| key | model | licence | note |
|---|---|---|---|
| `trellis` | microsoft/TRELLIS-image-large | MIT | proven API, fast install |
| `trellis2` | microsoft/TRELLIS.2-4B | MIT | newest; loader may need patch |
| `triposg` | VAST-AI/TripoSG | MIT | best-effort API |
| `instantmesh` | TencentARC/InstantMesh | Apache-2.0 | native full-res on 80 GB |
| `sam3d` | facebook/sam-3d-objects | SAM Licence | gated (needs HF token); slowest install |

## Steps (on the pod, after I SSH in)
```bash
cd /workspace
tar xzf cloud_bundle.tar.gz          # -> /workspace/cloud_bundle/
cd cloud_bundle

# (only for sam3d) export your token so the gated weights download:
# export HUGGING_FACE_HUB_TOKEN=hf_xxx

# 1) one-time install of the chosen models (parallel-friendly; ~20-45 min)
bash install_models.sh trellis triposg                 # <=2 hr target set

# 2) run the benchmark (model-level parallelism; ~15 min inference)
python run_cloud_benchmark.py --models triposg,trellis --parallel 2

# 3) results: out/cloud_scores.csv + out/<model>/<key>.glb + logs/
```

## Time-boxed (≤2 hr) recommendation
`trellis` + `triposg` (drop `sam3d` — it's the install/time risk). Add `instantmesh` if installs go smoothly.

## What comes back to the local machine
The `out/` folder (meshes + `cloud_scores.csv`) and `logs/`. Locally we then:
- **re-score every model together** (incl. TripoSR `_sam2`/`_rembg`) with the identical metric → one fair table,
- **IFC4-export + validate** each generated mesh (CPU, $0) to confirm BIM compliance,
- drop the new columns into the dashboard / paper.

## Notes
- `install_models.sh` and the `infer_*.py` are best-effort from each repo's docs; TRELLIS.2/TripoSG/SAM3D
  loaders or entrypoints may need a small live patch (logs show exactly what's available).
- Object identification (which furniture it is) is **not** done by these generators — that's the DETR
  detection stage in `run_detect_and_place.py`, handled separately/locally.
- **Terminate the pod when done** — billing runs until you do.
