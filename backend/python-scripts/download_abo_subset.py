"""
Download a curated subset of Amazon Berkeley Objects (ABO) for SCS retrieval.

ABO is CC-BY-4.0 — fully commercial-safe, attribution required.

Pipeline:
  1. Fetch abo-listings.tar (about 80 MB) — product metadata
  2. Parse each listings_*.json.gz, filter to SCS-relevant office categories
  3. Pick the entries that have a `3dmodel_id` (i.e., an actual 3D mesh)
  4. Download per-product GLBs from the ABO public S3 bucket
  5. Drop GLBs into data/mesh_library_abo/ with a fresh manifest.json

This is intentionally a separate folder from data/mesh_library/ (the procedural
library) so the two coexist while testing.  build_mesh_library_abo.py picks it
up and rebuilds the FAISS index.
"""
from __future__ import annotations

import gzip
import io
import json
import os
import sys
import tarfile
import time
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = REPO_ROOT / "data" / "mesh_library_abo"
OUT_DIR.mkdir(parents=True, exist_ok=True)

LISTINGS_URL = "https://amazon-berkeley-objects.s3.amazonaws.com/archives/abo-listings.tar"
SPINS_URL    = "https://amazon-berkeley-objects.s3.amazonaws.com/archives/abo-spins.tar"
MODELS_BASE  = "https://amazon-berkeley-objects.s3.amazonaws.com/3dmodels/original"

# ABO product_type values mapped to SCS canonical categories.
# Coverage chosen so every entry contributes to one of the 11 SCS categories.
SCS_CATEGORY_MAP = {
    "CHAIR":           "office_chair",
    "OFFICE_CHAIR":    "office_chair",
    "DINING_CHAIR":    "office_chair",
    "RECLINER":        "office_chair",
    "SOFA":            "sofa",
    "SECTIONAL_SOFA":  "sofa",
    "LOVESEAT":        "sofa",
    "BENCH":           "sofa",
    "TABLE":           "table",
    "DINING_TABLE":    "table",
    "COFFEE_TABLE":    "table",
    "END_TABLE":       "table",
    "CONSOLE_TABLE":   "table",
    "DESK":            "table",  # treat as desk-like
    "OUTDOOR_TABLE":   "table",
    "CABINET":         "appliance",
    "STORAGE_CABINET": "appliance",
    "DRESSER":         "appliance",
    "WARDROBE":        "appliance",
    "BOOKCASE":        "appliance",
    "SHELF":           "appliance",
    "STORAGE_RACK":    "appliance",
    "LAMP":            "plant",  # floor-standing object slot
    "TABLE_LAMP":      "plant",
    "FLOOR_LAMP":      "plant",
    "PENDANT_LIGHT":   "plant",
    "TV":              "monitor",
    "COMPUTER_MONITOR": "monitor",
}


def log(msg, level="info"):
    print(f"[{level.upper():4s}] {msg}", flush=True)


def http_stream_download(url: str, dest: Path, expected_mb_hint: int = None):
    """Stream a URL to a file with progress every ~5 MB."""
    log(f"GET {url}")
    if dest.exists():
        log(f"  already on disk ({dest.stat().st_size // (1024*1024)} MB), skip")
        return
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "SCS-ABO-fetch/1.0"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        total = int(resp.headers.get("Content-Length") or 0)
        if total:
            log(f"  size: {total // (1024*1024)} MB")
        wrote = 0
        last_print = 0
        with open(tmp, "wb") as fh:
            while True:
                chunk = resp.read(1024 * 1024)
                if not chunk:
                    break
                fh.write(chunk)
                wrote += len(chunk)
                if wrote - last_print > 5 * 1024 * 1024:
                    last_print = wrote
                    if total:
                        pct = 100 * wrote / total
                        log(f"  {wrote // (1024*1024):4d} / {total // (1024*1024):4d} MB ({pct:5.1f}%)")
                    else:
                        log(f"  {wrote // (1024*1024):4d} MB")
    tmp.rename(dest)
    log(f"  saved {dest}")


