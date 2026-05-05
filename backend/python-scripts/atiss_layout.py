"""
Sprint 6 — ATISS (Autoregressive Transformers for Indoor Scene Synthesis)
Paper: https://arxiv.org/abs/2110.03937
License: MIT

ATISS generates plausible indoor scene layouts by learning from 3D-FRONT dataset.
This module:
  1. Provides an ATISS inference wrapper (if weights are present)
  2. Falls back to the OR-Tools CP-SAT solver (Sprint 5)
  3. Includes a fine-tuning entry point for office layout datasets

Setup:
  git clone https://github.com/nv-tlabs/ATISS models/atiss/src
  pip install -r models/atiss/src/requirements.txt
  Download weights: models/atiss/office_scene.pth  (fine-tuned)
               or: models/atiss/threedfront.pth   (pretrained)

Fine-tuning data format: 3D-FRONT JSON scene format
  See: https://tianchi.aliyun.com/specials/promotion/alibaba-3d-scene-dataset
"""

import sys
import json
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from inference_base import log, error_exit, success_exit

MODELS_DIR   = Path(__file__).parent.parent.parent / "models"
ATISS_DIR    = MODELS_DIR / "atiss"
ATISS_SRC    = ATISS_DIR / "src"
ATISS_CKPT   = ATISS_DIR / "office_scene.pth"
ATISS_CKPT_PRETRAIN = ATISS_DIR / "threedfront.pth"


def _run_atiss_inference(room, object_categories):
    """
    Run ATISS autoregressive scene generation.
    Returns list of {category, position, size, rotation} placements.
    """
    import torch

    if ATISS_SRC.exists():
        sys.path.insert(0, str(ATISS_SRC))

    ckpt = ATISS_CKPT if ATISS_CKPT.exists() else ATISS_CKPT_PRETRAIN
    if not ckpt.exists():
        raise FileNotFoundError(
            f"ATISS weights not found at {ATISS_DIR}.\n"
            "Steps:\n"
            "  1. git clone https://github.com/nv-tlabs/ATISS models/atiss/src\n"
            "  2. Download pretrained weights to models/atiss/threedfront.pth\n"
            "  3. Fine-tune on office data: python atiss_layout.py --finetune <data>"
        )

    log(f"Loading ATISS from {ckpt.name}...", "info")
    from scene_synthesis.networks import build_network

    device = "cuda" if torch.cuda.is_available() else "cpu"
    config_path = ATISS_SRC / "config" / "bedrooms_config.yaml"
    model, _ = build_network(str(config_path), ckpt, device)
    model.eval()

    log("Generating scene layout with ATISS...", "info")
    with torch.no_grad():
        boxes = model.generate_boxes(
            room_mask=None,
            max_boxes=len(object_categories) + 2,
        )

    placements = []
    for i, box in enumerate(boxes):
        cat = object_categories[i] if i < len(object_categories) else "furniture"
        placements.append({
            "id": f"{cat}_{i}",
            "category": cat,
            "position": [float(box.translation[0]), 0.0, float(box.translation[2])],
            "size":     [float(box.size[0]), float(box.size[1]), float(box.size[2])],
            "rotation": [0, float(box.angle), 0],
            "placed":   True,
            "source":   "atiss",
        })
        log(f"ATISS placed: {cat} at ({box.translation[0]:.2f}, {box.translation[2]:.2f})", "info")

    return placements


def generate_layout(room, object_categories):
    """
    Main entry point. Tries ATISS, falls back to OR-Tools spatial_layout.
    """
    log(f"Room: {room['width']}m × {room['depth']}m, categories: {object_categories}", "info")

    try:
        placements = _run_atiss_inference(room, object_categories)
        return {
            "room": room,
            "placements": placements,
            "solver": "atiss",
            "object_count": len(placements),
        }
    except FileNotFoundError as e:
        log(str(e), "warn")
        log("Falling back to OR-Tools spatial_layout...", "warn")
    except Exception as e:
        log(f"ATISS failed: {e} — falling back to OR-Tools", "warn")

    # Fallback: build objects list from categories and call OR-Tools
    from spatial_layout import layout_room
    objects = [
        {
            "id": f"{cat}_{i}",
            "category": cat,
            "width":  0.6 if "chair" in cat else 1.2,
            "depth":  0.6 if "chair" in cat else 0.8,
        }
        for i, cat in enumerate(object_categories)
    ]
    result = layout_room(room, objects)
    result["solver"] = "ortools-fallback"
    return result


def finetune(data_dir, epochs=50, batch_size=4):
    """
    Fine-tune ATISS on office layout data.
    data_dir should contain 3D-FRONT format JSON scene files.
    """
    if ATISS_SRC.exists():
        sys.path.insert(0, str(ATISS_SRC))

    try:
        from train import train_model
    except ImportError:
        error_exit("ATISS training script not found. Clone the repo to models/atiss/src/")

    log(f"Starting ATISS fine-tune: {epochs} epochs, batch={batch_size}", "info")
    train_model(
        data_dir=data_dir,
        output_dir=str(ATISS_DIR),
        epochs=epochs,
        batch_size=batch_size,
        base_checkpoint=str(ATISS_CKPT_PRETRAIN) if ATISS_CKPT_PRETRAIN.exists() else None,
    )
    return {"status": "complete", "output_checkpoint": str(ATISS_CKPT)}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="ATISS layout synthesis")
    parser.add_argument("--finetune", help="Fine-tune on this data directory")
    parser.add_argument("--room", help="JSON room spec")
    parser.add_argument("--categories", help="JSON array of object categories")
    parser.add_argument("--epochs", type=int, default=50)
    args = parser.parse_args()

    if args.finetune:
        result = finetune(args.finetune, args.epochs)
        success_exit(result)
    elif args.room and args.categories:
        room = json.loads(args.room)
        cats = json.loads(args.categories)
        result = generate_layout(room, cats)
        success_exit(result)
    else:
        error_exit("Usage: atiss_layout.py --room <json> --categories <json>\n"
                   "   or: atiss_layout.py --finetune <data_dir>")
