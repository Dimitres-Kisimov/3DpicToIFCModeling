"""
detect_worker.py — persistent warm-model worker for the "Fast — from catalog" path.

Holds DETR + Depth-Anything + DINOv2 (+ the FAISS index) in memory so catalog
recall costs seconds, not the ~20 s of per-request model loading. Runs on CPU
(the parent sets CUDA_VISIBLE_DEVICES='') so it never competes with TripoSR for
the 6 GB GPU.

Protocol: one JSON object per stdin line ->
    {"id": 7, "image": "<path>", "out": "<path.glb>"}
one JSON object per stdout line <-
    {"id": 7, "result": {...run_detect_and_place result...}}
    {"id": 7, "error": "...", "trace": "..."}
Model/library noise on stdout is tolerated by the Node reader (it only accepts
lines that parse as JSON with a matching "id"). Logs go to stderr.
"""
from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import run_detect_and_place as rdp   # noqa: E402  (SCS_WARM_MODELS=1 in our env)


def main():
    print(json.dumps({"ready": True}), flush=True)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        rid = None
        try:
            req = json.loads(line)
            rid = req.get("id")
            if req.get("cmd") == "ping":
                print(json.dumps({"id": rid, "pong": True}), flush=True)
                continue
            result = rdp.run(req["image"], req["out"])
            print(json.dumps({"id": rid, "result": result}), flush=True)
        except SystemExit:
            # a pipeline stage called error_exit(); stay alive for the next request
            print(json.dumps({"id": rid, "error": "pipeline stage exited"}), flush=True)
        except Exception as exc:
            print(json.dumps({"id": rid, "error": str(exc),
                              "trace": traceback.format_exc()[-2000:]}), flush=True)


if __name__ == "__main__":
    main()
