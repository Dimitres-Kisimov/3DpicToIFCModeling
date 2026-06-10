"""
Side-by-side benchmark of 10 commercial-safe HuggingFace models on an office photo.

Tested on: RTX 4070 Laptop (8 GB VRAM), Python 3.13, PyTorch 2.12 cu126.

Models run sequentially; each is freed before the next loads, so all 10 fit
within 8 GB VRAM individually.

Output:
  outputs/detection_benchmark.csv          per-model metrics
  outputs/detection_overlays/<model>.jpg   annotated detection overlay (where applicable)

Usage:
  python scripts/test_furniture_detection.py --image path/to/photo.jpg
  python scripts/test_furniture_detection.py --image office.jpg --models grounding_dino owlv2
"""
from __future__ import annotations

import argparse
import csv
import gc
import time
from pathlib import Path

import torch
from PIL import Image, ImageDraw, ImageFont

SCS_CATEGORIES = [
    "office chair", "desk", "monitor", "cabinet", "bookshelf",
    "lamp", "desk lamp", "keyboard", "mouse", "table", "filing cabinet",
]
GROUNDING_DINO_PROMPT = " . ".join(SCS_CATEGORIES) + " ."


def device() -> str:
    return "cuda" if torch.cuda.is_available() else "cpu"


def vram_mb() -> int:
    if torch.cuda.is_available():
        return int(torch.cuda.max_memory_allocated() / (1024 * 1024))
    return 0


def reset_vram_peak() -> None:
    if torch.cuda.is_available():
        torch.cuda.reset_peak_memory_stats()


def free_model(*objs) -> None:
    for o in objs:
        del o
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


def draw_boxes(image: Image.Image, boxes, labels, scores, out: Path) -> None:
    img = image.copy()
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", 16)
    except Exception:
        font = ImageFont.load_default()
    for box, label, score in zip(boxes, labels, scores):
        x0, y0, x1, y1 = [int(v) for v in box]
        draw.rectangle([x0, y0, x1, y1], outline="red", width=3)
        draw.text((x0 + 4, y0 + 4), f"{label} {score:.2f}", fill="red", font=font)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, quality=85)


# -------- model adapters ------------------------------------------------------


def run_detr(image, model_id):
    from transformers import DetrImageProcessor, DetrForObjectDetection
    processor = DetrImageProcessor.from_pretrained(model_id)
    model = DetrForObjectDetection.from_pretrained(model_id).to(device())
    model.eval()
    inputs = processor(images=image, return_tensors="pt").to(device())
    with torch.no_grad():
        outputs = model(**inputs)
    target_sizes = torch.tensor([image.size[::-1]]).to(device())
    results = processor.post_process_object_detection(outputs, target_sizes=target_sizes, threshold=0.5)[0]
    id2label = model.config.id2label
    boxes = results["boxes"].cpu().numpy().tolist()
    labels = [id2label[i.item()] for i in results["labels"]]
    scores = results["scores"].cpu().numpy().tolist()
    free_model(processor, model)
    return boxes, labels, scores


def run_rt_detr(image):
    from transformers import RTDetrImageProcessor, RTDetrForObjectDetection
    mid = "PekingU/rtdetr_r101vd_coco_o365"
    processor = RTDetrImageProcessor.from_pretrained(mid)
    model = RTDetrForObjectDetection.from_pretrained(mid).to(device())
    model.eval()
    inputs = processor(images=image, return_tensors="pt").to(device())
    with torch.no_grad():
        outputs = model(**inputs)
    target_sizes = torch.tensor([image.size[::-1]]).to(device())
    results = processor.post_process_object_detection(outputs, target_sizes=target_sizes, threshold=0.5)[0]
    id2label = model.config.id2label
    boxes = results["boxes"].cpu().numpy().tolist()
    labels = [id2label[i.item()] for i in results["labels"]]
    scores = results["scores"].cpu().numpy().tolist()
    free_model(processor, model)
    return boxes, labels, scores


def run_deta(image):
    from transformers import AutoImageProcessor, AutoModelForObjectDetection
    mid = "jozhang97/deta-swin-large"
    processor = AutoImageProcessor.from_pretrained(mid)
    model = AutoModelForObjectDetection.from_pretrained(mid).to(device())
    model.eval()
    inputs = processor(images=image, return_tensors="pt").to(device())
    with torch.no_grad():
        outputs = model(**inputs)
    target_sizes = torch.tensor([image.size[::-1]]).to(device())
    results = processor.post_process_object_detection(outputs, target_sizes=target_sizes, threshold=0.5)[0]
    id2label = model.config.id2label
    boxes = results["boxes"].cpu().numpy().tolist()
    labels = [id2label[i.item()] for i in results["labels"]]
    scores = results["scores"].cpu().numpy().tolist()
    free_model(processor, model)
    return boxes, labels, scores


