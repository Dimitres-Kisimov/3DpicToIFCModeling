"""
fetch_images.py — source 10 unique free-licensed photos per category (17x10 = 170)
for the TripoSR A/B benchmark. NOT from the ABO catalog — real internet photos.

Primary source: Wikimedia Commons API (free-licensed by definition).
Backup: Openverse API (CC-licensed aggregator) for sparse categories.

Saves benchmark/images/<category>/list01.jpg ... list10.jpg
and benchmark/images/sources.json  (per image: url, page, license hint, fetched_at).

    python fetch_images.py [--only-list 1] [--category desk]
"""
from __future__ import annotations
import os, sys, json, time, argparse
from datetime import datetime
from pathlib import Path
import requests

HERE = Path(__file__).resolve().parent
IMG_DIR = HERE / "images"
UA = {"User-Agent": "SCS-3D-benchmark/1.0 (research; contact: dev@localhost)"}

# The 17 picker categories -> search terms tuned for single-object photos
CATEGORIES = {
    "bookshelf":      ["bookshelf furniture", "bookcase wooden"],
    "cabinet":        ["cabinet furniture", "sideboard furniture"],
    "clock":          ["wall clock", "table clock"],
    "coffee_table":   ["coffee table furniture", "low table living room"],
    "desk":           ["office desk furniture", "writing desk"],
    "filing_cabinet": ["filing cabinet", "file cabinet office"],
    "lamp":           ["floor lamp", "desk lamp"],
    "laptop":         ["laptop computer open", "notebook computer"],
    "mirror":         ["wall mirror frame", "standing mirror furniture"],
    "monitor":        ["computer monitor", "LCD monitor"],
    "office_chair":   ["office chair", "swivel chair"],
    "picture_frame":  ["picture frame wall", "photo frame"],
    "planter":        ["flower pot plant", "potted plant planter"],
    "side_table":     ["side table furniture", "end table furniture"],
    "sofa":           ["sofa furniture", "couch furniture"],
    "stool":          ["stool furniture wooden", "bar stool"],
    "table":          ["dining table furniture", "wooden table"],
}
# SCS_BENCH_N lets a sweep extend the lists (e.g. =11 adds one fresh photo per
# category as list11 for the all-AI grand comparison) without renaming anything.
N_PER_CAT = int(os.environ.get("SCS_BENCH_N", 10))

# extra terms tried only when the primary terms leave a category short
SPARE_TERMS = {
    "clock": ["alarm clock", "mantel clock", "kitchen clock wall", "railway station clock"],
    "picture_frame": ["gilded picture frame", "empty picture frame", "wooden photo frame", "baroque frame"],
    "filing_cabinet": ["office drawer cabinet", "steel filing cabinet drawers"],
    "planter": ["terracotta flower pot", "garden planter pot", "ceramic plant pot"],
    "mirror": ["antique mirror", "bathroom mirror", "dressing mirror"],
    "monitor": ["desktop computer screen", "flat screen monitor"],
    "laptop": ["open laptop on desk", "notebook pc"],
    "side_table": ["nightstand", "bedside table"],
    "stool": ["kitchen stool", "three legged stool", "wooden milking stool"],
    "coffee_table": ["glass coffee table", "round coffee table"],
    "office_chair": ["ergonomic office chair", "desk chair wheels"],
    "desk": ["computer desk", "school desk", "bureau desk"],
    "lamp": ["standard lamp", "table lamp shade", "reading lamp"],
    "sofa": ["leather sofa", "two seat couch", "loveseat"],
    "table": ["kitchen table", "round dining table", "wooden table four legs"],
    "cabinet": ["display cabinet", "kitchen cabinet unit", "antique cabinet"],
    "bookshelf": ["wooden bookcase", "open shelving unit books"],
}


def commons_search(term, limit=40):
    """Wikimedia Commons file search -> [(direct_url, page_url, w, h, mime)]."""
    r = requests.get("https://commons.wikimedia.org/w/api.php", headers=UA, timeout=30, params={
        "action": "query", "format": "json", "generator": "search",
        "gsrsearch": f'filetype:bitmap {term}', "gsrnamespace": 6, "gsrlimit": limit,
        # iiurlwidth -> thumburl: Wikimedia 429s bulk full-res downloads; 1024 px
        # thumbnails are cache-served, allowed, and plenty for TripoSR input.
        "prop": "imageinfo", "iiprop": "url|size|mime", "iiurlwidth": 1024,
    })
    r.raise_for_status()
    pages = (r.json().get("query") or {}).get("pages") or {}
    out = []
    for p in pages.values():
        for ii in p.get("imageinfo", []):
            out.append((ii.get("thumburl") or ii.get("url"), ii.get("descriptionurl"),
                        ii.get("width", 0), ii.get("height", 0), ii.get("mime", "")))
    return out


def commons_category(cat_title, limit=100):
    """Files in a curated Commons category — much cleaner than search for sparse
    object types. Returns the same tuple shape as commons_search."""
    r = requests.get("https://commons.wikimedia.org/w/api.php", headers=UA, timeout=30, params={
        "action": "query", "format": "json", "generator": "categorymembers",
        "gcmtitle": cat_title, "gcmtype": "file", "gcmlimit": limit,
        "prop": "imageinfo", "iiprop": "url|size|mime", "iiurlwidth": 1024,
    })
    r.raise_for_status()
    pages = (r.json().get("query") or {}).get("pages") or {}
    out = []
    for p in pages.values():
        for ii in p.get("imageinfo", []):
            out.append((ii.get("thumburl") or ii.get("url"), ii.get("descriptionurl"),
                        ii.get("width", 0), ii.get("height", 0), ii.get("mime", "")))
    return out


