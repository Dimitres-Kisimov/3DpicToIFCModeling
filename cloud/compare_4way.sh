#!/usr/bin/env bash
# compare_4way.sh — single-image → 3D, four ways, on a cloud GPU.
#
#   TripoSR        MIT             (reliable)
#   InstantMesh    Apache-2.0      (reliable)
#   TRELLIS        MIT             (best-effort: heavy CUDA build)
#   SAM 3D Objects SAM Licence     (best-effort: recent repo, entrypoint may differ)
#
# Target box : RunPod A40 48GB, template "PyTorch 2.4 / CUDA 11.8", Ubuntu, /workspace persistent.
# Usage      : bash compare_4way.sh /workspace/input.png
# Deliverable: /workspace/comparison/comparison_report.html  + the 4 GLBs in that folder.
#
# Design notes:
#   * NO `set -e` — every model is isolated; one failing must not kill the others.
#   * Each model gets its own venv (--system-site-packages shares torch, shadows conflicting deps).
#   * Reliable models run FIRST so a mid-run crash/budget-stop still leaves usable output.
#   * Per-model logs in /workspace/comparison/logs/<model>.log.

set -u

INPUT="${1:-/workspace/input.png}"
ROOT=/workspace
REPOS="$ROOT/repos"
ENVS="$ROOT/envs"
OUT="$ROOT/comparison"
LOGS="$OUT/logs"
mkdir -p "$REPOS" "$ENVS" "$OUT" "$LOGS"

if [ ! -f "$INPUT" ]; then
  echo "FATAL: input image not found at '$INPUT'."
  echo "Upload your executive-chair photo to $INPUT (RunPod Files tab) and re-run."
  exit 1
fi
cp "$INPUT" "$OUT/input.png" 2>/dev/null || true

STATS="$OUT/stats.csv"
echo "model,status,seconds,peak_vram_mb,verts,faces,filesize_bytes,glb" > "$STATS"

log(){ echo -e "\n=== [$(date +%H:%M:%S)] $* ==="; }

# ----------------------------------------------------------------------------
# system build deps + headless renderer (in base python)
# ----------------------------------------------------------------------------
log "Installing system build deps (apt) — see $LOGS/apt.log"
apt-get update -y >"$LOGS/apt.log" 2>&1
DEBIAN_FRONTEND=noninteractive apt-get install -y \
  git build-essential ninja-build pkg-config \
  libgl1 libglib2.0-0 libegl1 libgles2 libglvnd-dev >>"$LOGS/apt.log" 2>&1

pip install -q --upgrade pip >/dev/null 2>&1
log "Installing headless renderer (pyrender/EGL) into base python — see $LOGS/render_setup.log"
pip install -q pyrender trimesh imageio numpy pillow >"$LOGS/render_setup.log" 2>&1

export CUDA_HOME="${CUDA_HOME:-/usr/local/cuda}"
export PATH="$CUDA_HOME/bin:$PATH"
export TORCH_CUDA_ARCH_LIST="8.6"        # A40 = sm_86
export PYOPENGL_PLATFORM=egl
export HF_HUB_ENABLE_HF_TRANSFER=0
# HF token (optional) is read from env HUGGING_FACE_HUB_TOKEN — never hard-coded here.

# ----------------------------------------------------------------------------
# helper python tools (written once, used by every stage)
# ----------------------------------------------------------------------------
cat > "$OUT/mesh_stats.py" <<'PY'
import sys, trimesh
try:
    m = trimesh.load(sys.argv[1], force='mesh')
    print(len(m.vertices), len(m.faces))
except Exception:
    print("0 0")
PY

