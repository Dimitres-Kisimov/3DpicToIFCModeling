# 3D Picture to IFC Modeling

AI-powered system that converts 2D images into 3D models and exports them to IFC format for architectural workflows.

## Quick Start

### Installation

```bash
# Install Node.js dependencies
npm install

# Setup Python environment (see SETUP_GUIDE.md)
conda create -n 3d-ifc python=3.9
conda activate 3d-ifc
pip install -r requirements.txt
```

### Run Application

```bash
# Copy environment config
cp .env.example .env

# Start server
npm start

# Visit http://localhost:3000
```

## Features

✨ **Multi-AI Model Support**
- InstantMesh - Fast mesh generation
- StableFast3D - Stable & fast 3D synthesis
- TripoSR - High-quality 3D from images

🎨 **xeokit Integration**
- Real-time 3D visualization
- Interactive object manipulation
- Multi-object scene management

📐 **IFC Export**
- Export scenes to Industry Foundation Classes (IFC)
- Preserve geometry, transforms, and object properties
- Compatible with Revit, AutoCAD, BIM software

🔧 **GPU-Accelerated Processing**
- Local NVIDIA GPU inference (CUDA)
- Mesh cleaning & normalization pipeline
- Real-time rendering

## Architecture

```
Image → AI Model → GLB Pipeline → xeokit Scene → IFC Export
```

### Stack
- **Backend**: Node.js/Express
- **Frontend**: Vanilla JS + xeokit SDK
- **AI Inference**: Python subprocess with GPU support
- **Mesh Processing**: Open3D, Three.js
- **IFC Export**: IfcOpenShell

## Project Structure

```
3DpicToIFCModeling/
├── backend/           # Express server + Python bridge
├── frontend/          # UI + xeokit viewer
├── docs/              # Documentation
├── package.json       # Node.js dependencies
├── requirements.txt   # Python dependencies
└── README.md
```

## Documentation

- [Setup Guide](./docs/SETUP_GUIDE.md) - Detailed installation & configuration
- [Implementation Plan](./docs/IMPLEMENTATION_PLAN.md) - Phase-by-phase roadmap
- [API Reference](./docs/API_REFERENCE.md) - Endpoint documentation

## Development Phases

**Phase 1**: Project structure & backend foundation ✅  
**Phase 2**: xeokit integration & frontend scaffolding  
**Phase 3**: AI model integration  
**Phase 4**: Mesh processing pipeline  
**Phase 5**: Object manipulation & transforms  
**Phase 6**: IFC export system  
**Phase 7**: Integration, utilities & polish  
**Phase 8**: Testing, optimization & deployment  

## Technology

- [xeokit](https://xeokit.io/) - 3D BIM visualization
- [Three.js](https://threejs.org/) - 3D graphics
- [Open3D](http://www.open3d.org/) - 3D data processing
- [PyTorch](https://pytorch.org/) - Deep learning
- [IfcOpenShell](https://ifcopenshell.org/) - IFC manipulation

## License

MIT

## Support

For setup issues, see [SETUP_GUIDE.md](./docs/SETUP_GUIDE.md)  
For development progress, see implementation plan in `/memories/session/plan.md`