"""
Sprint 4 — Office Object Detection & Classification
Pipeline:
  1. YOLOv8 detects and segments the dominant object
  2. Classifier maps YOLO class → IFC object type + material category
  3. Returns structured metadata for IFC export (type, material, ifc_class)

Fine-tuning path (when labeled office data is ready):
  yolo train data=office_objects.yaml model=yolov8n-seg.pt epochs=100 imgsz=640
  Export: yolo export model=runs/segment/train/weights/best.pt format=onnx

Usage: python classify_object.py <input_image>
"""

import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from inference_base import log, error_exit, success_exit

MODELS_DIR      = Path(__file__).parent.parent.parent / "models"
CUSTOM_YOLO_PT  = MODELS_DIR / "yolo" / "office_seg.pt"  # custom fine-tuned weights
BASE_YOLO_PT    = "yolov8n-seg.pt"                        # pretrained fallback


# ─── IFC class + material taxonomy ───────────────────────────────────────────
# Maps YOLO COCO class names → IFC type, material category, BIM properties

OBJECT_TAXONOMY = {
    "chair": {
        "ifc_class": "IfcFurnishingElement",
        "ifc_type": "IfcChair",
        "material_category": "textile_soft",
        "bim_properties": {"LoadBearing": False, "IsExternal": False, "Occupancy": "seating"},
    },
    "couch": {
        "ifc_class": "IfcFurnishingElement",
        "ifc_type": "IfcSofa",
        "material_category": "textile_soft",
        "bim_properties": {"LoadBearing": False, "IsExternal": False, "Occupancy": "seating"},
    },
    "dining table": {
        "ifc_class": "IfcFurnishingElement",
        "ifc_type": "IfcTable",
        "material_category": "wood_polished",
        "bim_properties": {"LoadBearing": False, "IsExternal": False},
    },
    "desk": {
        "ifc_class": "IfcFurnishingElement",
        "ifc_type": "IfcTable",
        "material_category": "wood_polished",
        "bim_properties": {"LoadBearing": False, "IsExternal": False, "Occupancy": "work"},
    },
    "laptop": {
        "ifc_class": "IfcFurnishingElement",
        "ifc_type": "IfcElectricAppliance",
        "material_category": "metal_brushed",
        "bim_properties": {"LoadBearing": False, "IsExternal": False},
    },
    "tv": {
        "ifc_class": "IfcFurnishingElement",
        "ifc_type": "IfcElectricAppliance",
        "material_category": "metal_matte",
        "bim_properties": {"LoadBearing": False, "IsExternal": False},
    },
    "refrigerator": {
        "ifc_class": "IfcFurnishingElement",
        "ifc_type": "IfcKitchenDevice",
        "material_category": "metal_polished",
        "bim_properties": {"LoadBearing": False, "IsExternal": False},
    },
    "book": {
        "ifc_class": "IfcFurnishingElement",
        "ifc_type": "IfcFurnishingElement",
        "material_category": "paper",
        "bim_properties": {},
    },
    "potted plant": {
        "ifc_class": "IfcFurnishingElement",
        "ifc_type": "IfcPlant",
        "material_category": "organic",
        "bim_properties": {},
    },
    "bed": {
        "ifc_class": "IfcFurnishingElement",
        "ifc_type": "IfcBed",
        "material_category": "textile_soft",
        "bim_properties": {"LoadBearing": False},
    },
}

DEFAULT_CLASSIFICATION = {
    "ifc_class": "IfcFurnishingElement",
    "ifc_type": "IfcFurnishingElement",
    "material_category": "unknown",
    "bim_properties": {},
}


def _detect_and_classify(image_path):
    """Run YOLO on image and return best detection with classification."""
    from ultralytics import YOLO
    import numpy as np

    # Load custom weights if available, else pretrained
    model_path = str(CUSTOM_YOLO_PT) if CUSTOM_YOLO_PT.exists() else BASE_YOLO_PT
    log(f"Loading YOLO from: {model_path}", "info")
    model = YOLO(model_path)

    results = model(image_path, verbose=False)
    detections = []

    if results[0].boxes is not None and len(results[0].boxes) > 0:
        boxes  = results[0].boxes
        confs  = boxes.conf.cpu().numpy()
        cls_ids = boxes.cls.cpu().numpy().astype(int)
        names  = results[0].names

        for i, (conf, cls_id) in enumerate(zip(confs, cls_ids)):
            class_name = names[cls_id].lower()
            taxonomy = OBJECT_TAXONOMY.get(class_name, DEFAULT_CLASSIFICATION)
            detections.append({
                "class_name": class_name,
                "confidence": float(conf),
                **taxonomy,
            })

        # Sort by confidence descending
        detections.sort(key=lambda d: d["confidence"], reverse=True)
        log(f"Detected {len(detections)} objects, best: {detections[0]['class_name']} ({detections[0]['confidence']:.2f})", "info")
    else:
        log("No objects detected", "warn")

    return detections


def classify_object(image_path):
    if not os.path.exists(image_path):
        error_exit(f"Image not found: {image_path}")

    try:
        detections = _detect_and_classify(image_path)

        primary = detections[0] if detections else {
            "class_name": "unknown",
            "confidence": 0.0,
            **DEFAULT_CLASSIFICATION,
        }

        return {
            "primary": primary,
            "all_detections": detections,
            "custom_model_used": CUSTOM_YOLO_PT.exists(),
            "model_path": str(CUSTOM_YOLO_PT) if CUSTOM_YOLO_PT.exists() else BASE_YOLO_PT,
        }

    except Exception as e:
        import traceback
        log(traceback.format_exc(), "error")
        error_exit(f"Classification failed: {str(e)}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        error_exit("Usage: classify_object.py <input_image>")
    result = classify_object(sys.argv[1])
    success_exit(result)
