"""
validate_images.py — CLIP-screen the benchmark photos so every image actually
shows the single object it claims (a dark room interior labelled "bookshelf"
produces garbage 3D and proves nothing about the repair).

Pass 1: classify every existing images/<cat>/listNN.* — delete failures AND their
        stale results/list*/<cat> outputs when the image is replaced.
Pass 2: refill each category to 10 with validated candidates (Commons/Openverse),
        re-numbering so list01..list10 stay contiguous.

    python validate_images.py
"""
from __future__ import annotations
import json, time, shutil
from datetime import datetime
from pathlib import Path
from PIL import Image

import fetch_images as F

HERE = Path(__file__).resolve().parent
IMG = HERE / "images"
RES = HERE / "results"

DISPLAY = {"bookshelf": "bookshelf", "cabinet": "cabinet", "clock": "clock",
           "coffee_table": "coffee table", "desk": "desk", "filing_cabinet": "filing cabinet",
           "lamp": "lamp", "laptop": "laptop", "mirror": "mirror", "monitor": "computer monitor",
           "office_chair": "office chair", "picture_frame": "picture frame",
           "planter": "potted plant", "side_table": "side table", "sofa": "sofa",
           "stool": "stool", "table": "table"}
NEGATIVES = ["a room interior", "a building", "a painting or artwork", "a person",
             "a landscape", "text or a document", "other object"]
# categories CLIP confuses with each other — accept these as equivalent evidence
ALIASES = {
    "desk": {"desk", "table"}, "table": {"table", "desk"},
    "coffee_table": {"coffee table", "table", "side table"},
    "side_table": {"side table", "table", "coffee table", "stool"},
    "stool": {"stool", "side table"},
    "cabinet": {"cabinet", "filing cabinet", "bookshelf"},
    "filing_cabinet": {"filing cabinet", "cabinet"},
    "bookshelf": {"bookshelf", "cabinet"},
    "picture_frame": {"picture frame", "mirror", "a painting or artwork"},
    "mirror": {"mirror", "picture frame"},
    "planter": {"potted plant"},
    "monitor": {"computer monitor", "laptop"},
    "laptop": {"laptop", "computer monitor"},
}

_clip = None
def clip():
    global _clip
    if _clip is None:
        from transformers import pipeline
        print("[screen] loading CLIP (CPU)...", flush=True)
        _clip = pipeline("zero-shot-image-classification",
                         model="openai/clip-vit-base-patch32", device=-1)
    return _clip


def image_ok(path, category):
    """True if CLIP reads the photo as this object (aliases allowed) and not as
    a scene/painting/person."""
    labels = sorted(set(DISPLAY.values())) + NEGATIVES
    try:
        res = clip()(Image.open(path).convert("RGB"), candidate_labels=labels)
    except Exception:
        return False, "unreadable"
    top = res[0]["label"]; score = res[0]["score"]
    accept = ALIASES.get(category, {DISPLAY[category]})
    if top in accept and score >= 0.28:
        return True, f"{top} {score:.2f}"
    # second chance: right label ranked 2nd with decent mass and top isn't a hard negative
    second = res[1]["label"] if len(res) > 1 else ""
    if second in accept and res[1]["score"] >= 0.22 and top not in NEGATIVES:
        return True, f"2nd:{second} {res[1]['score']:.2f}"
    return False, f"{top} {score:.2f}"


def purge_results_for(cat, stem):
    """An image was replaced — its generated outputs are stale."""
    n = stem.replace("list", "")
    d = RES / f"list{n}" / cat
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)


def candidates_for(cat, seen):
    """Validated-refill candidate pool: curated Commons categories first (clean
    single-object photos), then term search, then Openverse."""
    out = []
    for title in F.COMMONS_CATEGORIES.get(cat, []):
        try:
            out += F.commons_category(title)
        except Exception:
            pass
        time.sleep(0.8)
    for term in F.CATEGORIES[cat] + F.SPARE_TERMS.get(cat, []):
        try:
            out += F.commons_search(term)
        except Exception:
            pass
        time.sleep(0.8)
    for term in F.CATEGORIES[cat]:
        try:
            out += F.openverse_search(term)
        except Exception:
            pass
        time.sleep(0.8)
    return [c for c in out if c[0] and c[0] not in seen]


def main():
    sources = {}
    sp = IMG / "sources.json"
    if sp.exists():
        sources = json.loads(sp.read_text(encoding="utf-8"))

    for cat in F.CATEGORIES:
        cdir = IMG / cat
        cdir.mkdir(parents=True, exist_ok=True)
        changed = False
        # pass 1 — screen what we have; keep = [(path, source_dict)]
        keep = []
        for p in sorted(cdir.glob("list*.*")) + sorted(cdir.glob("_ok*.*")):
            ok, why = image_ok(p, cat)
            src = sources.pop(f"{cat}/{p.name}", None)
            if ok:
                keep.append((p, src))
            else:
                print(f"[{cat}] DROP {p.name} ({why})", flush=True)
                changed = True
                p.unlink()
        # pass 2 — refill with validated candidates
        need = F.N_PER_CAT - len(keep)
        if need > 0:
            print(f"[{cat}] refilling {need}", flush=True)
            seen = {s.get("url") for s in sources.values() if s} | \
                   {s.get("url") for _, s in keep if s}
            for url, page, w, h, mime in candidates_for(cat, seen):
                if need <= 0:
                    break
                if not F.usable(url, w, h, mime):
                    continue
                seen.add(url)
                tmp = cdir / f"_new{len(keep):02d}.jpg"
                try:
                    F.download(url, tmp)
                except Exception:
                    time.sleep(0.5)
                    continue
                ok, why = image_ok(tmp, cat)
                if not ok:
                    tmp.unlink(missing_ok=True)
                    continue
                keep.append((tmp, {"url": url, "page": page,
                                   "source": "wikimedia_commons" if "wikimedia" in (url or "") else "openverse",
                                   "fetched_at": datetime.now().isoformat(timespec="seconds")}))
                need -= 1
                changed = True
                print(f"[{cat}] ADD ({why}) {url[:80]}", flush=True)
                time.sleep(0.8)
        # renumber SAFELY: two-phase (everything -> __tmp names, then -> final)
        keep = [(p, s) for p, s in keep if p.exists()]
        staged = []
        for i, (p, src) in enumerate(keep, start=1):
            ext = p.suffix if p.suffix in (".jpg", ".png") else ".jpg"
            t = cdir / f"__tmp{i:02d}{ext}"
            p.rename(t)
            staged.append((t, src))
        for i, (t, src) in enumerate(staged, start=1):
            want = cdir / f"list{i:02d}{t.suffix}"
            t.rename(want)
            if src:
                sources[f"{cat}/{want.name}"] = src
        # any change means listNN can show a different photo — old results are stale
        if changed:
            for d in RES.glob(f"list*/{cat}"):
                shutil.rmtree(d, ignore_errors=True)
        print(f"[{cat}] validated {len(staged)}/{F.N_PER_CAT}", flush=True)
        sp.write_text(json.dumps(sources, indent=1), encoding="utf-8")
    print("screening done", flush=True)


if __name__ == "__main__":
    main()
