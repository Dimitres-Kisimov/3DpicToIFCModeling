"""
download_openimages.py
======================
Downloads up to 2000 images per category from the Google Open Images V7 dataset
using the publicly available metadata CSVs and Flickr-hosted image URLs.
No API key required.

Dataset license: Open Images Dataset is licensed under Creative Commons
Attribution 4.0 International (CC BY 4.0).
See https://storage.googleapis.com/openimages/web/factsfigures_v7.html

Pipeline:
  1. Fetch class-descriptions-boxable.csv  → map human name → LabelName (MID)
  2. Fetch train-images-boxable-with-rotation.csv → map ImageID → URL
  3. For each category, fetch train-annotations-human-imagelabels.csv lines
     whose LabelName matches and Confidence == 1 → collect ImageIDs → download
  4. Save to  data/office_images/<category_name>/image_<i>.jpg
  5. Write  data/office_images/manifest.csv

Usage:
    python scripts/download_openimages.py
    python scripts/download_openimages.py --max_per_class 500  # quick test
    python scripts/download_openimages.py --workers 16
"""

import argparse
import csv
import io
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests
from tqdm import tqdm

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

CATEGORIES = {
    "Chair":             "office_chair",
    "Table":             "table",
    "Desk":              "desk",
    "Cabinet":           "cabinet",
    "Computer monitor":  "monitor",
    "Filing cabinet":    "filing_cabinet",
    "Lamp":              "lamp",
    "Bookcase":          "bookshelf",
    "Computer keyboard": "keyboard",
    "Computer mouse":    "mouse",
    "Desk lamp":         "desk_lamp",
}

DEFAULT_MAX_PER_CLASS = 2000
DEFAULT_WORKERS = 8

# Public Open Images URLs (no auth required)
URL_CLASS_DESC_BOXABLE = (
    "https://storage.googleapis.com/openimages/v5/class-descriptions-boxable.csv"
)
URL_CLASS_DESC_V6 = (
    "https://storage.googleapis.com/openimages/v6/oidv6-class-descriptions.csv"
)
URL_TRAIN_IMAGES = (
    "https://storage.googleapis.com/openimages/2018_04/train/"
    "train-images-boxable-with-rotation.csv"
)
URL_TRAIN_LABELS = (
    "https://storage.googleapis.com/openimages/v5/"
    "train-annotations-human-imagelabels.csv"
)

DATA_ROOT = Path(__file__).resolve().parent.parent / "data" / "office_images"
MANIFEST_PATH = DATA_ROOT / "manifest.csv"
CACHE_DIR = DATA_ROOT / "_cache"

SESSION_TIMEOUT = 15   # seconds per image download
RETRY_DELAY = 1.0      # seconds between retries
MAX_RETRIES = 2

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": "3DpicToIFC-OpenImages-Downloader/1.0"})
    return s


def _download_text(url: str, desc: str, session: requests.Session) -> str:
    """Stream-download a potentially large text file, return as string."""
    print(f"  Downloading {desc} ...", flush=True)
    r = session.get(url, stream=True, timeout=120)
    r.raise_for_status()
    chunks = []
    total = int(r.headers.get("content-length", 0))
    with tqdm(total=total, unit="B", unit_scale=True, desc=desc, leave=False) as bar:
        for chunk in r.iter_content(chunk_size=1 << 20):
            chunks.append(chunk)
            bar.update(len(chunk))
    return b"".join(chunks).decode("utf-8", errors="replace")


