"""
Inference base module - shared utilities for AI models
Phase 1: Placeholder for image loading, error handling
"""

import json
import sys
import traceback
from pathlib import Path


def log(message, level="info"):
    """Log message to stderr for Node.js to capture"""
    print(f"[{level.upper()}] {message}", file=sys.stderr)


def error_exit(message, code=1):
    """Print error as JSON and exit"""
    error_obj = {
        "success": False,
        "error": {"message": message},
    }
    print(json.dumps(error_obj))
    sys.exit(code)


def success_exit(data):
    """Print success result as JSON and exit"""
    result = {
        "success": True,
        "data": data,
    }
    print(json.dumps(result))
    sys.exit(0)


def load_image(image_path):
    """Load image from file path"""
    try:
        from PIL import Image
        img = Image.open(image_path)
        return img
    except ImportError:
        error_exit("Pillow library required for image loading")
    except Exception as e:
        error_exit(f"Failed to load image: {str(e)}")


if __name__ == "__main__":
    log("This is a shared module for Python scripts")