def extract_listings(listings_tar: Path, work_dir: Path) -> list[Path]:
    log(f"Extracting listings_*.json.gz from {listings_tar.name}")
    work_dir.mkdir(parents=True, exist_ok=True)
    out_files = []
    with tarfile.open(listings_tar, "r") as tf:
        for m in tf.getmembers():
            if m.name.endswith(".json.gz") and "metadata" in m.name:
                tf.extract(m, path=str(work_dir))
                out_files.append(work_dir / m.name)
    log(f"  extracted {len(out_files)} listings shard(s)")
    return out_files


def parse_listings(shard_paths: list[Path]) -> dict[str, list[dict]]:
    """Return dict mapping category -> list of {item_id, product_type, dimensions, 3dmodel_id}."""
    by_cat: dict[str, list[dict]] = {}
    skipped = 0
    no_3d = 0
    for shard in shard_paths:
        log(f"Parsing {shard.name}")
        with gzip.open(shard, "rt", encoding="utf-8") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                except Exception:
                    skipped += 1
                    continue
                ptype = rec.get("product_type", [])
                if isinstance(ptype, list) and ptype:
                    ptype_val = ptype[0].get("value") if isinstance(ptype[0], dict) else str(ptype[0])
                elif isinstance(ptype, dict):
                    ptype_val = ptype.get("value")
                else:
                    ptype_val = str(ptype)
                ptype_val = (ptype_val or "").upper()
                if ptype_val not in SCS_CATEGORY_MAP:
                    continue
                model_id = rec.get("3dmodel_id")
                if not model_id:
                    # try fallback fields some listings use
                    model_id = rec.get("3dmodel") or rec.get("three_d_model_id")
                if not model_id:
                    no_3d += 1
                    continue
                cat = SCS_CATEGORY_MAP[ptype_val]
                # Dimensions (cm) — convert to m if present
                dims = {}
                for k in ("item_height", "item_width", "item_depth", "item_length"):
                    val = rec.get(k)
                    if isinstance(val, dict) and "normalized_value" in val:
                        nv = val["normalized_value"]
                        v = nv.get("value")
                        u = nv.get("unit") or ""
                        if isinstance(v, (int, float)):
                            if u.lower() in ("centimeters", "centimetres", "cm"):
                                v = v / 100.0
                            elif u.lower() in ("inches",):
                                v = v * 0.0254
                            dims[k] = float(v)
                by_cat.setdefault(cat, []).append({
                    "item_id": rec.get("item_id") or model_id,
                    "model_id": model_id,
                    "product_type": ptype_val,
                    "dimensions_m": dims,
                })
    if skipped:
        log(f"  skipped {skipped} malformed lines", "warn")
    log(f"  {no_3d} matching products had no 3dmodel — skipped those")
    return by_cat


BUCKET_BASE = "https://amazon-berkeley-objects.s3.amazonaws.com"


