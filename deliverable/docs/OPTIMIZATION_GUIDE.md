# Performance Optimization Guide - Phase 8

## Overview
This guide details optimization strategies and profiling tools for the 3D Picture to IFC Modeling pipeline.

## 1. Profiling Endpoints

### System Information
```bash
GET /api/debug/system
```
Returns: CPU cores, memory usage, system load, uptime

### Storage Status
```bash
GET /api/debug/storage
```
Returns: Files in directories, disk space available

### Request Statistics
```bash
GET /api/debug/stats
```
Returns: Total requests, errors, average load, requests by method/path

### Memory Usage
```bash
GET /api/debug/memory
```
Returns: Heap memory, RSS, external memory usage

### Full Health Check
```bash
GET /api/debug/health/full
```
Returns: System, Python, pipeline, and memory info

## 2. Optimization Strategies

### A. AI Inference Optimization

**GPU Memory Management:**
- Set `CUDA_VISIBLE_DEVICES=0` to use single GPU
- Monitor `GPU_MAX_MEMORY_MB` (default 8192)
- Consider model quantization for lower memory usage

**Model Loading:**
- Load models once and cache in memory
- Use model caching for repeated inference
- Consider async model loading

**Batch Processing:**
- Group multiple images for parallel processing
- Implement queue system for requests

### B. Mesh Processing Optimization

**Pipeline Efficiency:**
- Skip unnecessary processing steps if quality acceptable
- Use fast approximations during preview
- Full processing only for final export

**Memory Management:**
- Stream large mesh files instead of loading fully
- Delete intermediate files immediately after processing
- Implement temporary file cleanup

### C. Frontend Optimization

**Bundle Optimization:**
- Minify JavaScript/CSS
- Use CDN for xeokit library
- Lazy load modules as needed

**Viewer Performance:**
- Use LOD (Level of Detail) for large meshes
- Implement frustum culling
- Cache viewer state

**Network:**
- Compress file uploads
- Use WebSocket for real-time updates
- Implement progress tracking

## 3. Caching Strategies

### Model Cache
```javascript
// Cache AI models after first load
const modelCache = new Map();
modelCache.set('instantmesh', loadedModel);
```

### GLB Cache
```javascript
// Cache processed GLBs to avoid re-processing
const glbCache = new Map();
glbCache.set(hash(imagePath), glbPath);
```

### Scene State
```javascript
// Save/restore scene state for performance
sessionStorage.setItem('sceneState', JSON.stringify(objects));
```

## 4. Database Optimization (Future)

Instead of in-memory storage, use database:
- PostgreSQL for object metadata
- Redis for caching
- S3/MinIO for file storage

## 5. Monitoring & Alerts

### Performance Metrics
- Track inference time per model
- Monitor mesh processing duration
- Measure API response times

### Error Tracking
- Log all failures with context
- Track error frequency by type
- Alert on critical errors

## 6. Testing

### Unit Tests
```bash
npm test
```

### Performance Tests
```bash
npm run test:performance
```

### Load Testing
```bash
npm run test:load
```

## 7. Benchmarks

### Target Metrics
- InstantMesh: < 30 seconds
- StableFast3D: < 40 seconds
- TripoSR: < 60 seconds
- Mesh processing: < 10 seconds
- IFC export: < 5 seconds

### Current Performance (Placeholder)
- Average inference: 0.1s (placeholder)
- Average processing: 0.05s (placeholder)
- Average export: 0.02s (placeholder)

## 8. Scaling Considerations

### Horizontal Scaling
- Use load balancer (nginx, HAProxy)
- Multiple Node.js instances
- Shared file storage (S3, NFS)

### Vertical Scaling
- Increase server resources (CPU, RAM, GPU)
- Optimize memory usage
- Reduce processing overhead

### Microservices
- Separate AI inference service
- Separate mesh processing service
- Separate IFC export service

## 9. Production Deployment

### Environment Configuration
```env
NODE_ENV=production
LOG_LEVEL=warn
USE_GPU=true
GPU_MAX_MEMORY_MB=16384
MAX_FILE_SIZE=104857600  # 100MB
```

### Optimization Checklist
- [ ] Enable gzip compression
- [ ] Set proper cache headers
- [ ] Use production logging
- [ ] Configure monitoring
- [ ] Setup alerts
- [ ] Test load capacity
- [ ] Document performance baselines

## 10. Debug Tools

### Node.js Profiling
```bash
node --prof backend/server.js
node --prof-process isolate-*.log > processed.txt
```

### Memory Debugging
```bash
node --max-old-space-size=4096 backend/server.js
```

### Request Tracing
```bash
curl http://localhost:3000/api/debug/stats
```

## References
- [Node.js Performance Guide](https://nodejs.org/en/docs/guides/nodejs-performance/)
- [xeokit Optimization](https://www.docs.xeokit.io/)
- [WebGL Best Practices](https://www.khronos.org/webgl/wiki/Optimization)
