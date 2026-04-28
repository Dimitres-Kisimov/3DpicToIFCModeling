# 3D Picture to IFC Modeling

AI-powered pipeline that converts a single 2D photograph into a 3D mesh and exports it to IFC format for architectural and BIM workflows.

Upload a photo → AI reconstructs the 3D object → inspect it in the browser → export to IFC for Revit / AutoCAD.

---

## Stack

| Layer | Technology |
|-------|-----------|
| Server | Node.js 24 + Express |
| Frontend | Vanilla JS + xeokit SDK v2.6.108 |
| 3D Viewer | xeokit (WebGL, local npm install) |
| AI Inference | Python 3.14 subprocess, GPU-accelerated |
| 3D Reconstruction | TripoSR (stabilityai/TripoSR) |
| Segmentation | rembg (U²-Net) + YOLOv8 segmentation |
| Depth Estimation | Intel DPT (dpt-hybrid-midas) via HuggingFace Transformers |
| Mesh Processing | trimesh, scikit-image, scipy |
| IFC Export | IfcOpenShell |
| Deep Learning | PyTorch 2.11 + CUDA 12.6 |

---

## Requirements

### Hardware
- NVIDIA GPU with CUDA support (tested on RTX 4050 Laptop, 6GB VRAM)
- 8GB+ RAM
- 10GB+ disk (model weights)

### Software
- Node.js 18+
- Python 3.11–3.14
- NVIDIA driver ≥ 520 (CUDA 12.x)

---

## Installation

### 1. Clone and install Node dependencies

```bash
git clone https://github.com/Dimitres-Kisimov/3DpicToIFCModeling.git
cd 3DpicToIFCModeling
npm install
```

### 2. Install Python dependencies

```bash
# PyTorch with CUDA 12.6 (required for GPU acceleration)
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu126

# Core ML and mesh libraries
pip install transformers ultralytics "rembg[cpu]" trimesh scikit-image scipy pillow numpy

# IFC export
pip install ifcopenshell

# HuggingFace hub for model weight downloads
pip install huggingface_hub
```

> **CPU-only fallback**: if you have no NVIDIA GPU, omit the `--index-url` flag.  
> TripoSR will run on CPU (~10–20 min per image instead of ~1–3 min).

### 3. Configure environment

Copy `.env.example` to `.env` (or edit `.env` directly):

```env
PORT=3000
USE_GPU=true                   # set false for CPU-only
PYTHON_PATH=python
PYTHON_SCRIPTS_DIR=./backend/python-scripts
```

### 4. Model weights

Weights are fetched automatically on first use and cached by HuggingFace:

| Model | Size | Cache |
|-------|------|-------|
| stabilityai/TripoSR | ~1.3 GB | `~/.cache/huggingface/` |
| yolov8n-seg.pt | ~6 MB | repo root (committed) |
| rembg u2net | ~176 MB | `~/.u2net/` |
| Intel DPT dpt-hybrid-midas | ~470 MB | `~/.cache/huggingface/` |

### 5. Start

```bash
npm start
# open http://localhost:3000
```

---

## How it works

```
Photo
  │
  ▼
rembg (U²-Net)          — remove background, isolate foreground object
  │
  ▼
TripoSR inference       — transformer encodes image → predicts 3D volume
  │                        marching cubes at 256³ resolution (GPU)
  ▼
Post-processing
  ├─ Component filter   — drop floating debris (<0.5% faces) and spike artifacts
  ├─ Orientation fix    — detect and correct upside-down meshes
  ├─ Laplacian smooth   — 5 iterations, reduce faceted appearance
  └─ PBR material       — median foreground color → GLTF baseColorFactor
  │
  ▼
GLB export (trimesh)
  │
  ▼
xeokit viewer           — WebGL render, orbit/pan/zoom, object picking
  │
  ▼
IFC export              — IfcOpenShell writes geometry + transforms to .ifc
```

### AI model details

