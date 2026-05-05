"""
train_clip_office.py
====================
Fine-tunes CLIP (openai/clip-vit-base-patch32) on the office furniture images
downloaded by download_openimages.py.

Two training modes (selected via --mode):

  linear_probe  (default, fast)
      Freeze the entire CLIP vision encoder.
      Train only a single Linear(512, num_classes) head.
      Good baseline; typically converges in ~10 epochs.

  lora
      Apply Low-Rank Adaptation (LoRA) to the CLIP vision transformer layers
      using the PEFT library.  Trains LoRA params + classification head.
      Better accuracy; requires 'pip install peft'.

Dataset license: Open Images V7 — CC BY 4.0
Model license:   openai/clip-vit-base-patch32 — MIT (OpenAI)
PEFT library:    Apache 2.0

Usage:
    python scripts/train_clip_office.py
    python scripts/train_clip_office.py --mode linear_probe
    python scripts/train_clip_office.py --mode lora
    python scripts/train_clip_office.py --mode linear_probe --epochs 20 --batch 64
"""

from __future__ import annotations

import argparse
import csv
import sys
import warnings
from pathlib import Path

import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset, WeightedRandomSampler
from torchvision import transforms

warnings.filterwarnings("ignore", category=UserWarning)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT    = PROJECT_ROOT / "data" / "office_images"
MANIFEST     = DATA_ROOT / "manifest.csv"
MODEL_DIR    = PROJECT_ROOT / "models" / "clip_office"
BEST_MODEL   = MODEL_DIR / "best_model.pt"

# ---------------------------------------------------------------------------
# Dataset
# ---------------------------------------------------------------------------


class OfficeDataset(Dataset):
    """
    Loads (image, label_index) pairs from the manifest CSV.
    Applies provided transform pipeline.
    Skips corrupted / missing images with a warning.
    """

    def __init__(
        self,
        rows: list[tuple[str, str]],       # [(filepath, category), ...]
        label_to_idx: dict[str, int],
        transform,
        processor=None,
    ):
        self.rows = rows
        self.label_to_idx = label_to_idx
        self.transform = transform
        self.processor = processor

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, idx: int):
        from PIL import Image as PilImage

        filepath, category = self.rows[idx]
        label_idx = self.label_to_idx[category]

        try:
            img = PilImage.open(filepath).convert("RGB")
        except Exception:
            # Return a black image on failure so the batch still forms
            img = PilImage.new("RGB", (224, 224), (0, 0, 0))

        if self.transform is not None:
            img = self.transform(img)

        return img, label_idx


# ---------------------------------------------------------------------------
# Augmentation
# ---------------------------------------------------------------------------

TRAIN_TRANSFORM = transforms.Compose([
    transforms.RandomResizedCrop(224, scale=(0.7, 1.0)),
    transforms.RandomHorizontalFlip(),
    transforms.ColorJitter(brightness=0.3, contrast=0.3, saturation=0.2, hue=0.05),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.48145466, 0.4578275,  0.40821073],
                         std =[0.26862954, 0.26130258, 0.27577711]),
])

EVAL_TRANSFORM = transforms.Compose([
    transforms.Resize(224),
    transforms.CenterCrop(224),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.48145466, 0.4578275,  0.40821073],
                         std =[0.26862954, 0.26130258, 0.27577711]),
])

# ---------------------------------------------------------------------------
# Model definitions
# ---------------------------------------------------------------------------


class CLIPLinearProbe(nn.Module):
    """Frozen CLIP vision encoder + trainable linear classification head."""

    def __init__(self, num_classes: int, clip_model):
        super().__init__()
        self.vision_encoder = clip_model.vision_model
        self.visual_projection = clip_model.visual_projection  # 768 → 512
        # Freeze everything
        for p in self.vision_encoder.parameters():
            p.requires_grad_(False)
        for p in self.visual_projection.parameters():
            p.requires_grad_(False)
        # Trainable head
        self.head = nn.Linear(512, num_classes)

    def forward(self, pixel_values: torch.Tensor) -> torch.Tensor:
        vision_outputs = self.vision_encoder(pixel_values=pixel_values)
        pooled = vision_outputs.pooler_output          # (B, 768)
        image_features = self.visual_projection(pooled)  # (B, 512)
        image_features = image_features / image_features.norm(dim=-1, keepdim=True)
        return self.head(image_features)


