# API Documentation - Complete Reference

## Base URL
```
http://localhost:3000/api
```

## Authentication
Currently, no authentication required. In production, add JWT or API keys.

---

## Endpoints by Phase

### Phase 3: AI Model Generation

#### POST /generate
Generate 3D model from image using selected AI model.

**Request:**
```bash
POST /api/generate
Content-Type: multipart/form-data

image: <image_file>
model: instantmesh|stablefast3d|triposr
```

**Response (200):**
```json
{
  "success": true,
  "model": "instantmesh",
  "glb": "/outputs/instantmesh_timestamp.glb",
  "glbPath": "/path/to/outputs/instantmesh_timestamp.glb",
  "metadata": {
    "model": "instantmesh",
    "glbSize": 2048576,
    "vertices": 2048,
    "faces": 4096
  }
}
```

#### GET /models/available
List available AI models.

**Response (200):**
```json
{
  "success": true,
  "models": [
    {
      "name": "instantmesh",
      "displayName": "InstantMesh",
      "description": "Fast 3D mesh generation from single image"
    },
    {
      "name": "stablefast3d",
      "displayName": "StableFast3D",
      "description": "Stable and fast 3D model generation"
    },
    {
      "name": "triposr",
      "displayName": "TripoSR",
      "description": "High-quality 3D synthesis from images"
    }
  ]
}
```

#### GET /models/validate
Validate model availability and status.

**Response (200):**
```json
{
  "success": true,
  "models": [
    {"available": true, "model": "instantmesh", "status": "ready"},
    {"available": true, "model": "stablefast3d", "status": "ready"},
    {"available": true, "model": "triposr", "status": "ready", "quality": "high"}
  ],
  "allAvailable": true
}
```

---

### Phase 5: Object Management

#### GET /objects
List all objects in scene.

**Response (200):**
```json
{
  "success": true,
  "count": 2,
  "objects": [
    {
      "id": "obj_1234567890",
      "name": "InstantMesh Model",
      "glbUrl": "/outputs/model.glb",
      "position": [0, 0, 0],
      "rotation": [0, 0, 0],
      "scale": [1, 1, 1],
      "metadata": {},
      "createdAt": "2026-04-21T05:40:00.000Z"
    }
  ]
}
```

#### GET /objects/:id
Get specific object details.

**Response (200):**
```json
{
  "success": true,
  "object": { /* object data */ }
}
```

#### POST /objects
Create/add new object to scene.

**Request:**
```json
{
  "id": "obj_new",
  "name": "My Object",
  "glbUrl": "/outputs/model.glb",
  "position": [1, 2, 3],
  "rotation": [0, 90, 0],
  "scale": [1.5, 1.5, 1.5],
  "metadata": {"category": "furniture"}
}
```

**Response (201):**
```json
{
  "success": true,
  "object": { /* created object */ }
}
```

#### PUT /objects/:id
Update object transform.

**Request:**
```json
{
  "position": [2, 3, 4],
  "rotation": [45, 0, 0],
  "scale": [2, 2, 2]
}
```

**Response (200):**
```json
{
  "success": true,
  "object": { /* updated object */ }
}
```

#### DELETE /objects/:id
Remove object from scene.

**Response (200):**
```json
{
  "success": true,
  "message": "Object deleted: obj_id"
}
```

#### POST /objects/batch/update
Update multiple objects at once.

**Request:**
```json
{
  "updates": [
    {"id": "obj_1", "position": [1, 0, 0]},
    {"id": "obj_2", "position": [2, 0, 0]}
  ]
}
```

**Response (200):**
```json
{
  "success": true,
  "updated": 2,
  "failed": 0,
  "results": [...]
}
```

#### POST /objects/batch/clear
Clear all objects from scene.

**Response (200):**
```json
{
  "success": true,
  "message": "Cleared 5 objects",
  "count": 5
}
```

---

### Phase 6: IFC Export

#### GET /export/formats
List available export formats.

**Response (200):**
```json
{
  "success": true,
  "formats": [
    {
      "format": "ifc2x3",
      "name": "IFC 2x3",
      "description": "Industry Foundation Classes 2x3"
    },
    {
      "format": "ifc4",
      "name": "IFC 4",
      "description": "Industry Foundation Classes 4.0"
    }
  ]
}
```

#### POST /export/ifc
Export scene to IFC format.

