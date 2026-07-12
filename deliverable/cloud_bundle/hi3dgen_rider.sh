#!/bin/bash
# hi3dgen_rider.sh — Hi3DGen (Stable-X/Stable3DGen, MIT) rides the Study E
# trellis env: TRELLIS-based, so the env rebuilt for run_multi_image already
# carries ~90% of its deps. Marginal cost: repo clone + 2 small weight repos +
# gate. The only affordable second new-engine under the $5 endgame.
L=/workspace/logs/queue_rest.log
mark(){ echo "$1 $(date +%H:%M)" >> $L; }

until grep -qE 'STUDY_E_COMPLETE|SE_ABORT' $L 2>/dev/null; do sleep 120; done
while pgrep -f 'run[_]cloud_benchmark|infer[_]' > /dev/null; do sleep 120; done
mark HR_START
cd /workspace/cloud_bundle
export CUDA_HOME=/usr/local/cuda TORCH_CUDA_ARCH_LIST=8.0 TMPDIR=/workspace/tmp

[ -d /workspace/repos/Stable3DGen ] || git clone --quiet --depth 1 https://github.com/Stable-X/Hi3DGen /workspace/repos/Stable3DGen >> /workspace/logs/hr.log 2>&1
/opt/envs/trellis/bin/pip install -q einops "diffusers>=0.28" accelerate >> /workspace/logs/hr.log 2>&1

mark HR_PREFLIGHT
rm -f out_preflight/hi3dgen/*.glb 2>/dev/null
python run_cloud_benchmark.py --models hi3dgen --manifest preflight_manifest.json --out out_preflight >> $L 2>&1
f=$(ls out_preflight/hi3dgen/*.glb 2>/dev/null | head -1)
if [ -z "$f" ] || [ "$(stat -c%s "$f")" -lt 50000 ]; then
  mark 'HR_GATE_FAIL — draft recipe; rider ends (logs/hi3dgen.log)'
  exit 1
fi
mark 'HR_GATE_OK — Hi3DGen generating (2nd new engine tonight)'
python run_cloud_benchmark.py --models hi3dgen >> $L 2>&1
python run_cloud_benchmark.py --models hi3dgen --manifest bench170_manifest.json --out out170 >> $L 2>&1
mark "HR_DONE r10=$(ls out/hi3dgen/*.glb 2>/dev/null | wc -l) s187=$(ls out170/hi3dgen/*.glb 2>/dev/null | wc -l)"
python score_all.py out >> $L 2>&1
tar czf /workspace/results_final.tar.gz out out170 out_seg apptest logs studyE_manifest.json 2>/dev/null
mark 'HR_RETAR done — READY_TO_STOP refreshed with hi3dgen included'