def list_all_3dmodel_keys() -> dict[str, tuple[str, int]]:
    """List the entire 3dmodels/original/ prefix and return id -> (S3 key, size_bytes)."""
    import xml.etree.ElementTree as ET
    out: dict[str, tuple[str, int]] = {}
    token = None
    page = 0
    NS = {"s3": "http://s3.amazonaws.com/doc/2006-03-01/"}
    while True:
        page += 1
        qs = "list-type=2&prefix=3dmodels/original/&max-keys=1000"
        if token:
            qs += f"&continuation-token={urllib.parse.quote(token)}"
        url = f"{BUCKET_BASE}/?{qs}"
        req = urllib.request.Request(url, headers={"User-Agent": "SCS-ABO-fetch/1.0"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read()
        root = ET.fromstring(data)
        for c in root.findall("s3:Contents", NS):
            key = c.findtext("s3:Key", default="", namespaces=NS)
            size = int(c.findtext("s3:Size", default="0", namespaces=NS))
            if key.endswith(".glb"):
                mid = Path(key).stem
                out[mid] = (key, size)
        is_trunc = root.findtext("s3:IsTruncated", default="false", namespaces=NS).lower() == "true"
        token = root.findtext("s3:NextContinuationToken", default="", namespaces=NS) or None
        log(f"  page {page}: {len(out)} keys total, truncated={is_trunc}")
        if not is_trunc:
            break
    return out


def download_glbs(by_cat: dict[str, list[dict]], per_cat_limit: int,
                   max_size_mb: int = 25) -> list[dict]:
    """Download up to `per_cat_limit` GLBs per SCS category, skipping any > max_size_mb."""
    import urllib.parse
    log("Listing every 3dmodels/original/ key once (one-time cost)…")
    id_to_key = list_all_3dmodel_keys()
    log(f"  total ABO GLBs available: {len(id_to_key)}")

    manifest = []
    for cat, items in by_cat.items():
        log(f"--- {cat}: {len(items)} candidates ---")
        picked = 0
        # Sort candidates: prefer those with smaller files (faster, lighter for retrieval)
        with_keys = []
        for item in items:
            mid = item["model_id"]
            if mid in id_to_key:
                key, size = id_to_key[mid]
                size_mb = size / (1024 * 1024)
                if size_mb <= max_size_mb:
                    with_keys.append((item, key, size_mb))
        with_keys.sort(key=lambda t: t[2])  # smallest first
        log(f"  {len(with_keys)} have available GLB <= {max_size_mb} MB")
        for item, key, size_mb in with_keys:
            if picked >= per_cat_limit:
                break
            mid = item["model_id"]
            url = f"{BUCKET_BASE}/{key}"
            dest = OUT_DIR / f"{cat}_{mid}.glb"
            try:
                http_stream_download(url, dest)
                manifest.append({
                    "id": f"{cat}_{mid}",
                    "category": cat,
                    "glb": dest.name,
                    "source_id": mid,
                    "product_type": item["product_type"],
                    "dimensions_m": item["dimensions_m"],
                    "glb_size_mb": round(size_mb, 1),
                    "license": "CC-BY-4.0",
                    "source": "Amazon Berkeley Objects (ABO)",
                    "attribution": "https://amazon-berkeley-objects.s3.amazonaws.com/index.html",
                })
                picked += 1
            except Exception as e:
                log(f"  download error for {mid}: {e}", "warn")
                continue
        log(f"  {picked} GLBs saved for {cat}")
    return manifest


# urllib.parse used by list_all_3dmodel_keys for token escaping
import urllib.parse  # noqa: E402


def main():
    work = OUT_DIR / "_listings_work"
    work.mkdir(parents=True, exist_ok=True)
    listings_tar = work / "abo-listings.tar"

    log("== Step 1: fetch listings metadata ==")
    http_stream_download(LISTINGS_URL, listings_tar)

    log("== Step 2: extract listings shards ==")
    shards = extract_listings(listings_tar, work)

    log("== Step 3: parse and filter by category ==")
    by_cat = parse_listings(shards)
    for cat, items in sorted(by_cat.items()):
        log(f"  {cat:14s}  {len(items):5d} candidate listings")

    log("== Step 4: download GLBs (per-category cap) ==")
    per_cat_limit = int(os.environ.get("ABO_PER_CAT", "40"))
    log(f"  per-category limit: {per_cat_limit}")
    manifest = download_glbs(by_cat, per_cat_limit)

    log(f"== Step 5: write manifest ({len(manifest)} entries) ==")
    (OUT_DIR / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    log(f"  manifest: {OUT_DIR / 'manifest.json'}")

    # Counts per category
    from collections import Counter
    cnt = Counter(m["category"] for m in manifest)
    log("== Done. Category counts ==")
    for cat, n in sorted(cnt.items()):
        log(f"  {cat:14s}  {n} meshes")
    log(f"Total: {len(manifest)} meshes in {OUT_DIR}")


if __name__ == "__main__":
    main()
