#!/bin/bash
# sam3d_final.sh — last SAM 3D attempt of the campaign, after makeup slots.
# Differences from the failed queue4 slot: (a) requirements.p3d.txt (prebuilt
# pytorch3d/kaolin/gsplat wheels for torch 2.5.1+cu121) BEFORE inference reqs,
# (b) per-line soft-fail on requirements.inference.txt, (c) numpy toggle —
# tonight's env hit `np.long` (a numpy-2.x symbol) with the manual's 1.26.4 pin,
# so try 1.26.4 first (H200-proven), then 2.1.* if the import chain demands it.
L=/workspace/logs/queue_rest.log
HUB=/root/.cache/huggingface/hub
mark(){ echo "$1 $(date +%H:%M)" >> $L; }

until grep -q MAKEUP_ALL_DONE $L 2>/dev/null; do sleep 120; done
mark S3F_START
cd /workspace/cloud_bundle
export CUDA_HOME=/usr/local/cuda TORCH_CUDA_ARCH_LIST=8.0 TMPDIR=/workspace/tmp

python3 -m venv /opt/envs/sam3d
ln -sfn /opt/envs/sam3d /workspace/envs/sam3d
P=/opt/envs/sam3d/bin/pip
$P install -q torch==2.5.1 torchvision==0.20.1 --index-url https://download.pytorch.org/whl/cu121 >> $L 2>&1
$P install -q -r /workspace/repos/SAM3D/requirements.p3d.txt >> /workspace/logs/s3f.log 2>&1
while read -r req; do
  case "$req" in ''|\#*) continue;; esac
  $P install -q "$req" >> /workspace/logs/s3f.log 2>&1 || echo "S3F_REQ_SOFT_FAIL $req" >> $L
done < /workspace/repos/SAM3D/requirements.inference.txt
$P install -q loguru timm==0.9.16 spconv-cu121==2.3.8 open3d trimesh optree astor rootutils \
  randomname opencv-python roma einops xatlas Rtree omegaconf scikit-image tifffile plyfile \
  lightning pyvista pymeshfix igraph hydra-core seaborn "werkzeug==3.0.6" >> /workspace/logs/s3f.log 2>&1
$P install -q "git+https://github.com/microsoft/MoGe.git@a8c37341bc0325ca99b9d57981cc3bb2bd3e255b" >> /workspace/logs/s3f.log 2>&1
F=/workspace/repos/SAM3D/sam3d_objects/model/backbone/tdfy_dit/modules/sparse/__init__.py
grep -q 'ATTN = "sdpa"' "$F" || sed -i '/__from_env()/a ATTN = "sdpa"' "$F"

test_import(){ /opt/envs/sam3d/bin/python /tmp/t_sam3d.py 2>&1 | tail -1; }
for NP in "numpy==1.26.4" "numpy==2.1.*"; do
  $P install -q "$NP" >> /workspace/logs/s3f.log 2>&1
  R=$(test_import)
  mark "S3F_IMPORT [$NP] $R"
  echo "$R" | grep -q IMPORT_OK && break
done

if ! test_import | grep -q IMPORT_OK; then
  mark "S3F_ABORT — import chain still broken; freeze+logs kept for morning forensics"
  exit 1
fi

mark S3F_PREFLIGHT
rm -f out_preflight/sam3d/*.glb 2>/dev/null
python run_cloud_benchmark.py --models sam3d --manifest preflight_manifest.json --out out_preflight >> $L 2>&1
f=$(ls out_preflight/sam3d/*.glb 2>/dev/null | head -1)
if [ -z "$f" ] || [ "$(stat -c%s "$f")" -lt 50000 ]; then
  mark "S3F_PREFLIGHT_FAIL — see logs/sam3d.log"
  exit 1
fi
mark "S3F_PREFLIGHT_OK — first verified SAM 3D mesh of the campaign"
python run_cloud_benchmark.py --models sam3d >> $L 2>&1
python run_cloud_benchmark.py --models sam3d --manifest bench170_manifest.json --out out170 >> $L 2>&1
mark "S3F_DONE r10=$(ls out/sam3d/*.glb 2>/dev/null | wc -l) s187=$(ls out170/sam3d/*.glb 2>/dev/null | wc -l)"
rm -rf $HUB/models--facebook--sam-3d-objects 2>/dev/null
python score_all.py out >> $L 2>&1
python app_pipeline_test.py out/ apptest/ --repo /workspace/repo3d >> $L 2>&1
mark "SAM3D_CAMPAIGN_COMPLETE — full campaign truly finished"