def _cache_path(name: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / name


def _get_cached_or_download(url: str, cache_name: str, desc: str,
                             session: requests.Session) -> str:
    """Return text content from local cache or download it once."""
    p = _cache_path(cache_name)
    if p.exists():
        print(f"  Using cached {desc}", flush=True)
        return p.read_text(encoding="utf-8", errors="replace")
    text = _download_text(url, desc, session)
    p.write_text(text, encoding="utf-8")
    return text


# ---------------------------------------------------------------------------
# Step 1 – Build name → LabelName mapping
# ---------------------------------------------------------------------------


def build_label_map(session: requests.Session) -> dict[str, str]:
    """
    Returns {human_readable_name_lower: mid_label_name} from both class-desc CSVs.
    We union both CSVs to maximise coverage.
    """
    label_map: dict[str, str] = {}

    for url, cache, desc in [
        (URL_CLASS_DESC_BOXABLE, "class_desc_boxable.csv", "class descriptions (boxable)"),
        (URL_CLASS_DESC_V6,      "class_desc_v6.csv",      "class descriptions (v6)"),
    ]:
        try:
            text = _get_cached_or_download(url, cache, desc, session)
            reader = csv.reader(io.StringIO(text))
            for row in reader:
                if len(row) >= 2:
                    mid, name = row[0].strip(), row[1].strip()
                    label_map[name.lower()] = mid
        except Exception as exc:
            print(f"  WARNING: could not fetch {desc}: {exc}", file=sys.stderr)

    return label_map


def fuzzy_find_mid(category_name: str, label_map: dict[str, str]) -> str | None:
    """
    Try exact match first, then substring match, then token overlap.
    Returns the MID string (e.g. '/m/01mzpv') or None.
    """
    key = category_name.lower().strip()

    # 1. Exact
    if key in label_map:
        return label_map[key]

    # 2. Substring (label_map key contains our query or vice-versa)
    for k, mid in label_map.items():
        if key in k or k in key:
            return mid

    # 3. Token overlap ≥ 0.5
    tokens = set(key.split())
    best_score, best_mid = 0.0, None
    for k, mid in label_map.items():
        k_tokens = set(k.split())
        overlap = len(tokens & k_tokens) / max(len(tokens | k_tokens), 1)
        if overlap > best_score:
            best_score, best_mid = overlap, mid
    if best_score >= 0.5:
        return best_mid

    return None


# ---------------------------------------------------------------------------
# Step 2 – Build ImageID → URL map (from train image list)
# ---------------------------------------------------------------------------


def build_image_url_map(session: requests.Session) -> dict[str, str]:
    """Returns {image_id: original_url} for all train images."""
    text = _get_cached_or_download(
        URL_TRAIN_IMAGES, "train_images.csv", "train image list", session
    )
    url_map: dict[str, str] = {}
    reader = csv.DictReader(io.StringIO(text))
    for row in reader:
        image_id = row.get("ImageID", "").strip()
        # The CSV has 'OriginalURL' column
        original_url = row.get("OriginalURL", row.get("url", "")).strip()
        if image_id and original_url:
            url_map[image_id] = original_url
    print(f"  Loaded {len(url_map):,} train image URLs", flush=True)
    return url_map


# ---------------------------------------------------------------------------
# Step 3 – Get ImageIDs for a given LabelName from the labels CSV
# ---------------------------------------------------------------------------


def get_image_ids_for_label(
    mid: str,
    max_count: int,
    session: requests.Session,
) -> list[str]:
    """
    Stream the large train-annotations CSV and collect up to max_count
    ImageIDs where LabelName == mid and Confidence == 1.
    """
    cache_name = f"labels_{mid.replace('/', '_')}.txt"
    cache_p = _cache_path(cache_name)

    if cache_p.exists():
        ids = cache_p.read_text().splitlines()
        print(f"  Loaded {len(ids)} cached IDs for {mid}", flush=True)
        return ids[:max_count]

    print(f"  Streaming label annotations for {mid} ...", flush=True)
    collected: list[str] = []

    try:
        r = session.get(URL_TRAIN_LABELS, stream=True, timeout=120)
        r.raise_for_status()

        buffer = ""
        header_parsed = False
        col_image_id = col_label = col_confidence = None

        for raw_chunk in r.iter_content(chunk_size=1 << 20):
            buffer += raw_chunk.decode("utf-8", errors="replace")
            lines = buffer.split("\n")
            buffer = lines[-1]  # keep incomplete last line

            for line in lines[:-1]:
                if not header_parsed:
                    cols = [c.strip() for c in line.split(",")]
                    try:
                        col_image_id = cols.index("ImageID")
                        col_label = cols.index("LabelName")
                        col_confidence = cols.index("Confidence")
                    except ValueError:
                        # Try alternative header names
                        col_image_id = 0
                        col_label = 2
                        col_confidence = 3
                    header_parsed = True
                    continue

                parts = line.split(",")
                if len(parts) <= max(col_image_id, col_label, col_confidence):
                    continue
                if (parts[col_label].strip() == mid and
                        parts[col_confidence].strip() == "1"):
                    collected.append(parts[col_image_id].strip())
                    if len(collected) >= max_count:
                        break

            if len(collected) >= max_count:
                break

    except Exception as exc:
        print(f"  WARNING: label streaming failed: {exc}", file=sys.stderr)

    # Cache results so re-runs skip the big download
    cache_p.write_text("\n".join(collected))
    print(f"  Found {len(collected)} images for {mid}", flush=True)
    return collected[:max_count]


# ---------------------------------------------------------------------------
# Step 4 – Download a single image
# ---------------------------------------------------------------------------


def _download_image(
    args: tuple[str, str, Path, str],
) -> tuple[str, bool, str]:
    """
    Worker function for ThreadPoolExecutor.
    args = (image_id, url, dest_path, category)
    Returns (image_id, success, error_msg).
    """
    image_id, url, dest_path, category = args

    if dest_path.exists():
        return image_id, True, "already exists"

    session = _session()
    for attempt in range(MAX_RETRIES + 1):
        try:
            r = session.get(url, timeout=SESSION_TIMEOUT)
            if r.status_code == 404:
                return image_id, False, "404"
            r.raise_for_status()

            # Validate minimal image size (avoid corrupt/tiny files)
            if len(r.content) < 1024:
                return image_id, False, "too small"

            dest_path.parent.mkdir(parents=True, exist_ok=True)

            # Quick PIL validation before writing
            try:
                from PIL import Image as PilImage
                import io as _io
                img = PilImage.open(_io.BytesIO(r.content))
                img.verify()
            except Exception:
                return image_id, False, "invalid image"

            dest_path.write_bytes(r.content)
            return image_id, True, ""

        except requests.exceptions.Timeout:
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)
                continue
            return image_id, False, "timeout"
        except Exception as exc:
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)
                continue
            return image_id, False, str(exc)

    return image_id, False, "max retries exceeded"


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------


