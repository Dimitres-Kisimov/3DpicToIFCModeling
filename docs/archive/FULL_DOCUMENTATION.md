# 3D Picture to IFC Modeling - Full Project Documentation

## Overview
This project converts 2D images into 3D models and exports them as IFC files, following a modular, multi-phase pipeline. It uses Node.js (Express) for the backend, Python for AI/model processing, and a modern JavaScript frontend with xeokit for 3D visualization.

---

## Table of Contents
1. Project Phases & Status
2. File Structure
3. Key Components & Files
4. API Endpoints
5. Setup & Installation
6. Optimization & Testing
7. Next Steps
8. Troubleshooting & Support

---

## 1. Project Phases & Status

| Phase | Name                   | Status      |
|-------|------------------------|-------------|
| 1     | Structure & Backend    | Complete    |
| 2     | xeokit Integration     | Ready       |
| 3     | AI Model Integration   | Planned     |
| 4     | Mesh Processing        | Planned     |
| 5     | Object Manipulation    | Planned     |
| 6     | IFC Export             | Planned     |
| 7     | Integration & Utils    | Planned     |
| 8     | Testing & Optimization | Planned     |

---

## 2. File Structure (Key Folders & Files)

```
3DpicToIFCModeling/
├── backend/
│   ├── server.js
│   ├── config/env.js
│   ├── middleware/logger.js, errorHandler.js
│   ├── services/
│   │   ├── pythonBridge.js
│   │   ├── aiRouter.js
│   │   ├── meshProcessor.js
│   │   ├── ifcExporter.js
│   │   └── pipeline.js
│   ├── ai/instantMesh.js, stablefast3d.js, triposr.js
│   ├── routes/apiRoutes.js, objectRoutes.js, exportRoutes.js, debugRoutes.js, pipelineRoutes.js
│   └── python-scripts/
│       ├── run_instantmesh.py, run_stablefast3d.py, run_triposr.py
│       ├── cleanMesh.py, normalizeMesh.py, fixOrientation.py, meshToGLB.py
│       ├── createIFCFurniture.py, saveIFC.py
│       └── inference_base.py, __init__.py
├── frontend/
│   ├── index.html
│   ├── css/style.css
│   └── js/api.js, exporter.js, glbLoader.js, index.js, inventory.js, transformControls.js, xeokitViewer.js
├── docs/SETUP_GUIDE.md, API_REFERENCE.md, OPTIMIZATION_GUIDE.md
├── temp/, uploads/, outputs/
├── package.json, requirements.txt, .env, .env.example
├── WORK_CHECKPOINT.md, INSTALLATION_COMPLETE.md, README.md
```

---

## 3. Key Components & Files

### Backend
- **server.js**: Express server entry point
- **pythonBridge.js**: Node.js ↔ Python subprocess bridge
- **aiRouter.js, meshProcessor.js, ifcExporter.js, pipeline.js**: Modular services for each pipeline phase
- **ai/**: Adapters for each AI model
- **python-scripts/**: Python scripts for AI inference, mesh processing, and IFC export
- **routes/**: REST API endpoints for each feature

### Frontend
- **index.html**: Main UI
- **js/**: Modular scripts for API, 3D viewer (xeokit), GLB loading, inventory, transforms, and export
- **css/style.css**: Responsive, BIM-inspired styling

### Docs
- **SETUP_GUIDE.md**: Installation and environment setup
- **API_REFERENCE.md**: Full API documentation
- **OPTIMIZATION_GUIDE.md**: Performance and profiling tips
- **WORK_CHECKPOINT.md**: Work summary and phase tracking

---

## 4. API Endpoints (Summary)

- **GET /api/health**: Server health check
- **GET /api/debug/health**: Python environment info
- **GET /api/models/available**: List available AI models
- **POST /api/generate**: Generate 3D model from image (planned)
- **GET /api/objects**: List scene objects (planned)
- **PUT /api/objects/:id**: Update object transform (planned)
- **POST /api/export/ifc**: Export scene to IFC (planned)
- **GET /api/debug/system, /storage, /stats, /memory, /health/full**: Diagnostics & profiling

See docs/API_REFERENCE.md for full details and request/response examples.

---

## 5. Setup & Installation

### Prerequisites
- Node.js 18+
- Python 3.9+
- Git
- (Optional) NVIDIA GPU with CUDA

### Steps
1. Clone repo: `git clone ...`
2. Install Node.js deps: `npm install`
3. Setup Python env (conda or venv) and install requirements
4. Configure `.env` file
5. Start server: `npm start`
6. Open http://localhost:3000

See docs/SETUP_GUIDE.md for full instructions and troubleshooting.

---

## 6. Optimization & Testing
- Profiling endpoints for system, storage, stats, memory, health
- AI/model, mesh, and frontend optimization strategies
- Caching for models, GLBs, and scene state
- Testing: `npm test`, `npm run test:performance`, `npm run test:load`
- Benchmarks and scaling tips

See docs/OPTIMIZATION_GUIDE.md for details.

---

## 7. Next Steps
- Phase 2: Integrate xeokit viewer and GLB loader
- Phase 3: Implement AI model adapters and connect to backend
- Phase 4: Mesh processing pipeline
- Phase 5: Object manipulation (transform controls, inventory)
- Phase 6: IFC export logic
- Phase 7: Pipeline integration and utilities
- Phase 8: Testing, optimization, and deployment

---

## 8. Troubleshooting & Support
- See WORK_CHECKPOINT.md and SETUP_GUIDE.md for common issues and solutions
- Check server logs and browser console for errors
- Verify Python and Node.js environments
- For CORS, GPU, or port issues, see troubleshooting section in SETUP_GUIDE.md

---

## Export Notes
This documentation summarizes the current state of the project as of April 21, 2026. For the most up-to-date details, refer to the checkpoint and guide files in the docs/ folder.