**Request:**
```json
{
  "objects": [
    {
      "id": "obj_1",
      "name": "Furniture 1",
      "glbPath": "/outputs/model.glb",
      "position": [0, 0, 0],
      "rotation": [0, 0, 0],
      "scale": [1, 1, 1]
    }
  ],
  "format": "ifc2x3"
}
```

**Response (200):**
```json
{
  "success": true,
  "format": "ifc2x3",
  "ifcUrl": "/outputs/scene_1234567890.ifc",
  "ifcPath": "/path/to/outputs/scene.ifc",
  "metadata": {
    "ifcSize": 4096,
    "objectCount": 1
  }
}
```

#### POST /export/glb-to-ifc
Convert single GLB to IFC furniture.

**Request:**
```json
{
  "glbPath": "/outputs/model.glb",
  "objectInfo": {
    "name": "Generated Furniture",
    "position": [0, 0, 0],
    "rotation": [0, 0, 0]
  }
}
```

**Response (200):**
```json
{
  "success": true,
  "ifcUrl": "/outputs/furniture.ifc",
  "metadata": { /* IFC metadata */ }
}
```

#### GET /export/list
List recent IFC exports.

**Response (200):**
```json
{
  "success": true,
  "count": 5,
  "exports": [
    {
      "filename": "scene_1234567890.ifc",
      "url": "/outputs/scene_1234567890.ifc",
      "size": 4096,
      "created": "2026-04-21T05:45:00.000Z",
      "modified": "2026-04-21T05:45:00.000Z"
    }
  ]
}
```

---

### Phase 7: Full Pipeline

#### GET /pipeline/info
Get pipeline information and capabilities.

**Response (200):**
```json
{
  "success": true,
  "pipeline": {
    "name": "3D Picture to IFC Modeling Pipeline",
    "version": "1.0.0",
    "phases": [
      {
        "name": "AI Generation",
        "models": ["instantmesh", "stablefast3d", "triposr"]
      },
      {
        "name": "Mesh Processing",
        "operations": ["clean", "normalize", "orient", "convert_to_glb"]
      },
      {
        "name": "IFC Export",
        "formats": ["ifc2x3", "ifc4"]
      }
    ],
    "status": "operational"
  }
}
```

#### POST /pipeline/run
Execute complete pipeline: Image → GLB → Process → IFC

**Request:**
```bash
POST /api/pipeline/run
Content-Type: multipart/form-data

image: <image_file>
model: instantmesh
processMesh: true
exportIFC: true
objectName: Generated Object
position: [0,0,0]
rotation: [0,0,0]
```

**Response (200):**
```json
{
  "success": true,
  "model": "instantmesh",
  "duration_ms": 15234,
  "steps": {
    "ai_generation": {
      "status": "complete",
      "glbUrl": "/outputs/model.glb",
      "glbSize": 2048576
    },
    "mesh_processing": {
      "status": "complete",
      "processed": true
    },
    "ifc_export": {
      "status": "complete",
      "ifcUrl": "/outputs/scene.ifc",
      "ifcSize": 4096
    }
  },
  "output": {
    "glbUrl": "/outputs/model.glb",
    "ifcUrl": "/outputs/scene.ifc"
  }
}
```

---

### Phase 8: Diagnostics & Profiling

#### GET /debug/system
System information and resource usage.

#### GET /debug/storage
Storage status and file counts.

#### GET /debug/stats
Request statistics and performance metrics.

#### GET /debug/memory
Memory usage breakdown.

#### GET /debug/config
Configuration summary (safe values only).

#### GET /debug/health/full
Comprehensive health check with all details.

---

## Common Status Codes

| Code | Meaning |
|------|---------|
| 200 | OK - Request successful |
| 201 | Created - Resource created |
| 400 | Bad Request - Invalid input |
| 404 | Not Found - Resource not found |
| 409 | Conflict - Resource already exists |
| 500 | Internal Server Error |
| 501 | Not Implemented - Feature not ready |
| 503 | Service Unavailable |
| 504 | Timeout - Operation took too long |

---

## Error Response Format

```json
{
  "success": false,
  "error": {
    "code": "ERROR_CODE",
    "message": "Human readable error message"
  }
}
```

---

## Rate Limiting

Currently disabled. In production, implement:
```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 99
X-RateLimit-Reset: 1234567890
```

---

## Webhooks (Future)

Configure webhooks for:
- `generation.complete`
- `export.complete`
- `processing.complete`
- `error.occurred`

---

## Pagination (Future)

```
GET /api/objects?page=1&limit=20&sort=-createdAt
```

---

## Filtering (Future)

```
GET /api/objects?model=instantmesh&status=processed
```