def download_category(
    category_name: str,
    category_slug: str,
    mid: str,
    url_map: dict[str, str],
    max_per_class: int,
    workers: int,
    session: requests.Session,
) -> list[tuple[str, str, str]]:
    """
    Download images for one category.
    Returns list of (filepath, category_slug, image_id) manifest rows.
    """
    print(f"\n[{category_name}] MID={mid}", flush=True)
    image_ids = get_image_ids_for_label(mid, max_per_class, session)

    if not image_ids:
        print(f"  No images found for {category_name}", file=sys.stderr)
        return []

    # Build work list
    cat_dir = DATA_ROOT / category_slug
    cat_dir.mkdir(parents=True, exist_ok=True)

    tasks: list[tuple[str, str, Path, str]] = []
    for i, img_id in enumerate(image_ids):
        url = url_map.get(img_id)
        if not url:
            continue
        dest = cat_dir / f"image_{i:04d}.jpg"
        tasks.append((img_id, url, dest, category_slug))

    if not tasks:
        print(f"  No URLs matched for {category_name}", file=sys.stderr)
        return []

    print(f"  Queuing {len(tasks)} downloads ...", flush=True)

    manifest_rows: list[tuple[str, str, str]] = []
    failed = 0

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_download_image, t): t for t in tasks}
        with tqdm(total=len(futures), desc=category_name, unit="img") as bar:
            for fut in as_completed(futures):
                img_id, ok, msg = fut.result()
                bar.update(1)
                task = futures[fut]
                dest_path = task[2]
                if ok:
                    manifest_rows.append((str(dest_path), category_slug, img_id))
                else:
                    failed += 1
                    bar.set_postfix(failed=failed)

    print(
        f"  {len(manifest_rows)} downloaded, {failed} failed for {category_name}",
        flush=True,
    )
    return manifest_rows


def write_manifest(all_rows: list[tuple[str, str, str]]) -> None:
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(MANIFEST_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["filepath", "category", "open_images_id"])
        writer.writerows(all_rows)
    print(f"\nManifest saved: {MANIFEST_PATH} ({len(all_rows)} entries)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Download Open Images for CLIP fine-tuning")
    parser.add_argument("--max_per_class", type=int, default=DEFAULT_MAX_PER_CLASS,
                        help=f"Max images per category (default {DEFAULT_MAX_PER_CLASS})")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS,
                        help=f"Parallel download threads (default {DEFAULT_WORKERS})")
    parser.add_argument("--categories", nargs="*",
                        help="Subset of category names to download (default: all)")
    args = parser.parse_args()

    session = _session()

    print("=" * 60)
    print("Open Images V7 Downloader — CC BY 4.0 dataset")
    print("=" * 60)

    # Step 1: build label map
    print("\nStep 1: Building label map ...")
    label_map = build_label_map(session)
    print(f"  {len(label_map):,} classes loaded")

    # Step 2: build URL map
    print("\nStep 2: Loading train image URLs ...")
    url_map = build_image_url_map(session)

    # Resolve MIDs for each category
    print("\nStep 3: Resolving category MIDs ...")
    resolved: list[tuple[str, str, str]] = []
    for cat_name, cat_slug in CATEGORIES.items():
        if args.categories and cat_name not in args.categories:
            continue
        mid = fuzzy_find_mid(cat_name, label_map)
        if mid:
            print(f"  {cat_name:25s} → {mid}")
            resolved.append((cat_name, cat_slug, mid))
        else:
            print(f"  {cat_name:25s} → NOT FOUND (skipping)", file=sys.stderr)

    if not resolved:
        print("ERROR: no categories resolved — check network or class CSV", file=sys.stderr)
        sys.exit(1)

    # Step 4: download
    print(f"\nStep 4: Downloading (max {args.max_per_class} per class, {args.workers} workers) ...")
    DATA_ROOT.mkdir(parents=True, exist_ok=True)

    all_manifest_rows: list[tuple[str, str, str]] = []
    summary: dict[str, int] = {}

    for cat_name, cat_slug, mid in resolved:
        rows = download_category(
            cat_name, cat_slug, mid, url_map,
            args.max_per_class, args.workers, session,
        )
        all_manifest_rows.extend(rows)
        summary[cat_name] = len(rows)

    # Write manifest
    write_manifest(all_manifest_rows)

    # Summary
    print("\n" + "=" * 60)
    print("DOWNLOAD SUMMARY")
    print("=" * 60)
    total = 0
    for cat_name, count in summary.items():
        print(f"  {cat_name:25s}: {count:5d} images")
        total += count
    print(f"  {'TOTAL':25s}: {total:5d} images")
    print(f"\nImages saved to: {DATA_ROOT}")
    print(f"Manifest:        {MANIFEST_PATH}")


if __name__ == "__main__":
    main()
