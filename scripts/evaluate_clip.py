"""
evaluate_clip.py
================
Side-by-side evaluation of zero-shot CLIP vs fine-tuned CLIP on the office
furniture categories downloaded by download_openimages.py.

Without --image   : runs on the test split from data/office_images/manifest.csv
With    --image   : classifies a single image and shows both models' top prediction

Output example:

    === CLIP Evaluation ===
    Zero-shot CLIP:
      office_chair:    91.2%  ✓
      monitor:         67.3%  ✓
      filing_cabinet:  43.1%  ✗ (predicted: cabinet)

    Fine-tuned CLIP:
      office_chair:    96.8%  ✓
      monitor:         94.2%  ✓
      filing_cabinet:  91.7%  ✓

    Average improvement: +23.4%

Dataset license: Open Images V7 — CC BY 4.0
Model license:   openai/clip-vit-base-patch32 — MIT (OpenAI)

Usage:
    python scripts/evaluate_clip.py
    python scripts/evaluate_clip.py --image path/to/chair.jpg
    python scripts/evaluate_clip.py --split test
    python scripts/evaluate_clip.py --image my_photo.jpg --no_finetuned
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import torch
import torch.nn.functional as F
from torchvision import transforms

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT    = PROJECT_ROOT / "data" / "office_images"
MANIFEST     = DATA_ROOT / "manifest.csv"
BEST_MODEL   = PROJECT_ROOT / "models" / "clip_office" / "best_model.pt"

# Text prompts used for zero-shot CLIP — one per category slug
CATEGORY_PROMPTS: dict[str, list[str]] = {
    "office_chair":  ["a photo of an office chair", "an office chair"],
    "table":         ["a photo of a table", "a dining or work table"],
    "desk":          ["a photo of a desk", "an office desk or writing desk"],
    "cabinet":       ["a photo of a cabinet", "a storage cabinet"],
    "monitor":       ["a photo of a computer monitor", "a computer screen or display"],
    "filing_cabinet":["a photo of a filing cabinet", "a metal filing cabinet"],
    "lamp":          ["a photo of a lamp", "a floor lamp or table lamp"],
    "bookshelf":     ["a photo of a bookcase or bookshelf", "shelves with books"],
    "keyboard":      ["a photo of a computer keyboard", "a keyboard for typing"],
    "mouse":         ["a photo of a computer mouse", "a computer mouse device"],
    "desk_lamp":     ["a photo of a desk lamp", "a small lamp on a desk"],
}

EVAL_TRANSFORM = transforms.Compose([
    transforms.Resize(224),
    transforms.CenterCrop(224),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.48145466, 0.4578275,  0.40821073],
                         std =[0.26862954, 0.26130258, 0.27577711]),
])

# ---------------------------------------------------------------------------
# Zero-shot CLIP inference
# ---------------------------------------------------------------------------


class ZeroShotCLIP:
    """
    Wraps openai/clip-vit-base-patch32 for zero-shot classification.
    Uses softmax over cosine similarities between image and text prompts.
    """

    def __init__(self, categories: list[str], device: torch.device):
        from transformers import CLIPModel, CLIPProcessor

        print("Loading zero-shot CLIP ...", flush=True)
        self.model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32").to(device)
        self.processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
        self.device = device
        self.categories = categories

        # Pre-encode text prompts (average multiple prompts per class)
        all_text_embeds: list[torch.Tensor] = []
        for cat in categories:
            prompts = CATEGORY_PROMPTS.get(cat, [f"a photo of a {cat}"])
            inputs = self.processor(
                text=prompts, return_tensors="pt", padding=True, truncation=True
            )
            inputs = {k: v.to(device) for k, v in inputs.items()}
            with torch.no_grad():
                text_features = self.model.get_text_features(**inputs)   # (P, 512)
                text_features = text_features / text_features.norm(dim=-1, keepdim=True)
                text_features = text_features.mean(dim=0, keepdim=True)  # (1, 512)
                text_features = text_features / text_features.norm(dim=-1, keepdim=True)
            all_text_embeds.append(text_features)

        # text_embeds: (num_classes, 512)
        self.text_embeds = torch.cat(all_text_embeds, dim=0)
        self.model.eval()

    @torch.no_grad()
    def predict_batch(
        self, pixel_tensors: torch.Tensor
    ) -> tuple[list[int], list[float]]:
        """
        pixel_tensors: (B, 3, 224, 224) already normalised
        Returns (predicted_indices, confidence_scores).
        """
        pixel_tensors = pixel_tensors.to(self.device)
        image_features = self.model.vision_model(pixel_values=pixel_tensors).pooler_output
        image_features = self.model.visual_projection(image_features)
        image_features = image_features / image_features.norm(dim=-1, keepdim=True)

        # Cosine similarity → temperature-scaled softmax
        logits = image_features @ self.text_embeds.T  # (B, C)
        logits = logits * self.model.logit_scale.exp()
        probs = F.softmax(logits, dim=-1)              # (B, C)

        preds = probs.argmax(dim=-1).cpu().tolist()
        confs = probs.max(dim=-1).values.cpu().tolist()
        return preds, confs

    @torch.no_grad()
    def predict_image(self, image_path: str) -> tuple[str, float, dict[str, float]]:
        """
        Predict a single image.
        Returns (predicted_category, confidence, all_scores_dict).
        """
        from PIL import Image as PilImage
        img = PilImage.open(image_path).convert("RGB")
        tensor = EVAL_TRANSFORM(img).unsqueeze(0).to(self.device)

        image_features = self.model.vision_model(pixel_values=tensor).pooler_output
        image_features = self.model.visual_projection(image_features)
        image_features = image_features / image_features.norm(dim=-1, keepdim=True)

        logits = image_features @ self.text_embeds.T
        logits = logits * self.model.logit_scale.exp()
        probs = F.softmax(logits, dim=-1).squeeze(0).cpu().tolist()

        all_scores = {cat: probs[i] for i, cat in enumerate(self.categories)}
        best_idx = max(range(len(probs)), key=lambda i: probs[i])
        return self.categories[best_idx], probs[best_idx], all_scores


# ---------------------------------------------------------------------------
# Fine-tuned CLIP inference
# ---------------------------------------------------------------------------


class FineTunedCLIP:
    """
    Loads the checkpoint saved by train_clip_office.py and runs inference.
    Supports both linear_probe and lora modes transparently.
    """

    def __init__(self, checkpoint_path: Path, device: torch.device):
        import torch.nn as nn
        from transformers import CLIPModel

        print(f"Loading fine-tuned model from {checkpoint_path} ...", flush=True)
        ckpt = torch.load(checkpoint_path, map_location=device, weights_only=False)

        self.label_to_idx: dict[str, int] = ckpt["label_to_idx"]
        self.idx_to_label: dict[int, str] = {v: k for k, v in self.label_to_idx.items()}
        self.num_classes = ckpt["num_classes"]
        self.mode = ckpt.get("mode", "linear_probe")
        self.device = device

        clip_model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32")

        if self.mode == "lora":
            try:
                # Reconstruct LoRA model structure
                # (LoRA adapters are included in state dict automatically)
                from peft import PeftModel
                # We rebuild the wrapper; actual LoRA weights are in state dict
                model = self._build_lora_wrapper(clip_model, self.num_classes)
            except ImportError:
                print(
                    "WARNING: peft not installed, falling back to linear_probe reconstruction",
                    file=sys.stderr,
                )
                model = self._build_probe_wrapper(clip_model, self.num_classes)
        else:
            model = self._build_probe_wrapper(clip_model, self.num_classes)

        model.load_state_dict(ckpt["model_state_dict"], strict=False)
        model.eval()
        self.model = model.to(device)

        self.categories = [self.idx_to_label[i] for i in range(self.num_classes)]
        val_acc = ckpt.get("val_accuracy", 0.0)
        print(
            f"  Mode: {self.mode}  |  "
            f"Classes: {self.num_classes}  |  "
            f"Val acc: {val_acc:.2%}"
        )

    @staticmethod
    def _build_probe_wrapper(clip_model, num_classes: int):
        """Re-create the CLIPLinearProbe architecture."""
        import torch.nn as nn

        class _Probe(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.vision_encoder = clip_model.vision_model
                self.visual_projection = clip_model.visual_projection
                self.head = nn.Linear(512, num_classes)

            def forward(self, pixel_values):
                out = self.vision_encoder(pixel_values=pixel_values)
                feats = self.visual_projection(out.pooler_output)
                feats = feats / feats.norm(dim=-1, keepdim=True)
                return self.head(feats)

        return _Probe()

    @staticmethod
    def _build_lora_wrapper(clip_model, num_classes: int):
        """Re-create the LoRA model architecture (without applying LoRA again)."""
        import torch.nn as nn

        class _LoRA(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.vision_model = clip_model.vision_model
                self.visual_projection = clip_model.visual_projection
                self.head = nn.Linear(512, num_classes)

            def forward(self, pixel_values):
                out = self.vision_model(pixel_values=pixel_values)
                feats = self.visual_projection(out.pooler_output)
                feats = feats / feats.norm(dim=-1, keepdim=True)
                return self.head(feats)

        return _LoRA()

    @torch.no_grad()
    def predict_batch(
        self, pixel_tensors: torch.Tensor
    ) -> tuple[list[int], list[float]]:
        pixel_tensors = pixel_tensors.to(self.device)
        logits = self.model(pixel_tensors)
        probs  = F.softmax(logits, dim=-1)
        preds  = probs.argmax(dim=-1).cpu().tolist()
        confs  = probs.max(dim=-1).values.cpu().tolist()
        return preds, confs

    @torch.no_grad()
    def predict_image(self, image_path: str) -> tuple[str, float, dict[str, float]]:
        from PIL import Image as PilImage
        img = PilImage.open(image_path).convert("RGB")
        tensor = EVAL_TRANSFORM(img).unsqueeze(0).to(self.device)
        logits = self.model(tensor)
        probs  = F.softmax(logits, dim=-1).squeeze(0).cpu().tolist()
        all_scores = {self.idx_to_label[i]: probs[i] for i in range(self.num_classes)}
        best_idx   = max(range(len(probs)), key=lambda i: probs[i])
        return self.idx_to_label[best_idx], probs[best_idx], all_scores


# ---------------------------------------------------------------------------
# Evaluation on test split
# ---------------------------------------------------------------------------


def load_test_split(manifest_path: Path) -> tuple[list[tuple[str, str]], dict[str, int]]:
    """Re-creates the same 80/10/10 test split as train_clip_office.py."""
    import random
    from collections import defaultdict

    if not manifest_path.exists():
        print(f"ERROR: manifest not found at {manifest_path}", file=sys.stderr)
        sys.exit(1)

    rows: list[tuple[str, str]] = []
    categories: set[str] = set()

    with open(manifest_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            fp  = row["filepath"].strip()
            cat = row["category"].strip()
            if Path(fp).exists():
                rows.append((fp, cat))
                categories.add(cat)

    label_to_idx = {cat: i for i, cat in enumerate(sorted(categories))}

    # Reproduce the same deterministic stratified split
    random.seed(42)
    by_cat: dict[str, list] = defaultdict(list)
    for row in rows:
        by_cat[row[1]].append(row)

    test_rows: list[tuple[str, str]] = []
    for cat, cat_rows in by_cat.items():
        random.shuffle(cat_rows)
        n = len(cat_rows)
        n_train = max(1, int(n * 0.8))
        n_val   = max(1, int(n * 0.1))
        test_rows.extend(cat_rows[n_train + n_val:])

    return test_rows, label_to_idx


def run_batch_evaluation(
    test_rows: list[tuple[str, str]],
    label_to_idx: dict[str, int],
    zero_shot: ZeroShotCLIP,
    fine_tuned: FineTunedCLIP | None,
    batch_size: int = 64,
) -> None:
    """Evaluate both models on the full test set and print comparison."""
    from torch.utils.data import DataLoader, Dataset
    from PIL import Image as PilImage

    idx_to_label = {v: k for k, v in label_to_idx.items()}
    categories   = [idx_to_label[i] for i in range(len(label_to_idx))]
    num_classes  = len(categories)

    class _DS(Dataset):
        def __init__(self, rows):
            self.rows = rows
        def __len__(self):
            return len(self.rows)
        def __getitem__(self, i):
            fp, cat = self.rows[i]
            try:
                img = PilImage.open(fp).convert("RGB")
            except Exception:
                img = PilImage.new("RGB", (224, 224))
            return EVAL_TRANSFORM(img), label_to_idx[cat]

    loader = DataLoader(_DS(test_rows), batch_size=batch_size, shuffle=False, num_workers=2)

    # Counters
    zs_per_class_correct  = [0] * num_classes
    ft_per_class_correct  = [0] * num_classes
    per_class_total       = [0] * num_classes
    zs_pred_when_wrong: dict[int, dict[int, int]] = {}  # true → {pred: count}

    print("Running inference ...", flush=True)
    for pixel_tensors, labels in loader:
        zs_preds, zs_confs = zero_shot.predict_batch(pixel_tensors)
        if fine_tuned is not None:
            ft_preds, ft_confs = fine_tuned.predict_batch(pixel_tensors)
        for i, true_idx in enumerate(labels.tolist()):
            per_class_total[true_idx] += 1
            if zs_preds[i] == true_idx:
                zs_per_class_correct[true_idx] += 1
            else:
                zs_pred_when_wrong.setdefault(true_idx, {})
                zs_pred_when_wrong[true_idx][zs_preds[i]] = (
                    zs_pred_when_wrong[true_idx].get(zs_preds[i], 0) + 1
                )
            if fine_tuned is not None and ft_preds[i] == true_idx:
                ft_per_class_correct[true_idx] += 1

    # Compute per-class accuracy
    zs_accs  = [zs_per_class_correct[i] / max(per_class_total[i], 1) for i in range(num_classes)]
    ft_accs  = (
        [ft_per_class_correct[i] / max(per_class_total[i], 1) for i in range(num_classes)]
        if fine_tuned is not None else None
    )
    zs_avg   = sum(zs_accs) / max(len(zs_accs), 1)
    ft_avg   = sum(ft_accs) / max(len(ft_accs), 1) if ft_accs else None

    # ── Print report ────────────────────────────────────────────────────────
    print("\n=== CLIP Evaluation ===\n")

    print("Zero-shot CLIP:")
    for i, cat in enumerate(categories):
        acc   = zs_accs[i]
        mark  = "✓" if acc >= 0.5 else "✗"
        wrong_note = ""
        if acc < 0.5 and i in zs_pred_when_wrong:
            top_wrong_idx = max(zs_pred_when_wrong[i], key=zs_pred_when_wrong[i].get)
            wrong_note = f" (most confused with: {categories[top_wrong_idx]})"
        print(f"  {cat:20s}: {acc:6.1%}  {mark}{wrong_note}")
    print(f"\n  Average accuracy: {zs_avg:.1%}")

    if ft_accs is not None:
        print("\nFine-tuned CLIP:")
        for i, cat in enumerate(categories):
            acc  = ft_accs[i]
            mark = "✓" if acc >= 0.5 else "✗"
            print(f"  {cat:20s}: {acc:6.1%}  {mark}")
        print(f"\n  Average accuracy: {ft_avg:.1%}")

        delta = ft_avg - zs_avg
        sign  = "+" if delta >= 0 else ""
        print(f"\nAverage improvement: {sign}{delta:.1%}")


# ---------------------------------------------------------------------------
# Single-image evaluation
# ---------------------------------------------------------------------------


def run_single_image(
    image_path: str,
    zero_shot: ZeroShotCLIP,
    fine_tuned: FineTunedCLIP | None,
) -> None:
    p = Path(image_path)
    if not p.exists():
        print(f"ERROR: image not found: {image_path}", file=sys.stderr)
        sys.exit(1)

    print(f"\n=== CLIP Evaluation: {p.name} ===\n")

    # Zero-shot
    zs_pred, zs_conf, zs_scores = zero_shot.predict_image(image_path)
    print("Zero-shot CLIP:")
    for cat, score in sorted(zs_scores.items(), key=lambda x: -x[1]):
        mark = "  <-- predicted" if cat == zs_pred else ""
        print(f"  {cat:20s}: {score:6.1%}{mark}")

    if fine_tuned is not None:
        ft_pred, ft_conf, ft_scores = fine_tuned.predict_image(image_path)
        print("\nFine-tuned CLIP:")
        for cat, score in sorted(ft_scores.items(), key=lambda x: -x[1]):
            mark = "  <-- predicted" if cat == ft_pred else ""
            print(f"  {cat:20s}: {score:6.1%}{mark}")

        delta = ft_conf - zs_conf
        sign  = "+" if delta >= 0 else ""
        if zs_pred == ft_pred:
            print(f"\nBoth models agree: {zs_pred}  ({sign}{delta:.1%} confidence change)")
        else:
            print(f"\nZero-shot: {zs_pred} ({zs_conf:.1%})")
            print(f"Fine-tuned: {ft_pred} ({ft_conf:.1%})")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate zero-shot vs fine-tuned CLIP on office furniture"
    )
    parser.add_argument("--image", type=str, default=None,
                        help="Path to a single image to classify")
    parser.add_argument("--no_finetuned", action="store_true",
                        help="Skip loading fine-tuned model (zero-shot only)")
    parser.add_argument("--batch", type=int, default=64,
                        help="Batch size for dataset evaluation (default 64)")
    parser.add_argument("--split", choices=["test", "val", "all"], default="test",
                        help="Which manifest split to evaluate (default: test)")
    args = parser.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}\n")

    # Determine categories for zero-shot from fine-tuned checkpoint (if available)
    # or fall back to the full CATEGORY_PROMPTS list
    if BEST_MODEL.exists() and not args.no_finetuned:
        ckpt_label_to_idx: dict[str, int] = torch.load(
            BEST_MODEL, map_location="cpu", weights_only=False
        )["label_to_idx"]
        num_classes = len(ckpt_label_to_idx)
        categories  = [
            {v: k for k, v in ckpt_label_to_idx.items()}[i]
            for i in range(num_classes)
        ]
    else:
        categories = list(CATEGORY_PROMPTS.keys())

    # Load zero-shot model
    zero_shot = ZeroShotCLIP(categories, device)

    # Load fine-tuned model
    fine_tuned: FineTunedCLIP | None = None
    if not args.no_finetuned:
        if BEST_MODEL.exists():
            try:
                fine_tuned = FineTunedCLIP(BEST_MODEL, device)
            except Exception as exc:
                print(
                    f"WARNING: could not load fine-tuned model ({exc})\n"
                    "Running zero-shot only.",
                    file=sys.stderr,
                )
        else:
            print(
                f"INFO: No fine-tuned checkpoint found at {BEST_MODEL}.\n"
                "Run train_clip_office.py first, or use --no_finetuned.\n"
                "Proceeding with zero-shot only.\n"
            )

    # Route to single-image or batch evaluation
    if args.image:
        run_single_image(args.image, zero_shot, fine_tuned)
    else:
        if not MANIFEST.exists():
            print(
                f"ERROR: manifest not found at {MANIFEST}\n"
                "Run download_openimages.py first, or provide --image.",
                file=sys.stderr,
            )
            sys.exit(1)
        test_rows, label_to_idx = load_test_split(MANIFEST)
        if not test_rows:
            print("ERROR: no test images found in manifest.", file=sys.stderr)
            sys.exit(1)
        print(f"Evaluating on {len(test_rows)} test images ...\n")
        run_batch_evaluation(test_rows, label_to_idx, zero_shot, fine_tuned, args.batch)


if __name__ == "__main__":
    main()
