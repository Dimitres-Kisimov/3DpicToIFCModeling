require('dotenv').config();

module.exports = {
  // Server
  PORT: process.env.PORT || 3000,
  HOST: process.env.HOST || 'localhost',
  NODE_ENV: process.env.NODE_ENV || 'development',

  // Files
  MAX_FILE_SIZE: parseInt(process.env.MAX_FILE_SIZE) || 52428800, // 50MB default
  TEMP_DIR: process.env.TEMP_DIR || './temp',
  UPLOAD_DIR: process.env.UPLOAD_DIR || './uploads',
  OUTPUT_DIR: process.env.OUTPUT_DIR || './outputs',

  // Python
  PYTHON_PATH: process.env.PYTHON_PATH || 'python',
  PYTHON_SCRIPTS_DIR: process.env.PYTHON_SCRIPTS_DIR || './backend/python-scripts',

  // Room builder (merged from the retired Flask app)
  ROOM_OUT_DIR: process.env.ROOM_OUT_DIR || './demo/app_out',

  // GPU
  USE_GPU: process.env.USE_GPU === 'true',
  CUDA_VISIBLE_DEVICES: process.env.CUDA_VISIBLE_DEVICES || '0',
  GPU_MAX_MEMORY_MB: parseInt(process.env.GPU_MAX_MEMORY_MB) || 8192,

  // AI Models
  INSTANTMESH_MODEL_PATH: process.env.INSTANTMESH_MODEL_PATH || '',
  STABLEFAST3D_MODEL_PATH: process.env.STABLEFAST3D_MODEL_PATH || '',
  TRIPOSR_MODEL_PATH: process.env.TRIPOSR_MODEL_PATH || '',

  // IFC
  IFC_OUTPUT_DIR: process.env.IFC_OUTPUT_DIR || './outputs',

  // Logging
  LOG_LEVEL: process.env.LOG_LEVEL || 'info',
};