def run_grounding_dino(image):
    from transformers import AutoProcessor, AutoModelForZeroShotObjectDetection
    mid = "IDEA-Research/grounding-dino-base"
    processor = AutoProcessor.from_pretrained(mid)
    model = AutoModelForZeroShotObjectDetection.from_pretrained(mid).to(device())
    model.eval()
    inputs = processor(images=image, text=GROUNDING_DINO_PROMPT, return_tensors="pt").to(device())
    with torch.no_grad():
        outputs = model(**inputs)
    results = processor.post_process_grounded_object_detection(
        outputs,
        inputs.input_ids,
        box_threshold=0.35,
        text_threshold=0.25,
        target_sizes=[image.size[::-1]],
    )[0]
    boxes = results["boxes"].cpu().numpy().tolist()
    labels = results["labels"]
    scores = results["scores"].cpu().numpy().tolist()
    free_model(processor, model)
    return boxes, labels, scores


def run_owlv2(image):
    from transformers import Owlv2Processor, Owlv2ForObjectDetection
    mid = "google/owlv2-large-patch14-ensemble"
    processor = Owlv2Processor.from_pretrained(mid)
    model = Owlv2ForObjectDetection.from_pretrained(mid).to(device())
    model.eval()
    texts = [[f"a photo of a {c}" for c in SCS_CATEGORIES]]
    inputs = processor(text=texts, images=image, return_tensors="pt").to(device())
    with torch.no_grad():
        outputs = model(**inputs)
    target_sizes = torch.tensor([image.size[::-1]]).to(device())
    results = processor.post_process_object_detection(outputs, target_sizes=target_sizes, threshold=0.2)[0]
    boxes = results["boxes"].cpu().numpy().tolist()
    labels = [SCS_CATEGORIES[i.item()] for i in results["labels"]]
    scores = results["scores"].cpu().numpy().tolist()
    free_model(processor, model)
    return boxes, labels, scores


