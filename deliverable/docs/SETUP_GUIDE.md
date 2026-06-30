# ============================================================================
# SETUP GUIDE - 3D Picture to IFC Modeling
# ============================================================================

## Prerequisites

- Node.js 18+ (https://nodejs.org/)
- Python 3.9+ (https://www.python.org/)
- Git (https://git-scm.com/)
- GPU: NVIDIA with CUDA support (optional but recommended)

---

## Installation Steps

### 1. Clone Repository

```bash
cd 3DpicToIFCModeling
git clone https://github.com/Dimitres-Kisimov/3DpicToIFCModeling.git
cd 3DpicToIFCModeling
```

### 2. Install Node.js Dependencies

```bash
npm install
```

This installs:
- Express (web framework)
- CORS (cross-origin support)
- Multer (file upload)
- Dotenv (environment config)
- And other utilities

### 3. Setup Python Environment

#### Option A: Using Conda (Recommended for CUDA)

```bash
# Create conda environment
conda create -n 3d-ifc python=3.9

# Activate environment
conda activate 3d-ifc

# Install PyTorch with CUDA support
conda install pytorch::pytorch torchvision torchaudio pytorch-cuda=11.8 -c pytorch -c nvidia

# Install other dependencies
pip install -r requirements.txt
```

#### Option B: Using venv

```bash
# Create virtual environment
python -m venv venv

# Activate (Windows)
venv\Scripts\activate

# Activate (macOS/Linux)
source venv/bin/activate

# Install PyTorch (CPU-only or with CUDA)
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118

# Install other dependencies
pip install -r requirements.txt
```

### 4. Configure Environment

```bash
# Copy example config
cp .env.example .env

# Edit .env with your settings
# Key settings:
# - PORT=3000
# - USE_GPU=true (if you have CUDA)
# - TEMP_DIR=./temp
# - PYTHON_PATH=python (or full path to Python executable)
```

### 5. Verify Python Environment

```bash
# Activate your Python environment first (conda or venv)

# Run the test script
node backend/server.js

# In another terminal, test API:
curl http://localhost:3000/api/debug/health
```

---

## Running the Application

### Development Mode

```bash
# Terminal 1: Start Node.js server
npm run dev

# Server runs on http://localhost:3000
```

### Production Mode

```bash
npm start
```

---

## Project Structure

```
3DpicToIFCModeling/
├── backend/
│   ├── server.js                 # Express entry point
│   ├── config/
│   │   └── env.js               # Environment configuration
│   ├── middleware/
│   │   ├── logger.js            # Logging utility
│   │   └── errorHandler.js      # Error handling
│   ├── services/
│   │   ├── pythonBridge.js      # Python subprocess executor
│   │   ├── aiRouter.js          # AI model routing (Phase 3)
│   │   ├── meshProcessor.js     # Mesh processing pipeline (Phase 4)
│   │   ├── ifcExporter.js       # IFC export logic (Phase 6)
│   │   └── pipeline.js          # Full workflow (Phase 7)
│   ├── ai/
│   │   ├── instantMesh.js       # InstantMesh adapter
│   │   ├── stableFast3D.js      # StableFast3D adapter
│   │   └── triposr.js           # TripoSR adapter
│   ├── routes/
│   │   ├── apiRoutes.js         # /api/generate, etc.
│   │   ├── objectRoutes.js      # /api/objects
│   │   ├── exportRoutes.js      # /api/export
│   │   └── debugRoutes.js       # /api/debug
│   └── python-scripts/
│       ├── run_instantmesh.py
│       ├── run_stablefast3d.py
│       ├── run_triposr.py
│       ├── cleanMesh.py
│       ├── normalizeMesh.py
│       ├── fixOrientation.py
│       ├── meshToGLB.py
│       ├── createIFCFurniture.py
│       └── saveIFC.py
├── frontend/
│   ├── index.html               # Main UI
│   ├── css/
│   │   └── style.css            # Styling
│   └── js/
│       ├── index.js             # Frontend entry point
│       ├── api.js               # API client
│       ├── xeokitViewer.js      # xeokit initialization (Phase 2)
│       ├── glbLoader.js         # GLB loader (Phase 2)
│       ├── inventory.js         # Inventory system (Phase 2)
│       ├── transformControls.js # Transform controls (Phase 5)
│       └── exporter.js          # Export handler (Phase 6)
├── shared/
│   └── (shared utilities)
├── docs/
│   └── (additional documentation)
├── temp/                        # Temporary files (auto-created)
├── uploads/                     # Upload directory (auto-created)
├── outputs/                     # Output files (auto-created)
├── package.json
├── .env.example
├── .gitignore
└── README.md
```

---

## API Endpoints (Phase 1)

### Health Check

```bash
GET /api/health

# Response
{
  "success": true,
  "message": "Server is running",
  "timestamp": "2026-04-15T10:30:00.000Z"
}
```

### Debug Health (with Python info)

```bash
GET /api/debug/health

# Response
{
  "success": true,
  "server": {
    "port": 3000,
    "nodeEnv": "development",
    "uptime": 45.2
  },
  "python": {
    "Python Version": {
      "available": true,
      "output": "Python 3.9.0 ..."
    },
    "NumPy": { ... },
    "PyTorch": { ... }
  }
}
```

### Available Models

```bash
GET /api/models/available

# Response
{
  "success": true,
  "models": [
    {
      "name": "instantmesh",
      "displayName": "InstantMesh",
      "description": "Fast 3D mesh generation from single image"
    },
    ...
  ]
}
```

---

## Troubleshooting

### "Python not found" Error

**Solution**: Ensure Python is in PATH or set `PYTHON_PATH` in `.env`

```bash
# Find Python path
which python    # macOS/Linux
where python    # Windows
```

### "Port 3000 already in use"

**Solution**: Change port in `.env` or kill process

```bash
# Windows
netstat -ano | findstr :3000
taskkill /PID <PID> /F

# macOS/Linux
lsof -i :3000
kill -9 <PID>
```

### GPU Not Detected

**Solution**: Verify CUDA installation

```bash
# Test GPU access
python -c "import torch; print(torch.cuda.is_available())"

# If False, reinstall PyTorch with CUDA support
```

### "CORS Error" in Browser

**Solution**: Already configured in Express, but check:
1. Frontend origin matches CORS allowed origins in `server.js`
2. Request uses correct API_BASE URL in `api.js`

---

## Next Steps

- **Phase 2**: Install xeokit SDK, implement viewer
- **Phase 3**: Setup AI model scripts, test generation
- **Phase 4**: Implement mesh processing pipeline
- **Phase 5**: Add object manipulation controls
- **Phase 6**: Implement IFC export

---

## Additional Resources

- xeokit Documentation: https://xeokit.io/
- Three.js Documentation: https://threejs.org/
- PyTorch Documentation: https://pytorch.org/
- IfcOpenShell: https://ifcopenshell.org/
- IFC Standard: https://www.buildingsmart.org/ifc/

---

## Support

For issues or questions, check:
1. Server logs (console output)
2. Browser developer console (F12)
3. `.env` configuration
4. Python environment setup
