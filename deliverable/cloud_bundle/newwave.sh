#!/bin/bash
# newwave.sh — the NEW AIs get their GPU time: 3DTopia-XL, Hi3DGen, PartCrafter,
# Direct3D-S2, Step1X-3D, SceneGen (benchmark-only tier; Cupid ON HOLD per user).
# One engine per slot: install (draft recipe) -> 1-mesh preflight gate -> 10+187
# -> weight eviction + env teardown. Draft recipes are unproven: a slot that
# fails its gate is marked and skipped — no debugging loops burn GPU money.
L=/workspace/logs/queue_rest.log
HUB=/root/.cache/huggingface/hub
mark(){ echo "$1 $(date +%H:%M)" >> $L; }

# USER REORDER 2026-07-12: new engines run FIRST — do not wait for the old roster.
while pgrep -f 'run[_]cloud_benchmark|infer[_]' > /dev/null; do sleep 120; done
mark NW_START
cd /workspace/cloud_bundle
export CUDA_HOME=/usr/local/cuda TORCH_CUDA_ARCH_LIST=8.0 TMPDIR=/workspace/tmp

slot(){  # $1 engine
  m=$1
  mark "NW_${m}_INSTALL free=$(df -h / | tail -1 | awk '{print $4}')"
  pip cache purge >/dev/null 2>&1
  bash install_models.sh $m >> /workspace/logs/nw_$m.log 2>&1
  mark "NW_${m}_PREFLIGHT"
  rm -f out_preflight/$m/*.glb 2>/dev/null
  python run_cloud_benchmark.py --models $m --manifest preflight_manifest.json --out out_preflight >> $L 2>&1
  f=$(ls out_preflight/$m/*.glb 2>/dev/null | head -1)
  if [ -z "$f" ] || [ "$(stat -c%s "$f")" -lt 50000 ]; then
    mark "NW_${m}_GATE_FAIL — draft recipe needs work, slot skipped (logs/nw_$m.log + logs/$m.log)"
  else
    mark "NW_${m}_GATE_OK — new engine generating"
    python run_cloud_benchmark.py --models $m >> $L 2>&1
    python run_cloud_benchmark.py --models $m --manifest bench170_manifest.json --out out170 >> $L 2>&1
    sizes=$(ls -la out170/$m/*.glb 2>/dev/null | awk '{print $5}' | sort -u | wc -l)
    mark "NW_${m}_DONE r10=$(ls out/$m/*.glb 2>/dev/null | wc -l) s187=$(ls out170/$m/*.glb 2>/dev/null | wc -l) distinct_sizes=$sizes"
  fi
  # teardown: env + weights are scripted-rebuildable; outputs are kept forever
  [ -d /workspace/envs/$m ] && /workspace/envs/$m/bin/pip freeze > /workspace/$m-freeze.txt 2>/dev/null
  rm -rf /workspace/envs/$m /opt/envs/$m 2>/dev/null
  find $HUB -maxdepth 1 -name 'models--*' -newer /workspace/newwave_epoch -exec rm -rf {} + 2>/dev/null
}

touch /workspace/newwave_epoch
for m in 3dtopiaxl hi3dgen partcrafter direct3ds2 step1x3d scenegen; do
  touch /workspace/newwave_epoch
  slot $m
done

python score_all.py out >> $L 2>&1
mark "NEWWAVE_ALL_DONE — new-AI coverage at maximum; scores updated"

# then the old-roster leftovers: SAM 3D re-run, InstantMesh 187-sweep
setsid nohup bash /workspace/s3y_run.sh > /dev/null 2>&1 < /dev/null &
sleep 60
until grep -qE 'SAM3D_TRULY_COMPLETE|S3Y_ABORT|S3Y_PREFLIGHT_FAIL' $L 2>/dev/null; do sleep 300; done
/opt/envs/instantmesh/bin/pip install -q pytorch_lightning lightning >> $L 2>&1
cd /workspace/cloud_bundle
python run_cloud_benchmark.py --models instantmesh --manifest bench170_manifest.json --out out170 >> $L 2>&1
mark "IM_FINAL s187=$(ls out170/instantmesh/*.glb 2>/dev/null | wc -l)"
python score_all.py out >> $L 2>&1
mark "ALL_ENGINES_FINAL — everything attempted; download-ready"
