"""
Sprint 4 — YOLO fine-tuning script for office object segmentation.

Training data structure expected:
  datasets/office_objects/
    images/train/*.jpg
    images/val/*.jpg
    labels/train/*.txt   (YOLO seg format)
    labels/val/*.txt

Classes (24 office furniture categories):
  0: chair, 1: desk, 2: conference_table, 3: sofa, 4: bookshelf,
  5: filing_cabinet, 6: monitor, 7: laptop, 8: keyboard, 9: mouse,
  10: printer, 11: whiteboard, 12: projector, 13: lamp, 14: plant,
  15: trash_bin, 16: coat_rack, 17: cabinet, 18: drawer, 19: partition,
  20: telephone, 21: coffee_machine, 22: water_dispenser, 23: safe

Run training:
  python finetune_yolo_office.py --data datasets/office_objects --epochs 100
"""

import sys
import argparse
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from inference_base import log, error_exit, success_exit

OFFICE_CLASSES = [
    "chair", "desk", "conference_table", "sofa", "bookshelf",
    "filing_cabinet", "monitor", "laptop", "keyboard", "mouse",
    "printer", "whiteboard", "projector", "lamp", "plant",
    "trash_bin", "coat_rack", "cabinet", "drawer", "partition",
    "telephone", "coffee_machine", "water_dispenser", "safe",
]

MODELS_DIR = Path(__file__).parent.parent.parent / "models" / "yolo"


def write_data_yaml(data_dir, yaml_path):
    """Write YOLO dataset YAML config."""
    data_dir = Path(data_dir).resolve()
    content = f"""path: {data_dir}
train: images/train
val: images/val

nc: {len(OFFICE_CLASSES)}
names: {OFFICE_CLASSES}
"""
    with open(yaml_path, "w") as f:
        f.write(content)
    log(f"Dataset config written: {yaml_path}", "info")


def run_training(data_dir, epochs=100, imgsz=640, batch=16, device="auto"):
    from ultralytics import YOLO

    yaml_path = Path(data_dir) / "office_objects.yaml"
    write_data_yaml(data_dir, str(yaml_path))

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    output_dir = MODELS_DIR / "training_run"

    log(f"Starting YOLO fine-tune: {epochs} epochs, imgsz={imgsz}", "info")

    model = YOLO("yolov8n-seg.pt")
    results = model.train(
        data=str(yaml_path),
        epochs=epochs,
        imgsz=imgsz,
        batch=batch,
        device=device,
        project=str(output_dir),
        name="office_seg",
        exist_ok=True,
    )

    best_weights = output_dir / "office_seg" / "weights" / "best.pt"
    dest_weights = MODELS_DIR / "office_seg.pt"

    if best_weights.exists():
        import shutil
        shutil.copy(best_weights, dest_weights)
        log(f"Best weights copied to: {dest_weights}", "info")

    return {
        "epochs_trained": epochs,
        "best_weights": str(dest_weights) if dest_weights.exists() else str(best_weights),
        "classes": len(OFFICE_CLASSES),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fine-tune YOLO for office objects")
    parser.add_argument("--data", required=True, help="Path to dataset directory")
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=16)
    parser.add_argument("--device", default="auto")
    args = parser.parse_args()

    if not Path(args.data).exists():
        error_exit(f"Dataset directory not found: {args.data}")

    result = run_training(args.data, args.epochs, args.imgsz, args.batch, args.device)
    success_exit(result)