cat > "$OUT/render_views.py" <<'PY'
import sys, os, numpy as np
os.environ.setdefault("PYOPENGL_PLATFORM", "egl")
mesh_path, out_png = sys.argv[1], sys.argv[2]
W = H = 400
def placeholder(msg):
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (W*4, H), (40, 40, 40))
    ImageDraw.Draw(im).text((20, H//2), msg, fill=(230, 90, 90))
    im.save(out_png)
try:
    import trimesh, imageio.v2 as imageio, pyrender
    tm = trimesh.load(mesh_path, force='mesh')
    if tm.vertices.shape[0] == 0:
        raise RuntimeError("empty mesh")
    tm.apply_translation(-tm.centroid)
    tm.apply_scale(1.0 / max(float(tm.extents.max()), 1e-6))
    frames = []
    for ang in (0, 90, 180, 270):
        scene = pyrender.Scene(bg_color=[255, 255, 255, 255], ambient_light=[0.45, 0.45, 0.45])
        R = trimesh.transformations.rotation_matrix(np.radians(ang), [0, 1, 0])
        m = tm.copy(); m.apply_transform(R)
        scene.add(pyrender.Mesh.from_trimesh(m, smooth=False))
        cam_pose = np.array([[1,0,0,0],[0,1,0,0.35],[0,0,1,2.3],[0,0,0,1]], dtype=float)
        scene.add(pyrender.PerspectiveCamera(yfov=np.pi/4.0), pose=cam_pose)
        scene.add(pyrender.DirectionalLight(intensity=3.5), pose=cam_pose)
        r = pyrender.OffscreenRenderer(W, H)
        color, _ = r.render(scene); r.delete()
        frames.append(color)
    imageio.imwrite(out_png, np.concatenate(frames, axis=1))
except Exception as e:
    placeholder("render failed: %s" % (str(e)[:60]))
PY

cat > "$OUT/make_report.py" <<'PY'
import csv, os, html
OUT = os.path.dirname(os.path.abspath(__file__))
rows = list(csv.DictReader(open(os.path.join(OUT, "stats.csv"))))
def mb(b):
    try: return "%.1f MB" % (int(b)/1e6)
    except: return "-"
def fmt(n):
    try: return "{:,}".format(int(n))
    except: return "-"
cards, trows = [], []
for r in rows:
    m = r["model"]; ok = r["status"] == "ok"
    badge = "#2e7d32" if ok else "#b71c1c"
    png = "%s.png" % m
    img = '<img src="%s" style="width:100%%;border:1px solid #ccc;border-radius:6px">' % png \
          if os.path.exists(os.path.join(OUT, png)) else '<div class="noimg">no preview</div>'
    glb = "%s.glb" % m
    dl = '<a href="%s" download>%s</a>' % (glb, glb) if os.path.exists(os.path.join(OUT, glb)) else '<span class="muted">no glb</span>'
    cards.append(f'''<div class="card">
      <div class="hdr"><span class="name">{html.escape(m)}</span>
      <span class="badge" style="background:{badge}">{r["status"].upper()}</span></div>
      {img}
      <div class="meta">{dl} &middot; <a href="logs/{m}.log">log</a></div></div>''')
    trows.append(f'''<tr><td>{m}</td><td>{r["status"]}</td><td>{r["seconds"]}s</td>
      <td>{r["peak_vram_mb"]} MB</td><td>{fmt(r["verts"])}</td><td>{fmt(r["faces"])}</td><td>{mb(r["filesize_bytes"])}</td></tr>''')
inp = '<img src="input.png" style="height:200px;border:1px solid #ccc;border-radius:6px">' if os.path.exists(os.path.join(OUT,"input.png")) else ""
doc = f'''<!doctype html><meta charset=utf-8><title>4-way single-image-to-3D comparison</title>
<style>
body{{font:15px/1.5 system-ui,Segoe UI,Arial;margin:32px;color:#1a1a1a;background:#fafafa}}
h1{{margin:0 0 4px}} .sub{{color:#666;margin-bottom:24px}}
.grid{{display:grid;grid-template-columns:repeat(2,1fr);gap:18px;margin:20px 0}}
.card{{background:#fff;border:1px solid #e0e0e0;border-radius:10px;padding:14px}}
.hdr{{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px}}
.name{{font-weight:600;font-size:17px}} .badge{{color:#fff;padding:2px 9px;border-radius:12px;font-size:12px}}
.meta{{margin-top:8px;font-size:13px}} .muted,.noimg{{color:#999}}
.noimg{{padding:60px 0;text-align:center;border:1px dashed #ccc;border-radius:6px}}
table{{border-collapse:collapse;width:100%;background:#fff}} td,th{{border:1px solid #e0e0e0;padding:8px 12px;text-align:right}}
th:first-child,td:first-child{{text-align:left}} thead{{background:#f0f0f0}}
.note{{color:#666;font-size:13px;margin-top:18px}}
</style>
<h1>Single-image → 3D: 4-way comparison</h1>
<div class=sub>Each preview = 4 orbit angles (0/90/180/270) at the same normalized scale.</div>
<div><b>Input:</b><br>{inp}</div>
<div class=grid>{''.join(cards)}</div>
<h2>Stats</h2>
<table><thead><tr><th>model</th><th>status</th><th>time</th><th>peak VRAM</th><th>verts</th><th>faces</th><th>file</th></tr></thead>
<tbody>{''.join(trows)}</tbody></table>
<div class=note>peak VRAM = whole-GPU max during that stage (nvidia-smi, 1 Hz). BUILD FAILED rows: open the log for the exact error.</div>'''
open(os.path.join(OUT, "comparison_report.html"), "w", encoding="utf-8").write(doc)
print("wrote", os.path.join(OUT, "comparison_report.html"))
PY

# ----------------------------------------------------------------------------
# stage plumbing
# ----------------------------------------------------------------------------
mkvenv(){ python -m venv "$ENVS/$1" --system-site-packages; }

start_vram(){ : > "$LOGS/vram_$1.log"; ( while true; do
  nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits >> "$LOGS/vram_$1.log" 2>/dev/null; sleep 1; done ) & echo $!; }
peak_vram(){ sort -n "$LOGS/vram_$1.log" 2>/dev/null | tail -1; }

emit(){ # model status seconds vram glb
  local m="$1" s="$2" sec="$3" vram="$4" glb="$5" verts=0 faces=0 size=0
  if [ -n "$glb" ] && [ -f "$glb" ]; then
    size=$(stat -c%s "$glb" 2>/dev/null || echo 0)
    read verts faces < <(python "$OUT/mesh_stats.py" "$glb" 2>/dev/null || echo "0 0")
    cp "$glb" "$OUT/$m.glb" 2>/dev/null || true
    python "$OUT/render_views.py" "$OUT/$m.glb" "$OUT/${m}.png" >>"$LOGS/render_$m.log" 2>&1 || true
  else
    s="failed"
  fi
  echo "$m,$s,$sec,${vram:-0},$verts,$faces,$size,$OUT/$m.glb" >> "$STATS"
}

run_stage(){ # model
  local m="$1"
  log "STAGE: $m"
  local t0 vpid glb status t1 sec vram
  t0=$(date +%s)
  vpid=$(start_vram "$m")
  status="ok"
  glb=$("stage_$m" 2>>"$LOGS/$m.log") || status="failed"
  kill "$vpid" 2>/dev/null
  t1=$(date +%s); sec=$((t1 - t0))
  vram=$(peak_vram "$m")
  [ -n "$glb" ] && [ -f "$glb" ] || status="failed"
  emit "$m" "$status" "$sec" "${vram:-0}" "$glb"
  log "STAGE $m: status=$status time=${sec}s peakVRAM=${vram:-0}MB"
  # regenerate report after every stage so partial results are viewable immediately
  python "$OUT/make_report.py" >/dev/null 2>&1 || true
}

# ----------------------------------------------------------------------------
# stage_*  — must print ONLY the produced .glb path on stdout. All install/run
# chatter goes to the per-model log via run_stage's redirect.
# ----------------------------------------------------------------------------
stage_triposr(){
  local V="$ENVS/triposr"
  { mkvenv triposr; source "$V/bin/activate"
    pip install -q transformers einops omegaconf trimesh rembg onnxruntime pillow imageio numpy
    pip install -q git+https://github.com/tatsy/torchmcubes.git
    [ -d "$REPOS/TripoSR" ] || git clone --depth 1 https://github.com/VAST-AI-Research/TripoSR "$REPOS/TripoSR"
    cd "$REPOS/TripoSR" && pip install -q -r requirements.txt
    python run.py "$INPUT" --output-dir "$REPOS/TripoSR/out" --model-save-format glb
    deactivate
  } 1>&2
  echo "$REPOS/TripoSR/out/0/mesh.glb"
}

stage_instantmesh(){
  local V="$ENVS/instantmesh"
  { mkvenv instantmesh; source "$V/bin/activate"
    pip install -q transformers==4.40.0 diffusers==0.27.2 huggingface_hub==0.23.0 \
      pytorch-lightning==2.1.2 einops omegaconf trimesh rembg onnxruntime \
      imageio imageio-ffmpeg pillow numpy xatlas plyfile
    pip install -q git+https://github.com/NVlabs/nvdiffrast.git
    [ -d "$REPOS/InstantMesh" ] || git clone --depth 1 https://github.com/TencentARC/InstantMesh "$REPOS/InstantMesh"
    cd "$REPOS/InstantMesh"
    python run.py configs/instant-mesh-base.yaml "$INPUT" --output_path "$REPOS/InstantMesh/out" \
      || python run.py configs/instant-mesh-base.yaml "$INPUT"
    local obj
    obj=$(ls "$REPOS/InstantMesh/out/instant-mesh-base/meshes/"*.obj 2>/dev/null | head -1)
    [ -z "$obj" ] && obj=$(ls "$REPOS/InstantMesh/outputs/instant-mesh-base/meshes/"*.obj 2>/dev/null | head -1)
    if [ -n "$obj" ]; then
      python -c "import trimesh,sys; trimesh.load(sys.argv[1]).export(sys.argv[2])" "$obj" "$REPOS/InstantMesh/out.glb"
    fi
    deactivate
  } 1>&2
  echo "$REPOS/InstantMesh/out.glb"
}

stage_trellis(){
  local V="$ENVS/trellis"
  { mkvenv trellis; source "$V/bin/activate"
    [ -d "$REPOS/TRELLIS" ] || git clone --recurse-submodules https://github.com/microsoft/TRELLIS "$REPOS/TRELLIS"
    cd "$REPOS/TRELLIS"
    pip install -q pillow imageio imageio-ffmpeg trimesh numpy scipy easydict \
      opencv-python-headless tqdm einops omegaconf rembg onnxruntime
    pip install -q xformers
    pip install -q flash-attn --no-build-isolation
    pip install -q spconv-cu118
    pip install -q git+https://github.com/NVlabs/nvdiffrast.git
    pip install -q git+https://github.com/JeffreyXiang/diffoctreerast.git
    pip install -q utils3d
    SPCONV_ALGO=native ATTN_BACKEND=flash-attn python - "$INPUT" <<'PY'
import sys, os
os.environ.setdefault("SPCONV_ALGO", "native")
from PIL import Image
from trellis.pipelines import TrellisImageTo3DPipeline
from trellis.utils import postprocessing_utils
pipe = TrellisImageTo3DPipeline.from_pretrained("microsoft/TRELLIS-image-large")
pipe.cuda()
out = pipe.run(Image.open(sys.argv[1]).convert("RGB"), seed=42)
glb = postprocessing_utils.to_glb(out['gaussian'][0], out['mesh'][0], simplify=0.95, texture_size=1024)
glb.export("/workspace/repos/TRELLIS/out.glb")
PY
    deactivate
  } 1>&2
  echo "$REPOS/TRELLIS/out.glb"
}

stage_sam3d(){
  # Best-effort: SAM 3D Objects is recent; if the entrypoint differs the log
  # will show the repo's README command to plug in.
  local V="$ENVS/sam3d"
  { mkvenv sam3d; source "$V/bin/activate"
    pip install -q "git+https://github.com/facebookresearch/pytorch3d.git@stable"
    local cloned=0
    for url in \
      https://github.com/facebookresearch/sam-3d-objects \
      https://github.com/facebookresearch/sam3d-objects ; do
      git clone --depth 1 "$url" "$REPOS/SAM3D" && { cloned=1; break; }
    done
    [ "$cloned" = 1 ] || { echo "could not locate SAM 3D Objects repo"; deactivate; exit 1; }
    cd "$REPOS/SAM3D"
    pip install -q -e . || pip install -q -r requirements.txt || true
    python -m sam3d_objects.demo --image "$INPUT" --output "$REPOS/SAM3D/out.glb" \
      || python demo.py --image "$INPUT" --output "$REPOS/SAM3D/out.glb" \
      || { echo "SAM3D entrypoint differs — check README in $REPOS/SAM3D"; ls -1; }
    deactivate
  } 1>&2
  echo "$REPOS/SAM3D/out.glb"
}

# ----------------------------------------------------------------------------
# run — reliable models first
# ----------------------------------------------------------------------------
log "GPU:"; nvidia-smi --query-gpu=name,memory.total --format=csv,noheader || true
log "Input image: $INPUT"

run_stage triposr
run_stage instantmesh
run_stage trellis
run_stage sam3d

python "$OUT/make_report.py"
log "DONE. Open $OUT/comparison_report.html  (download the folder from RunPod's Files tab)."
echo
echo "Summary:"; column -t -s, "$STATS"