def run_florence(image):
    from transformers import AutoProcessor, AutoModelForCausalLM
    mid = "microsoft/Florence-2-large"
    processor = AutoProcessor.from_pretrained(mid, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(mid, trust_remote_code=True, torch_dtype=torch.float16).to(device())
    model.eval()
    prompt = "<OD>"
    inputs = processor(text=prompt, images=image, return_tensors="pt").to(device(), torch.float16)
    with torch.no_grad():
        gen = model.generate(input_ids=inputs["input_ids"], pixel_values=inputs["pixel_values"],
                             max_new_tokens=1024, num_beams=3, do_sample=False)
    text = processor.batch_decode(gen, skip_special_tokens=False)[0]
    parsed = processor.post_process_generation(text, task="<OD>", image_size=(image.width, image.height))
    od = parsed.get("<OD>", {"bboxes": [], "labels": []})
    boxes = od["bboxes"]
    labels = od["labels"]
    scores = [1.0] * len(boxes)
    free_model(processor, model)
    return boxes, labels, scores


def run_oneformer(image):
    from transformers import OneFormerProcessor, OneFormerForUniversalSegmentation
    mid = "shi-labs/oneformer_ade20k_swin_large"
    processor = OneFormerProcessor.from_pretrained(mid)
    model = OneFormerForUniversalSegmentation.from_pretrained(mid).to(device())
    model.eval()
    inputs = processor(images=image, task_inputs=["panoptic"], return_tensors="pt").to(device())
    with torch.no_grad():
        outputs = model(**inputs)
    result = processor.post_process_panoptic_segmentation(outputs, target_sizes=[image.size[::-1]])[0]
    id2label = model.config.id2label
    labels = []
    scores = []
    boxes = []
    for seg in result["segments_info"]:
        labels.append(id2label[seg["label_id"]])
        scores.append(seg.get("score", 1.0))
        boxes.append([0, 0, image.width, image.height])
    free_model(processor, model)
    return boxes, labels, scores


def run_siglip(image):
    from transformers import AutoProcessor, AutoModel
    mid = "google/siglip2-so400m-patch14-384"
    processor = AutoProcessor.from_pretrained(mid)
    model = AutoModel.from_pretrained(mid).to(device())
    model.eval()
    texts = [f"a photo of a {c}" for c in SCS_CATEGORIES]
    inputs = processor(text=texts, images=image, padding="max_length", return_tensors="pt").to(device())
    with torch.no_grad():
        outputs = model(**inputs)
    probs = torch.sigmoid(outputs.logits_per_image).squeeze(0)
    top = torch.topk(probs, k=min(5, len(SCS_CATEGORIES)))
    labels = [SCS_CATEGORIES[i.item()] for i in top.indices]
    scores = top.values.cpu().numpy().tolist()
    boxes = [[0, 0, image.width, image.height]] * len(labels)
    free_model(processor, model)
    return boxes, labels, scores


def run_dinov2(image):
    from transformers import AutoImageProcessor, AutoModel
    mid = "facebook/dinov2-large"
    processor = AutoImageProcessor.from_pretrained(mid)
    model = AutoModel.from_pretrained(mid).to(device())
    model.eval()
    inputs = processor(images=image, return_tensors="pt").to(device())
    with torch.no_grad():
        outputs = model(**inputs)
    embedding = outputs.last_hidden_state[:, 0, :].cpu().numpy().tolist()[0]
    labels = ["<embedding>"]
    scores = [float(sum(abs(x) for x in embedding) / len(embedding))]
    boxes = [[0, 0, image.width, image.height]]
    free_model(processor, model)
    return boxes, labels, scores


# -------- registry ------------------------------------------------------------

MODELS = {
    "detr_r50":        ("DETR ResNet-50",        lambda img: run_detr(img, "facebook/detr-resnet-50")),
    "detr_r101":       ("DETR ResNet-101",       lambda img: run_detr(img, "facebook/detr-resnet-101")),
    "rt_detr":         ("RT-DETR R101 VD",       run_rt_detr),
    "deta":            ("DETA Swin-Large",       run_deta),
    "grounding_dino":  ("Grounding DINO base",   run_grounding_dino),
    "owlv2":           ("OWLv2 large ensemble",  run_owlv2),
    "florence":        ("Florence-2 large",      run_florence),
    "oneformer":       ("OneFormer ADE20K Swin-L", run_oneformer),
    "siglip":          ("SigLIP 2 so400m",       run_siglip),
    "dinov2":          ("DINOv2-Large",          run_dinov2),
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True, help="Path to office photo")
    parser.add_argument("--models", nargs="+", default=list(MODELS.keys()),
                        help=f"Subset of models to run (default: all). Available: {list(MODELS.keys())}")
    parser.add_argument("--outdir", default="outputs", help="Output directory")
    args = parser.parse_args()

    image_path = Path(args.image)
    if not image_path.exists():
        raise SystemExit(f"image not found: {image_path}")
    image = Image.open(image_path).convert("RGB")
    print(f"loaded image: {image_path}  size={image.size}  device={device()}")

    outdir = Path(args.outdir)
    overlays_dir = outdir / "detection_overlays"
    csv_path = outdir / "detection_benchmark.csv"
    outdir.mkdir(parents=True, exist_ok=True)

    rows = []
    for key in args.models:
        if key not in MODELS:
            print(f"skipping unknown model: {key}")
            continue
        name, runner = MODELS[key]
        print(f"\n=== {name} ({key}) ===")
        reset_vram_peak()
        t0 = time.perf_counter()
        try:
            boxes, labels, scores = runner(image)
            ok = True
            err = ""
        except Exception as e:
            print(f"  ERROR: {e}")
            boxes, labels, scores = [], [], []
            ok = False
            err = str(e)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        peak_mb = vram_mb()

        n = len(labels)
        top5 = [(l, round(float(s), 3)) for l, s in zip(labels[:5], scores[:5])]
        print(f"  {n} detections   latency={elapsed_ms:.0f} ms   peak VRAM={peak_mb} MB")
        for lbl, sc in top5:
            print(f"    {lbl}  {sc}")

        if ok and boxes:
            draw_boxes(image, boxes, labels, scores, overlays_dir / f"{key}.jpg")

        rows.append({
            "key": key,
            "model": name,
            "ok": ok,
            "error": err,
            "n_detections": n,
            "top5": str(top5),
            "latency_ms": round(elapsed_ms, 1),
            "peak_vram_mb": peak_mb,
        })

    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["key", "model", "ok", "error", "n_detections", "top5",
                                          "latency_ms", "peak_vram_mb"])
        w.writeheader()
        w.writerows(rows)
    print(f"\nwrote {csv_path}")
    print(f"wrote overlays to {overlays_dir}/")


if __name__ == "__main__":
    main()
