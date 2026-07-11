#!/bin/bash
# queue_trio.sh — census-trio queue (scenegen · cupid · 3dtopiaxl) with per-model preflight gates.
# DRAFT 2026-07-11 — gate pattern copied from queue3_verified.sh; tuned for a CHEAP 24 GB pod
# (RTX A5000 / 4090, ~$0.40–0.70/h — see RUNBOOK_CENSUS_TRIO.md).
#
# Baked-in lessons:
#  - PREFLIGHT: each model must generate ONE real mesh (>50 KB) before any batch;
#    an import error costs 1 minute, not a silent 180-item fabrication.
#  - POSTCHECK: >10 outputs with <3 distinct file sizes = fabricated -> SUSPECT.
#  - TWO PHASES (budget guard, cheap pod): research-10 for ALL models first (the scored result),
#    THEN the 170/187 gallery sweep cheapest-model-first — if money runs out we still have scores.
#  - Masks FIRST: scenegen REQUIRES per-object masks (SAM3D convention, precompute_masks.py);
#    the scenegen venv has rembg, so masks are computed there.
#  - HF caches evicted between models (small cheap-pod disk).
#  - All markers append to /workspace/logs/queue_trio.log (the monitored file).
L=/workspace/logs/queue_trio.log
HUB=/root/.cache/huggingface/hub
cd /workspace/cloud_bundle
mark(){ echo "$1 $(date +%H:%M)" >> $L; }

python3 - <<'PY'
import json
items = json.load(open('manifest.json'))
json.dump(items[:1], open('preflight_manifest.json', 'w'))
PY

preflight(){
  m=$1
  mark "QT_PREFLIGHT $m"
  rm -f out_preflight/$m/*.glb 2>/dev/null
  python run_cloud_benchmark.py --models $m --manifest preflight_manifest.json --out out_preflight >> $L 2>&1
  f=$(ls out_preflight/$m/*.glb 2>/dev/null | head -1)
  if [ -z "$f" ] || [ "$(stat -c%s "$f")" -lt 50000 ]; then
    mark "QT_PREFLIGHT_FAIL $m — skipped, see cloud_bundle/logs/$m.log + manuals fix table"
    return 1
  fi
  mark "QT_PREFLIGHT_OK $m ($(stat -c%s "$f") bytes)"
}

evict(){
  case "$1" in
    scenegen)  rm -rf $HUB/models--facebook--VGGT-1B $HUB/models--facebook--sam2* \
                      $HUB/models--haoningwu--SceneGen 2>/dev/null;;   # local_dir copies under repos/ stay
    cupid)     rm -rf $HUB/models--hbb1--Cupid 2>/dev/null;;
    3dtopiaxl) : ;;                                  # flat .pt files live in repos/3DTopia-XL/pretrained
  esac
}

mark QT_START
# clear stubs from crashed runs so skip-exists cannot keep garbage
find out out170 out_preflight -name '*.glb' -size -50k -delete 2>/dev/null

# the 170/187 gallery manifest is built on the pod from the cloned repo's benchmark photos
[ -f bench170_manifest.json ] || \
  python3 make_bench170_manifest.py /workspace/3DpicToIFCModeling/benchmark/images bench170_manifest.json >> $L 2>&1

mark QT_MASKS   # scenegen needs masks for EVERY item; rembg lives in its own venv
/workspace/envs/scenegen/bin/python precompute_masks.py manifest.json masks >> $L 2>&1
/workspace/envs/scenegen/bin/python precompute_masks.py bench170_manifest.json masks >> $L 2>&1

# ---------------- PHASE A: preflight + research-10 for all three (the scored deliverable) ------
GATED=""
for m in 3dtopiaxl scenegen cupid; do          # cheapest/fastest first
  if preflight $m; then
    python run_cloud_benchmark.py --models $m >> $L 2>&1     # research-10, scored at the end
    GATED="$GATED $m"
    mark "QT_R10_DONE $m n=$(ls out/$m/*.glb 2>/dev/null | wc -l)"
  fi
done
python score_all.py manifest.json out >> $L 2>&1
mark "QT_SCORED r10 models:$GATED"

# ---------------- PHASE B: 170/187 gallery sweep, cheapest-first (stop here if budget is gone) -
for m in $GATED; do
  python run_cloud_benchmark.py --models $m --manifest bench170_manifest.json --out out170 >> $L 2>&1
  sizes=$(ls -la out170/$m/*.glb 2>/dev/null | awk '{print $5}' | sort -u | wc -l)
  n=$(ls out170/$m/*.glb 2>/dev/null | wc -l)
  mark "QT_DONE $m s170=$n distinct_sizes=$sizes"
  if [ "$n" -gt 10 ] && [ "$sizes" -lt 3 ]; then
    mark "QT_SUSPECT $m — outputs nearly identical, treat as fabricated"
  fi
  evict $m
done

mark "QUEUE_TRIO_ALL_DONE vol=$(du -sh /workspace 2>/dev/null | cut -f1) free=$(df -h / | tail -1 | awk '{print $4}')"
