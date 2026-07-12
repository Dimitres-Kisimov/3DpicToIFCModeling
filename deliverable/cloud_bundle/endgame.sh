#!/bin/bash
# endgame.sh — last-dollars plan (~$5 balance): 3DTopia-XL verdict (install already
# paid for) -> Study E multi-image -> final tarball -> READY_TO_STOP.
L=/workspace/logs/queue_rest.log
mark(){ echo "$1 $(date +%H:%M)" >> $L; }
mark EG_START
cd /workspace/cloud_bundle
export CUDA_HOME=/usr/local/cuda TORCH_CUDA_ARCH_LIST=8.0 TMPDIR=/workspace/tmp

while pgrep -f 'install[_]models' > /dev/null; do sleep 60; done
rm -f out_preflight/3dtopiaxl/*.glb 2>/dev/null
python run_cloud_benchmark.py --models 3dtopiaxl --manifest preflight_manifest.json --out out_preflight >> $L 2>&1
f=$(ls out_preflight/3dtopiaxl/*.glb 2>/dev/null | head -1)
if [ -n "$f" ] && [ "$(stat -c%s "$f")" -ge 50000 ]; then
  mark 'EG_TOPIA_GATE_OK — new engine generating'
  python run_cloud_benchmark.py --models 3dtopiaxl >> $L 2>&1
  python run_cloud_benchmark.py --models 3dtopiaxl --manifest bench170_manifest.json --out out170 >> $L 2>&1
  mark "EG_TOPIA_DONE r10=$(ls out/3dtopiaxl/*.glb 2>/dev/null | wc -l) s187=$(ls out170/3dtopiaxl/*.glb 2>/dev/null | wc -l)"
else
  mark 'EG_TOPIA_GATE_FAIL — draft recipe; skipped'
fi
rm -rf /root/.cache/huggingface/hub/models--3DTopia* 2>/dev/null

# Study E gets the remaining budget (its slot script waits for this marker)
echo "ALL_ENGINES_FINAL (endgame trim: budget) $(date +%H:%M)" >> $L
setsid nohup bash /workspace/studyE_slot.sh > /dev/null 2>&1 < /dev/null &
until grep -qE 'STUDY_E_COMPLETE|SE_ABORT' $L 2>/dev/null; do sleep 120; done

python score_all.py out >> $L 2>&1
tar czf /workspace/results_final.tar.gz out out170 out_seg apptest logs studyE_manifest.json 2>/dev/null
mark "EG_TARBALL $(ls -la /workspace/results_final.tar.gz | awk '{print $5}') bytes"
mark 'READY_TO_STOP — download results_final.tar.gz, verify locally, then STOP the pod (not terminate: volume persists for a cheap resume)'
