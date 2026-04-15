const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');
const logger = require('../middleware/logger');
const config = require('../config/env');

/**
 * Execute Python script with arguments
 * @param {string} scriptName - Name of the Python script in python-scripts directory
 * @param {array} args - Command line arguments to pass to Python script
 * @param {object} options - Additional options (timeout, env, cwd)
 * @returns {Promise<object>} - { success, stdout, stderr, exitCode }
 */
function executePythonScript(scriptName, args = [], options = {}) {
  return new Promise((resolve, reject) => {
    const scriptPath = path.join(config.PYTHON_SCRIPTS_DIR, scriptName);

    if (!fs.existsSync(scriptPath)) {
      const error = new Error(`Python script not found: ${scriptPath}`);
      error.statusCode = 500;
      logger.error('PYTHON_BRIDGE', `Script not found: ${scriptName}`);
      reject(error);
      return;
    }

    logger.info('PYTHON_BRIDGE', `Executing: ${scriptName}`, { args });

    const pythonProcess = spawn(config.PYTHON_PATH, [scriptPath, ...args], {
      cwd: process.cwd(),
      env: {
        ...process.env,
        CUDA_VISIBLE_DEVICES: config.USE_GPU ? config.CUDA_VISIBLE_DEVICES : '',
        ...options.env,
      },
      timeout: options.timeout || 300000, // 5 min default
    });

    let stdout = '';
    let stderr = '';
    let timedOut = false;

    const timeout = setTimeout(() => {
      timedOut = true;
      pythonProcess.kill();
    }, options.timeout || 300000);

    pythonProcess.stdout.on('data', (data) => {
      stdout += data.toString();
      logger.debug('PYTHON_BRIDGE', `[${scriptName}] stdout:`, data.toString().trim());
    });

    pythonProcess.stderr.on('data', (data) => {
      stderr += data.toString();
      logger.warn('PYTHON_BRIDGE', `[${scriptName}] stderr:`, data.toString().trim());
    });

    pythonProcess.on('close', (code) => {
      clearTimeout(timeout);

      logger.info('PYTHON_BRIDGE', `Script finished: ${scriptName}`, { exitCode: code });

      if (timedOut) {
        const error = new Error(`Python script timed out: ${scriptName}`);
        error.statusCode = 504;
        error.code = 'TIMEOUT';
        reject(error);
        return;
      }

      try {
        // Try to parse stdout as JSON if code was 0
        let jsonOutput = null;
        if (code === 0 && stdout) {
          try {
            jsonOutput = JSON.parse(stdout);
          } catch (e) {
            // Not JSON, treat as plain text
          }
        }

        resolve({
          success: code === 0,
          exitCode: code,
          stdout: jsonOutput || stdout,
          stderr,
        });
      } catch (error) {
        reject(error);
      }
    });

    pythonProcess.on('error', (error) => {
      clearTimeout(timeout);
      logger.error('PYTHON_BRIDGE', `Process error: ${scriptName}`, error.message);
      reject(error);
    });
  });
}

/**
 * Execute Python command directly (for testing)
 * @param {string} command - Python code to execute
 * @returns {Promise<object>}
 */
function executePythonCommand(command, options = {}) {
  return new Promise((resolve, reject) => {
    logger.info('PYTHON_BRIDGE', 'Executing inline Python command');

    const pythonProcess = spawn(config.PYTHON_PATH, ['-c', command], {
      env: {
        ...process.env,
        CUDA_VISIBLE_DEVICES: config.USE_GPU ? config.CUDA_VISIBLE_DEVICES : '',
        ...options.env,
      },
      timeout: options.timeout || 30000,
    });

    let stdout = '';
    let stderr = '';

    const timeout = setTimeout(() => {
      pythonProcess.kill();
    }, options.timeout || 30000);

    pythonProcess.stdout.on('data', (data) => {
      stdout += data.toString();
    });

    pythonProcess.stderr.on('data', (data) => {
      stderr += data.toString();
    });

    pythonProcess.on('close', (code) => {
      clearTimeout(timeout);
      resolve({
        success: code === 0,
        exitCode: code,
        stdout,
        stderr,
      });
    });

    pythonProcess.on('error', (error) => {
      clearTimeout(timeout);
      reject(error);
    });
  });
}

/**
 * Test Python environment
 * @returns {Promise<object>} - Environment info
 */
async function testEnvironment() {
  try {
    logger.info('PYTHON_BRIDGE', 'Testing Python environment');

    const commands = [
      {
        name: 'Python Version',
        cmd: 'import sys; print(sys.version)',
      },
      {
        name: 'NumPy',
        cmd: 'import numpy; print(numpy.__version__)',
      },
      {
        name: 'PyTorch',
        cmd: 'import torch; print(torch.__version__); print("CUDA:", torch.cuda.is_available())',
      },
    ];

    const results = {};

    for (const { name, cmd } of commands) {
      try {
        const result = await executePythonCommand(cmd);
        results[name] = {
          available: result.success,
          output: result.stdout.trim(),
        };
      } catch (error) {
        results[name] = {
          available: false,
          error: error.message,
        };
      }
    }

    logger.info('PYTHON_BRIDGE', 'Environment test complete', results);
    return results;
  } catch (error) {
    logger.error('PYTHON_BRIDGE', 'Environment test failed', error.message);
    throw error;
  }
}

module.exports = {
  executePythonScript,
  executePythonCommand,
  testEnvironment,
};
