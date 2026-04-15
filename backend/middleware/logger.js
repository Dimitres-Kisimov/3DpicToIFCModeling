const config = require('../config/env');

const LOG_LEVELS = {
  error: 0,
  warn: 1,
  info: 2,
  debug: 3,
};

const currentLevel = LOG_LEVELS[config.LOG_LEVEL] || LOG_LEVELS.info;

function log(level, component, message, data = null) {
  const levelNum = LOG_LEVELS[level] || 0;
  if (levelNum > currentLevel) return; // Skip if below threshold

  const timestamp = new Date().toISOString();
  const prefix = `[${timestamp}] [${level.toUpperCase()}] [${component}]`;

  if (data) {
    console.log(`${prefix} ${message}`, data);
  } else {
    console.log(`${prefix} ${message}`);
  }
}

module.exports = {
  error: (component, message, data) => log('error', component, message, data),
  warn: (component, message, data) => log('warn', component, message, data),
  info: (component, message, data) => log('info', component, message, data),
  debug: (component, message, data) => log('debug', component, message, data),
};
