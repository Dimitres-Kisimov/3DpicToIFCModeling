const logger = require('./logger');

// Express error handling middleware
function errorHandler(err, req, res, next) {
  logger.error('ERROR_HANDLER', err.message, {
    stack: err.stack,
    path: req.path,
    method: req.method,
  });

  const statusCode = err.statusCode || 500;
  const message = err.message || 'Internal Server Error';

  res.status(statusCode).json({
    success: false,
    error: {
      code: err.code || 'ERROR',
      message: message,
      ...(process.env.NODE_ENV === 'development' && { stack: err.stack }),
    },
  });
}

module.exports = errorHandler;