**TripoSR** (default — "High quality" mode)
- Single-image 3D reconstruction neural network by Stability AI
- Transformer architecture trained on ~800K 3D objects
- GPU: ~1–3 min at 256³ | CPU: ~10–20 min at 96³
- Outputs a closed mesh with real geometry (not a depth relief)

**InstantMesh / StableFast3D** (alternative modes)
- Use YOLO segmentation + Intel DPT depth estimation
- Produce a 2.5D depth-map mesh of the segmented object
- Faster but geometrically less accurate than TripoSR

---

## Project structure

```
3DpicToIFCModeling/
├── backend/
│   ├── server.js                  # Express entry point
│   ├── ai/
│   │   ├── triposr.js             # TripoSR adapter (calls Python subprocess)
│   │   ├── instantMesh.js         # InstantMesh adapter
│   │   └── stablefast3d.js        # StableFast3D adapter
│   ├── config/
│   ├── middleware/
│   ├── routes/
│   ├── services/
│   │   └── pythonBridge.js        # Spawns Python scripts, parses JSON output
│   ├── python-scripts/
│   │   ├── inference_base.py      # Shared: depth mesh, YOLO segmentation, logging
│   │   ├── run_triposr.py         # TripoSR full pipeline
│   │   ├── run_instantmesh.py     # InstantMesh pipeline
│   │   ├── run_stablefast3d.py    # StableFast3D pipeline
│   │   ├── cleanMesh.py
│   │   ├── createIFCFurniture.py
│   │   ├── fixOrientation.py
│   │   ├── meshToGLB.py
│   │   ├── normalizeMesh.py
│   │   └── saveIFC.py
│   └── triposr/                   # TripoSR source (Stability AI, MIT)
│       └── tsr/
│           ├── system.py
│           ├── utils.py
│           └── models/
│               └── isosurface.py  # Patched: scikit-image marching_cubes
│                                  # (replaces torchmcubes — no C ext needed)
├── frontend/
│   ├── index.html
│   └── js/
│       ├── xeokitViewer.js        # xeokit init, GLB load, camera, picking
│       └── index.js               # UI: upload, model selection, IFC export
├── yolov8n-seg.pt                 # YOLOv8 segmentation weights
├── .env                           # Runtime config (not committed)
├── package.json
├── requirements.txt
└── FULL_DOCUMENTATION.md          # Detailed pipeline and troubleshooting reference
```

---

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/upload` | Upload image, returns `imageId` |
| `POST` | `/api/generate` | Run AI model, returns GLB URL |
| `GET` | `/api/status/:jobId` | Poll generation job status |
| `POST` | `/api/export/ifc` | Export current scene to IFC |
| `GET` | `/outputs/:file` | Serve generated GLB / IFC files |
| `GET` | `/api/health` | Dependency version check |

---

## Known issues

- **Python 3.14**: `torchmcubes` has no wheels for this version — patched with `skimage.measure.marching_cubes` in `backend/triposr/tsr/models/isosurface.py`
- **xeokit vertex colors**: xeokit's GLTFLoaderPlugin ignores `COLOR_0` vertex attributes — colors must be set via GLTF PBR `baseColorFactor` material
- **Color accuracy**: mesh color is derived from median foreground pixels of the rembg-masked image; multi-color objects get a single averaged color
- **TripoSR orientation**: upside-down output is corrected by a Y-centroid heuristic; unusual camera angles may still need manual rotation

---

## Licenses

| Component | License |
|-----------|---------|
| This project | MIT |
| TripoSR (Stability AI) | MIT |
| xeokit SDK | AGPL-3.0 / Commercial |
| YOLOv8 (Ultralytics) | AGPL-3.0 |
| PyTorch | BSD-3 |
| rembg | MIT |
| trimesh | MIT |
| IfcOpenShell | LGPL-3.0 |

> **Commercial use note**: xeokit SDK and YOLOv8 are AGPL-3.0. For closed-source commercial deployment a commercial license is required from [xeokit.io](https://xeokit.io) and Ultralytics respectively.