def build_lora_model(num_classes: int, clip_model):
    """
    Apply LoRA to the CLIP vision encoder attention layers using PEFT.
    Returns (lora_clip_model, head).
    Raises ImportError if PEFT is not installed.
    """
    from peft import get_peft_model, LoraConfig, TaskType

    # LoRA targets: query and value projections in every attention layer
    lora_cfg = LoraConfig(
        r=16,
        lora_alpha=32,
        target_modules=["q_proj", "v_proj"],
        lora_dropout=0.1,
        bias="none",
    )
    lora_model = get_peft_model(clip_model.vision_model, lora_cfg)
    lora_model.print_trainable_parameters()

    head = nn.Linear(512, num_classes)

    class LoRAClipModel(nn.Module):
        def __init__(self):
            super().__init__()
            self.vision_model = lora_model
            self.visual_projection = clip_model.visual_projection
            # LoRA params are trainable; freeze projection for speed
            for p in self.visual_projection.parameters():
                p.requires_grad_(False)
            self.head = head

        def forward(self, pixel_values: torch.Tensor) -> torch.Tensor:
            out = self.vision_model(pixel_values=pixel_values)
            pooled = out.pooler_output
            feats = self.visual_projection(pooled)
            feats = feats / feats.norm(dim=-1, keepdim=True)
            return self.head(feats)

    return LoRAClipModel()


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def load_manifest(manifest_path: Path) -> tuple[list[tuple[str, str]], dict[str, int]]:
    """Returns (rows, label_to_idx) from manifest.csv."""
    if not manifest_path.exists():
        print(
            f"ERROR: manifest not found at {manifest_path}\n"
            "Run download_openimages.py first.",
            file=sys.stderr,
        )
        sys.exit(1)

    rows: list[tuple[str, str]] = []
    categories: set[str] = set()

    with open(manifest_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            fp = row["filepath"].strip()
            cat = row["category"].strip()
            if Path(fp).exists():
                rows.append((fp, cat))
                categories.add(cat)
            # silently skip missing files

    if not rows:
        print("ERROR: manifest is empty or all files are missing.", file=sys.stderr)
        sys.exit(1)

    label_to_idx = {cat: i for i, cat in enumerate(sorted(categories))}
    print(f"Loaded {len(rows)} images across {len(label_to_idx)} classes")
    return rows, label_to_idx


def stratified_split(
    rows: list[tuple[str, str]],
    label_to_idx: dict[str, int],
    train_frac: float = 0.8,
    val_frac: float = 0.1,
) -> tuple[list, list, list]:
    """
    Stratified split by category.
    Returns (train_rows, val_rows, test_rows).
    """
    import random
    from collections import defaultdict

    random.seed(42)
    by_cat: dict[str, list] = defaultdict(list)
    for row in rows:
        by_cat[row[1]].append(row)

    train, val, test = [], [], []
    for cat, cat_rows in by_cat.items():
        random.shuffle(cat_rows)
        n = len(cat_rows)
        n_train = max(1, int(n * train_frac))
        n_val   = max(1, int(n * val_frac))
        train.extend(cat_rows[:n_train])
        val.extend(cat_rows[n_train:n_train + n_val])
        test.extend(cat_rows[n_train + n_val:])

    return train, val, test


# ---------------------------------------------------------------------------
# Training loop
# ---------------------------------------------------------------------------


def train_epoch(
    model: nn.Module,
    loader: DataLoader,
    optimizer: torch.optim.Optimizer,
    criterion: nn.Module,
    device: torch.device,
    scaler,
) -> float:
    model.train()
    total_loss = 0.0
    for pixel_values, labels in loader:
        pixel_values = pixel_values.to(device)
        labels = labels.to(device)

        optimizer.zero_grad()
        if scaler is not None:
            with torch.amp.autocast("cuda"):
                logits = model(pixel_values)
                loss = criterion(logits, labels)
            scaler.scale(loss).backward()
            scaler.unscale_(optimizer)
            torch.nn.utils.clip_grad_norm_(
                (p for p in model.parameters() if p.requires_grad), 1.0
            )
            scaler.step(optimizer)
            scaler.update()
        else:
            logits = model(pixel_values)
            loss = criterion(logits, labels)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(
                (p for p in model.parameters() if p.requires_grad), 1.0
            )
            optimizer.step()

        total_loss += loss.item() * labels.size(0)

    return total_loss / len(loader.dataset)


@torch.no_grad()
def evaluate(
    model: nn.Module,
    loader: DataLoader,
    criterion: nn.Module,
    device: torch.device,
    num_classes: int,
) -> tuple[float, float, list[float]]:
    """Returns (loss, accuracy, per_class_accuracy)."""
    model.eval()
    total_loss = 0.0
    correct = 0
    per_class_correct = [0] * num_classes
    per_class_total   = [0] * num_classes

    for pixel_values, labels in loader:
        pixel_values = pixel_values.to(device)
        labels = labels.to(device)
        logits = model(pixel_values)
        loss = criterion(logits, labels)
        total_loss += loss.item() * labels.size(0)
        preds = logits.argmax(dim=-1)
        correct += (preds == labels).sum().item()
        for pred, label in zip(preds.cpu().tolist(), labels.cpu().tolist()):
            per_class_total[label] += 1
            if pred == label:
                per_class_correct[label] += 1

    n = len(loader.dataset)
    avg_loss = total_loss / n
    avg_acc  = correct / n
    per_class_acc = [
        per_class_correct[i] / max(per_class_total[i], 1)
        for i in range(num_classes)
    ]
    return avg_loss, avg_acc, per_class_acc


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Fine-tune CLIP on office images")
    parser.add_argument(
        "--mode", choices=["linear_probe", "lora"], default="linear_probe",
        help="Training mode: linear_probe (fast) or lora (better, requires peft)",
    )
    parser.add_argument("--epochs", type=int, default=None,
                        help="Override default epochs (10 for linear_probe, 20 for lora)")
    parser.add_argument("--batch", type=int, default=32, help="Batch size (default 32)")
    parser.add_argument("--lr", type=float, default=None,
                        help="Learning rate (default 1e-3 for probe, 1e-4 for lora)")
    parser.add_argument("--workers", type=int, default=4,
                        help="DataLoader num_workers (default 4)")
    args = parser.parse_args()

    # Defaults per mode
    epochs = args.epochs or (10 if args.mode == "linear_probe" else 20)
    lr     = args.lr     or (1e-3 if args.mode == "linear_probe" else 1e-4)

    # Device
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")
    if device.type == "cuda":
        print(f"  GPU: {torch.cuda.get_device_name(0)}")

    # Data
    rows, label_to_idx = load_manifest(MANIFEST)
    idx_to_label = {v: k for k, v in label_to_idx.items()}
    num_classes = len(label_to_idx)
    train_rows, val_rows, test_rows = stratified_split(rows, label_to_idx)
    print(f"Split: {len(train_rows)} train / {len(val_rows)} val / {len(test_rows)} test")

    train_ds = OfficeDataset(train_rows, label_to_idx, TRAIN_TRANSFORM)
    val_ds   = OfficeDataset(val_rows,   label_to_idx, EVAL_TRANSFORM)
    test_ds  = OfficeDataset(test_rows,  label_to_idx, EVAL_TRANSFORM)

    # Weighted sampler for class imbalance
    from collections import Counter
    label_counts = Counter(r[1] for r in train_rows)
    weights = [1.0 / label_counts[r[1]] for r in train_rows]
    sampler = WeightedRandomSampler(weights, num_samples=len(weights), replacement=True)

    train_loader = DataLoader(
        train_ds, batch_size=args.batch, sampler=sampler,
        num_workers=args.workers, pin_memory=(device.type == "cuda"),
    )
    val_loader = DataLoader(
        val_ds, batch_size=args.batch * 2, shuffle=False,
        num_workers=args.workers, pin_memory=(device.type == "cuda"),
    )
    test_loader = DataLoader(
        test_ds, batch_size=args.batch * 2, shuffle=False,
        num_workers=args.workers, pin_memory=(device.type == "cuda"),
    )

    # Load CLIP
    print("\nLoading CLIP model (openai/clip-vit-base-patch32) ...")
    from transformers import CLIPModel
    clip_model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32")
    clip_model.eval()

    # Build task model
    if args.mode == "linear_probe":
        print("Mode: Linear Probe (frozen CLIP + trainable head)")
        model = CLIPLinearProbe(num_classes, clip_model)
        trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
        print(f"  Trainable parameters: {trainable:,}")
    else:
        print("Mode: LoRA fine-tuning")
        try:
            model = build_lora_model(num_classes, clip_model)
        except ImportError:
            print(
                "\nERROR: 'peft' library not found.\n"
                "Install it with:  pip install peft\n"
                "Or use --mode linear_probe instead.",
                file=sys.stderr,
            )
            sys.exit(1)

    model = model.to(device)

    # Optimizer & scheduler
    trainable_params = [p for p in model.parameters() if p.requires_grad]
    optimizer = torch.optim.AdamW(trainable_params, lr=lr, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)
    criterion = nn.CrossEntropyLoss(label_smoothing=0.1)

    # Mixed precision scaler
    scaler = torch.amp.GradScaler("cuda") if device.type == "cuda" else None

    # Training
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    best_val_acc = 0.0
    best_epoch = 0

    print(f"\n{'Epoch':>6}  {'Train Loss':>11}  {'Val Loss':>9}  {'Val Acc':>8}  {'Best':>5}")
    print("-" * 55)

    for epoch in range(1, epochs + 1):
        train_loss = train_epoch(model, train_loader, optimizer, criterion, device, scaler)
        val_loss, val_acc, _ = evaluate(model, val_loader, criterion, device, num_classes)
        scheduler.step()

        is_best = val_acc > best_val_acc
        marker = " *" if is_best else ""
        print(
            f"{epoch:>6}  {train_loss:>11.4f}  {val_loss:>9.4f}  {val_acc:>8.2%}{marker}"
        )

        if is_best:
            best_val_acc = val_acc
            best_epoch = epoch
            torch.save(
                {
                    "model_state_dict": model.state_dict(),
                    "label_to_idx": label_to_idx,
                    "mode": args.mode,
                    "val_accuracy": val_acc,
                    "epoch": epoch,
                    "num_classes": num_classes,
                },
                BEST_MODEL,
            )

    print(f"\nBest val accuracy: {best_val_acc:.2%}  (epoch {best_epoch})")
    print(f"Checkpoint saved:  {BEST_MODEL}")

    # Test evaluation
    print("\nLoading best checkpoint for test evaluation ...")
    ckpt = torch.load(BEST_MODEL, map_location=device, weights_only=False)
    model.load_state_dict(ckpt["model_state_dict"])

    test_loss, test_acc, per_class_acc = evaluate(
        model, test_loader, criterion, device, num_classes
    )

    print(f"\n{'=' * 55}")
    print(f"TEST ACCURACY: {test_acc:.2%}")
    print(f"{'=' * 55}")
    print(f"\n{'Class':30s}  {'Accuracy':>8}")
    print("-" * 42)
    for idx in sorted(idx_to_label):
        cls = idx_to_label[idx]
        acc = per_class_acc[idx]
        print(f"  {cls:28s}  {acc:8.2%}")
    print("-" * 42)
    print(f"  {'AVERAGE':28s}  {test_acc:8.2%}")


if __name__ == "__main__":
    main()