# curated Commons categories — cleaner candidates for the sparse object types
COMMONS_CATEGORIES = {
    "clock": ["Category:Wall clocks", "Category:Alarm clocks", "Category:Mantel clocks"],
    "picture_frame": ["Category:Picture frames", "Category:Empty picture frames"],
    "coffee_table": ["Category:Coffee tables"],
    "bookshelf": ["Category:Bookcases"],
    "stool": ["Category:Stools"],
    "side_table": ["Category:Side tables", "Category:Nightstands"],
    "filing_cabinet": ["Category:Filing cabinets"],
    "planter": ["Category:Flowerpots"],
    "mirror": ["Category:Mirrors"],
    "sofa": ["Category:Couches"],
    "lamp": ["Category:Floor lamps", "Category:Table lamps"],
    "desk": ["Category:Desks"],
    "table": ["Category:Tables (furniture)"],
    "cabinet": ["Category:Cabinets (furniture)"],
    "office_chair": ["Category:Office chairs"],
    "monitor": ["Category:Computer monitors"],
    "laptop": ["Category:Laptop computers"],
}


def openverse_search(term, limit=40):
    """Openverse CC image search -> same tuple shape."""
    r = requests.get("https://api.openverse.org/v1/images/", headers=UA, timeout=30, params={
        "q": term, "page_size": limit, "license_type": "all-cc",
    })
    r.raise_for_status()
    out = []
    for res in r.json().get("results", []):
        out.append((res.get("url"), res.get("foreign_landing_url"),
                    res.get("width") or 0, res.get("height") or 0, res.get("filetype") or ""))
    return out


def usable(url, w, h, mime):
    if not url:
        return False
    low = url.lower().split("?")[0]
    bad = (".svg", ".gif", ".tif", ".tiff", ".webp", ".pdf", ".ogg", ".mp4")
    if low.endswith(bad) or any(b.strip(".") in str(mime).lower() for b in (".svg", ".gif", ".tiff")):
        return False                          # PIL verify() at download is the real gate
    if w and (w < 480 or w > 6000):
        return False
    if w and h and not (0.4 <= w / max(h, 1) <= 2.6):
        return False
    return True


def download(url, dest):
    r = requests.get(url, headers=UA, timeout=60)
    if r.status_code == 429:                  # throttled — one slow retry, then give up
        time.sleep(20)
        r = requests.get(url, headers=UA, timeout=60)
    r.raise_for_status()
    if len(r.content) < 15_000:               # icons / stubs
        raise ValueError("too small")
    dest.write_bytes(r.content)
    # sanity: PIL can open it and it is big enough
    from PIL import Image
    im = Image.open(dest); im.verify()
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--category", default=None)
    args = ap.parse_args()

    sources_path = IMG_DIR / "sources.json"
    sources = json.loads(sources_path.read_text(encoding="utf-8")) if sources_path.exists() else {}
    cats = [args.category] if args.category else list(CATEGORIES)

    for cat in cats:
        cdir = IMG_DIR / cat
        cdir.mkdir(parents=True, exist_ok=True)
        have = sorted(cdir.glob("list*.jpg")) + sorted(cdir.glob("list*.png"))
        if len(have) >= N_PER_CAT:
            print(f"[{cat}] already have {len(have)}")
            continue
        # never reuse a photo that an earlier list already used
        candidates = []
        seen = {v.get("url") for v in sources.values() if v.get("url")}
        # Openverse FIRST: its images live on third-party hosts, while Wikimedia
        # rate-penalizes bulk downloads from upload.wikimedia.org (observed 429s).
        for term in CATEGORIES[cat]:
            try:
                candidates += openverse_search(term)
            except Exception as e:
                print(f"[{cat}] openverse '{term}' failed: {e}", flush=True)
            time.sleep(1.2)
        for term in CATEGORIES[cat] + SPARE_TERMS.get(cat, []):
            try:
                candidates += commons_search(term)
            except Exception as e:
                print(f"[{cat}] commons '{term}' failed: {e}", flush=True)
            time.sleep(1.2)
        got = len(have)
        for url, page, w, h, mime in candidates:
            if got >= N_PER_CAT:
                break
            if url in seen or not usable(url, w, h, mime):
                continue
            seen.add(url)
            ext = ".png" if ".png" in url.lower() else ".jpg"
            dest = cdir / f"list{got + 1:02d}{ext}"
            try:
                download(url, dest)
                time.sleep(0.8)                      # stay polite — Wikimedia 429s bursts
            except Exception:
                time.sleep(0.8)
                continue
            sources[f"{cat}/{dest.name}"] = {
                "url": url, "page": page,
                "source": "wikimedia_commons" if "wikimedia" in url else "openverse",
                "fetched_at": datetime.now().isoformat(timespec="seconds"),
            }
            got += 1
            print(f"[{cat}] {dest.name} <- {url[:90]}")
        print(f"[{cat}] total {got}/{N_PER_CAT}")
        sources_path.parent.mkdir(parents=True, exist_ok=True)
        sources_path.write_text(json.dumps(sources, indent=1), encoding="utf-8")
    print("done")


if __name__ == "__main__":
    main()
