"""
Meshy API 3D generation - real single-image to 3D mesh via cloud API.
Sign up at meshy.ai, get a free API key, add MESHY_API_KEY to .env
"""

import sys
import os
import json
import base64
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from inference_base import log, error_exit, success_exit


def generate_with_meshy(image_path, output_path, api_key):
    import urllib.request
    import urllib.parse

    # Encode image as base64 data URL
    ext = Path(image_path).suffix.lower().lstrip(".")
    mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png"}.get(ext, "image/jpeg")
    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    image_data_url = f"data:{mime};base64,{b64}"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    def api_request(method, url, body=None):
        data = json.dumps(body).encode() if body else None
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())

    # Create image-to-3D task
    log("Sending image to Meshy API...", "info")
    result = api_request("POST", "https://api.meshy.ai/v2/image-to-3d", {
        "image_url": image_data_url,
        "enable_pbr": False,
        "ai_model": "meshy-4",
        "topology": "quad",
        "target_polycount": 30000,
    })
    task_id = result["result"]
    log(f"Task created: {task_id}", "info")

    # Poll until done (max 10 minutes)
    for attempt in range(120):
        time.sleep(5)
        status = api_request("GET", f"https://api.meshy.ai/v2/image-to-3d/{task_id}")
        state = status.get("status", "")
        progress = status.get("progress", 0)
        log(f"Status: {state} ({progress}%)", "info")

        if state == "SUCCEEDED":
            glb_url = status["model_urls"]["glb"]
            log(f"Downloading GLB...", "info")
            urllib.request.urlretrieve(glb_url, output_path)
            size = os.path.getsize(output_path)
            log(f"GLB saved: {size} bytes", "info")
            return size

        if state in ("FAILED", "EXPIRED"):
            msg = status.get("task_error", {}).get("message", "unknown error")
            raise RuntimeError(f"Meshy task failed: {msg}")

    raise RuntimeError("Meshy task timed out after 10 minutes")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        error_exit("Usage: run_meshy_api.py <input_image> <output_glb>")

    api_key = os.environ.get("MESHY_API_KEY", "")
    if not api_key:
        error_exit("MESHY_API_KEY not set in environment. Add it to your .env file.")

    if not os.path.exists(sys.argv[1]):
        error_exit(f"Input image not found: {sys.argv[1]}")

    try:
        size = generate_with_meshy(sys.argv[1], sys.argv[2], api_key)
        success_exit({
            "model": "meshy-api",
            "image_path": sys.argv[1],
            "output_path": sys.argv[2],
            "glb_size_bytes": size,
            "method": "meshy-cloud-api",
        })
    except Exception as e:
        error_exit(str(e))
