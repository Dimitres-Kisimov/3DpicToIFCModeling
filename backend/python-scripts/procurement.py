"""procurement.py — v4: from an AI-generated catalog item to the cheapest real,
visually-similar product, landed at Bildungscampus, 74076 Heilbronn.

Pipeline (documented in docs/PROCUREMENT_METHOD.md):
  1. item views (thumb + preview) -> CLIP ViT-B/32 image embeddings (local GPU/CPU)
  2. CLIP zero-shot attributes (wood/metal/white/upholstered...) -> German query
  3. multi-company sweep over the SHOP REGISTRY below — IKEA via its public JSON
     search; the other retailers via headless Chrome (real rendered DOM) with a
     generic tile extractor (anchor + image + € price proximity). Plug-in
     providers (eBay Browse API, SerpAPI Google Shopping = hundreds of shops)
     activate automatically when their env keys are present.
  4. every candidate's product photo is CLIP-scored against our views; a
     similarity floor drops lookalikes; ratings gate quality where available
  5. landed cost: listed price (incl. 19% VAT) + per-shop delivery estimate
     (parcel vs Spedition by category bulk class) for 1 and N units; IKEA also
     gets the pickup alternative (Ludwigsburg, ~90 km round trip)
  6. three business tiers: BUDGET (cheapest above the floor), STANDARD (best
     similarity-per-euro), PREMIUM (highest similarity x quality)

Honesty rule: the report claims "cheapest among the companies scanned" and
lists them — never "cheapest on the internet". Estimates are flagged.

CLI:
  python procurement.py --item bed-TRL-001 --qty 1 10          # one item
  python procurement.py --item bed-TRL-001 --json out.json     # for the API
"""
import argparse
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ASSETS = REPO / "data" / "generated_assets"
CACHE = REPO / "data" / "procurement_cache"
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
      "Accept-Language": "de-DE,de;q=0.9"}
CACHE_TTL_S = 24 * 3600
FETCH_GAP_S = 1.5          # politeness between network hits
SIM_FLOOR = 0.55           # CLIP cosine floor: below this it's not "the same thing"
DEST = "Bildungscampus, 74076 Heilbronn (DE)"
KM_RATE = 0.30             # €/km, German Kilometerpauschale

# ---------------------------------------------------------------------------
# THE COMPANIES COMPARED — the shop registry (keyless rows work out of the box)
# ---------------------------------------------------------------------------
SHOPS = [
    {"id": "ikea", "name": "IKEA Deutschland", "kind": "ikea",
     "ship_parcel": 5.99, "ship_bulky": 39.00, "free_above": None,
     "pickup": {"store": "IKEA Ludwigsburg", "km_roundtrip": 90}},
    {"id": "otto", "name": "OTTO", "kind": "chrome",
     "url": "https://www.otto.de/suche/{q}/",
     "ship_parcel": 5.95, "ship_bulky": 29.95, "free_above": None},
    {"id": "poco", "name": "POCO Einrichtungsmärkte", "kind": "chrome",
     "url": "https://www.poco.de/search?q={q}",
     "ship_parcel": 4.99, "ship_bulky": 29.95, "free_above": None},
    {"id": "home24", "name": "home24", "kind": "chrome",
     "url": "https://www.home24.de/suche/?query={q}",
     "ship_parcel": 5.90, "ship_bulky": 0.00, "free_above": 30.0},
    {"id": "moebelboss", "name": "Möbel Boss", "kind": "chrome",
     "url": "https://www.moebel-boss.de/search?q={q}",
     "ship_parcel": 5.95, "ship_bulky": 49.95, "free_above": None},
    {"id": "kaiserkraft", "name": "Kaiserkraft (B2B)", "kind": "chrome",
     "url": "https://www.kaiserkraft.de/search/?text={q}",
     "ship_parcel": 0.0, "ship_bulky": 0.0, "free_above": 0.0},  # B2B frei Haus
    {"id": "ebay", "name": "eBay.de (API)", "kind": "ebay",
     "env": "EBAY_OAUTH_TOKEN",
     "ship_parcel": 0.0, "ship_bulky": 0.0, "free_above": None},  # API returns real shipping
    {"id": "gshopping", "name": "Google Shopping via SerpAPI (100s of shops)",
     "kind": "serpapi", "env": "SERPAPI_KEY",
     "ship_parcel": 5.95, "ship_bulky": 39.00, "free_above": None},
]

BULKY = {"bed", "sofa", "desk", "table", "cabinet", "bookshelf", "wardrobe",
         "locker", "server_rack", "fridge", "partition", "phone_booth"}
CAT_DE = {"bed": "bett", "chair": "stuhl", "stool": "hocker", "sofa": "sofa",
          "office_chair": "bürostuhl", "desk": "schreibtisch", "table": "esstisch",
          "armchair": "sessel", "bookshelf": "bücherregal", "cabinet": "schrank",
          "side_table": "beistelltisch", "coffee_table": "couchtisch",
          "lamp": "stehlampe", "planter": "pflanzkübel", "mirror": "wandspiegel",
          "coat_rack": "garderobenständer", "waste_bin": "abfalleimer",
          "monitor": "monitor", "printer": "drucker", "microwave": "mikrowelle",
          "fridge": "kühlschrank", "coffee_machine": "kaffeemaschine",
          "whiteboard": "whiteboard", "flipchart": "flipchart",
          "locker": "spind", "filing_cabinet": "aktenschrank"}
# CLIP zero-shot attribute prompts -> German query modifier
ATTRS = [("a photo of wooden furniture", "holz"),
         ("a photo of black metal furniture", "metall schwarz"),
         ("a photo of white furniture", "weiß"),
         ("a photo of upholstered fabric furniture", "polster grau"),
         ("a photo of leather furniture", "leder")]

# category gate: a candidate must SAY it is the thing (title word) — or, when
# the title is uninformative, its photo must CLIP-classify as the thing.
# (Without this, shop sidebars leak fly screens and wallpaper into bed results.)
TITLE_WORDS = {
    "bed": ["bett"], "chair": ["stuhl"], "stool": ["hocker"],
    "office_chair": ["bürostuhl", "drehstuhl", "stuhl"],
    "sofa": ["sofa", "couch"], "desk": ["schreibtisch"],
    "table": ["tisch"], "armchair": ["sessel"],
    "bookshelf": ["regal", "bücherregal"], "cabinet": ["schrank", "kommode"],
    "side_table": ["beistelltisch"], "coffee_table": ["couchtisch"],
    "lamp": ["lampe", "leuchte"], "planter": ["pflanz", "blumenkübel"],
    "mirror": ["spiegel"], "coat_rack": ["garderobe"],
    "waste_bin": ["eimer", "abfall", "mülleimer"], "locker": ["spind"],
    "filing_cabinet": ["aktenschrank", "rollcontainer"],
    "printer": ["drucker"], "monitor": ["monitor"],
    "microwave": ["mikrowelle"], "fridge": ["kühlschrank"],
    "coffee_machine": ["kaffee"], "whiteboard": ["whiteboard", "tafel"],
}
CAT_PROMPTS = {  # CLIP zero-shot category classifier (fallback gate)
    "bed": "a product photo of a bed", "chair": "a product photo of a chair",
    "stool": "a product photo of a stool",
    "office_chair": "a product photo of an office swivel chair",
    "sofa": "a product photo of a sofa", "desk": "a product photo of a desk",
    "table": "a product photo of a dining table",
    "armchair": "a product photo of an armchair",
    "bookshelf": "a product photo of a bookshelf",
    "cabinet": "a product photo of a cabinet",
    "lamp": "a product photo of a floor lamp",
    "mirror": "a product photo of a wall mirror",
    "planter": "a product photo of a plant pot",
}
_OTHER_PROMPTS = ["a product photo of a curtain", "a product photo of wallpaper",
                  "a product photo of a rug", "a product photo of a fly screen",
                  "a product photo of a lamp", "a product photo of a picture frame"]

_clip = None


def clip():
    global _clip
    if _clip is None:
        import torch
        from transformers import CLIPModel, CLIPProcessor
        dev = "cuda" if torch.cuda.is_available() else "cpu"
        m = CLIPModel.from_pretrained("openai/clip-vit-base-patch32").to(dev).eval()
        p = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
        _clip = (m, p, dev, torch)
    return _clip


def _embed_images(pil_images):
    m, p, dev, torch = clip()
    with torch.no_grad():
        inp = p(images=pil_images, return_tensors="pt").to(dev)
        v = m.get_image_features(**inp)
        if not torch.is_tensor(v):        # newer transformers wrap the output
            v = getattr(v, "image_embeds", None) if hasattr(v, "image_embeds") \
                else v.pooler_output
            if v.shape[-1] != m.config.projection_dim:
                v = m.visual_projection(v)
        return v / v.norm(dim=-1, keepdim=True)


def _embed_texts(texts):
    m, p, dev, torch = clip()
    with torch.no_grad():
        inp = p(text=texts, return_tensors="pt", padding=True).to(dev)
        v = m.get_text_features(**inp)
        if not torch.is_tensor(v):
            v = getattr(v, "text_embeds", None) if hasattr(v, "text_embeds") \
                else v.pooler_output
            if v.shape[-1] != m.config.projection_dim:
                v = m.text_projection(v)
        return v / v.norm(dim=-1, keepdim=True)


# ---------------------------------------------------------------------------
# fetch layer: cached + polite; Chrome for JS shops, urllib for JSON/images
# ---------------------------------------------------------------------------
_last_fetch = [0.0]


def _polite():
    dt = time.time() - _last_fetch[0]
    if dt < FETCH_GAP_S:
        time.sleep(FETCH_GAP_S - dt)
    _last_fetch[0] = time.time()


def _cached(key, fetch_fn, suffix):
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / (hashlib.sha1(key.encode()).hexdigest()[:20] + suffix)
    if f.exists() and time.time() - f.stat().st_mtime < CACHE_TTL_S:
        return f.read_bytes()
    _polite()
    data = fetch_fn()
    if data:
        f.write_bytes(data)
    return data


def fetch_url(url, timeout=20):
    def go():
        try:
            return urllib.request.urlopen(
                urllib.request.Request(url, headers=UA), timeout=timeout).read()
        except Exception:
            return b""
    return _cached(url, go, ".bin")


def fetch_chrome(url, budget_ms=12000):
    def go():
        try:
            r = subprocess.run([CHROME, "--headless=new", "--disable-gpu",
                                "--dump-dom", f"--virtual-time-budget={budget_ms}",
                                "--window-size=1400,900", url],
                               capture_output=True, timeout=90)
            return r.stdout
        except Exception:
            return b""
    return _cached("chrome:" + url, go, ".html")


# ---------------------------------------------------------------------------
# providers
# ---------------------------------------------------------------------------
def provider_ikea(shop, query, limit=12):
    u = ("https://sik.search.blue.cdtapps.com/de/de/search-result-page"
         f"?types=PRODUCT&q={urllib.parse.quote(query)}&size={limit}")
    raw = fetch_url(u)
    out = []
    try:
        j = json.loads(raw.decode("utf-8", "ignore"))
        items = (j.get("searchResultPage", {}).get("products", {})
                  .get("main", {}).get("items", []))
        for it in items:
            pr = it.get("product") or {}
            price = ((pr.get("salesPrice") or {}).get("numeral"))
            img = pr.get("mainImageUrl")
            if price is None or not img:
                continue
            out.append({"shop": shop["id"], "shop_name": shop["name"],
                        "title": f"{pr.get('name','')} {pr.get('typeName','')}".strip(),
                        "price": float(price), "url": pr.get("pipUrl"),
                        "image": img,
                        "rating": (pr.get("ratingValue")),
                        "rating_n": pr.get("ratingCount")})
    except Exception:
        pass
    return out


_PRICE = re.compile(r"(\d{1,3}(?:\.\d{3})*,\d\d)\s*€|€\s*(\d{1,3}(?:\.\d{3})*(?:,\d\d)?)")


def _to_eur(m):
    s = (m.group(1) or m.group(2)).replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def provider_chrome_generic(shop, query, limit=12):
    """Generic tile extractor over a real rendered DOM: for every € price,
    associate the nearest preceding product anchor and image. CLIP filters
    the noise downstream, so recall beats precision here."""
    url = shop["url"].format(q=urllib.parse.quote(query))
    h = fetch_chrome(url).decode("utf-8", "ignore")
    if not h:
        return []
    base = "{0.scheme}://{0.netloc}".format(urllib.parse.urlparse(url))
    anchors = [(m.start(), m.group(1)) for m in
               re.finditer(r'<a\b[^>]*href="([^"#]+)"', h)]
    imgs = [(m.start(), m.group(1)) for m in
            re.finditer(r'<img\b[^>]*src="(https?://[^"]+)"', h)]
    out, seen = [], set()
    for pm in _PRICE.finditer(h):
        price = _to_eur(pm)
        if price is None or not (5 <= price <= 5000):
            continue
        pos = pm.start()
        near_a = [(pos - p, u) for p, u in anchors if 0 <= pos - p < 2500]
        near_i = [(abs(pos - p), u) for p, u in imgs if abs(pos - p) < 2500]
        if not near_a or not near_i:
            continue
        href = min(near_a)[1]
        img = min(near_i)[1]
        if href.startswith("/"):
            href = base + href
        if urllib.parse.urlparse(href).netloc not in url:
            continue
        # product-ish paths only (kills nav/footer/service links)
        path = urllib.parse.urlparse(href).path
        if len(path) < 8 or any(k in href.lower() for k in
                                ("hilfe", "service", "login", "warenkorb", "agb",
                                 "kontakt", "filiale", "gutschein", "javascript")):
            continue
        if href in seen:
            continue
        seen.add(href)
        # title: img alt near the price, else slug from the URL
        alt = re.search(r'<img\b[^>]*alt="([^"]{6,120})"[^>]*src="' + re.escape(img[:60]),
                        h)
        title = (alt.group(1) if alt else
                 urllib.parse.unquote(path.strip("/").split("/")[-1])
                 .replace("-", " ").replace("_", " ")[:90])
        out.append({"shop": shop["id"], "shop_name": shop["name"], "title": title,
                    "price": price, "url": href, "image": img,
                    "rating": None, "rating_n": None})
        if len(out) >= limit:
            break
    return out


def provider_ebay(shop, query, limit=12):
    tok = os.environ.get(shop["env"] or "", "")
    if not tok:
        return []
    u = ("https://api.ebay.com/buy/browse/v1/item_summary/search?q="
         + urllib.parse.quote(query) + f"&limit={limit}&filter=deliveryCountry:DE")
    try:
        req = urllib.request.Request(u, headers={
            "Authorization": "Bearer " + tok,
            "X-EBAY-C-MARKETPLACE-ID": "EBAY_DE",
            "X-EBAY-C-ENDUSERCTX": "contextualLocation=country=DE,zip=74076"})
        j = json.loads(urllib.request.urlopen(req, timeout=20).read())
        out = []
        for it in j.get("itemSummaries", []):
            price = float(it["price"]["value"])
            ship = 0.0
            for so in it.get("shippingOptions", []):
                c = so.get("shippingCost", {}).get("value")
                if c is not None:
                    ship = float(c)
                    break
            out.append({"shop": shop["id"], "shop_name": shop["name"],
                        "title": it.get("title", ""), "price": price,
                        "url": it.get("itemWebUrl"),
                        "image": (it.get("image") or {}).get("imageUrl"),
                        "rating": None, "rating_n": None, "ship_exact": ship})
        return out
    except Exception:
        return []


def provider_serpapi(shop, query, limit=12):
    key = os.environ.get(shop["env"] or "", "")
    if not key:
        return []
    u = ("https://serpapi.com/search.json?engine=google_shopping&gl=de&hl=de&q="
         + urllib.parse.quote(query) + "&api_key=" + key)
    try:
        j = json.loads(urllib.request.urlopen(u, timeout=30).read())
        out = []
        for it in j.get("shopping_results", [])[:limit]:
            pr = it.get("extracted_price")
            if pr is None:
                continue
            out.append({"shop": shop["id"],
                        "shop_name": it.get("source") or shop["name"],
                        "title": it.get("title", ""), "price": float(pr),
                        "url": it.get("link"), "image": it.get("thumbnail"),
                        "rating": it.get("rating"), "rating_n": it.get("reviews")})
        return out
    except Exception:
        return []


PROVIDERS = {"ikea": provider_ikea, "chrome": provider_chrome_generic,
             "ebay": provider_ebay, "serpapi": provider_serpapi}


# ---------------------------------------------------------------------------
# scoring + cost model
# ---------------------------------------------------------------------------
def item_views(item_id):
    from PIL import Image
    views = []
    for suffix in (".thumb.png", ".preview.png"):
        p = ASSETS / (item_id + suffix)
        if p.exists():
            views.append(Image.open(p).convert("RGB"))
    if not views:
        raise SystemExit(f"no views for {item_id} (need {item_id}.thumb.png)")
    return views


def pick_attribute(view_embs):
    t = _embed_texts([a[0] for a in ATTRS])
    sims = (view_embs @ t.T).mean(dim=0)
    return ATTRS[int(sims.argmax())][1]


def score_candidates(view_embs, cands, category):
    from PIL import Image
    import io
    words = TITLE_WORDS.get(category, [category.replace("_", " ")])
    cat_prompt = CAT_PROMPTS.get(category,
                                 f"a product photo of a {category.replace('_', ' ')}")
    text_embs = _embed_texts([cat_prompt] + _OTHER_PROMPTS)
    scored = []
    for c in cands:
        if not c.get("image"):
            continue
        title_ok = any(w in (c.get("title") or "").lower() for w in words)
        raw = fetch_url(c["image"], timeout=15)
        if not raw:
            continue
        try:
            img = Image.open(io.BytesIO(raw)).convert("RGB")
        except Exception:
            continue
        e = _embed_images([img])
        if not title_ok:
            # zero-shot check: the photo must classify as OUR category,
            # not as one of the known sidebar leaks
            tsims = (e @ text_embs.T)[0]
            if int(tsims.argmax()) != 0:
                continue
        c["similarity"] = round(float((view_embs @ e.T).max()), 4)
        c["category_check"] = "title" if title_ok else "clip-zero-shot"
        scored.append(c)
    return scored


def landed(c, category, qty):
    """Landed cost to DEST for qty units. German listings include 19% VAT."""
    shop = next(s for s in SHOPS if s["id"] == c["shop"])
    bulky = category in BULKY
    if "ship_exact" in c:                      # eBay API: real per-item shipping
        ship_one = c["ship_exact"]
        ship_n = ship_one * qty
        how = "seller shipping (exact, API)"
    else:
        fee = shop["ship_bulky"] if bulky else shop["ship_parcel"]
        if shop.get("free_above") is not None and c["price"] >= shop["free_above"]:
            fee = 0.0
        if bulky:
            ship_one, ship_n = fee, fee        # one Spedition covers the order
            how = "Spedition estimate (one fee/order)"
        else:
            per_pkg = 3                        # ~3 parcel-size units per package
            ship_one = fee
            ship_n = fee * math.ceil(qty / per_pkg)
            how = f"parcel estimate ({per_pkg}/package)"
    unit = c["price"]
    total = round(unit * qty + ship_n, 2)
    out = {"qty": qty, "unit_price": unit, "shipping": round(ship_n, 2),
           "shipping_basis": how, "landed_total": total,
           "landed_per_unit": round(total / qty, 2)}
    if shop.get("pickup"):
        km = shop["pickup"]["km_roundtrip"]
        out["pickup_alternative"] = {
            "store": shop["pickup"]["store"],
            "cost": round(km * KM_RATE, 2),
            "note": f"{km} km round trip @ {KM_RATE:.2f} €/km, one trip/order"}
    return out


def tiers(scored, category, qtys):
    ok = [c for c in scored if c.get("similarity", 0) >= SIM_FLOOR]
    pool = ok if ok else sorted(scored, key=lambda c: -c.get("similarity", 0))[:5]
    if not pool:
        return {}, pool
    def q(c):                                   # quality proxy
        r = c.get("rating") or 3.5
        return float(r) / 5.0
    # tiers prefer DISTINCT products (fall back to overlap in tiny pools)
    budget = min(pool, key=lambda c: c["price"])
    prem_pool = [c for c in pool if c is not budget] or pool
    premium = max(prem_pool, key=lambda c: c["similarity"] * (0.7 + 0.3 * q(c)))
    std_pool = [c for c in pool if c is not budget and c is not premium] or pool
    standard = max(std_pool, key=lambda c: c["similarity"] / max(30.0, c["price"]))
    out = {}
    for name, c in (("budget", budget), ("standard", standard), ("premium", premium)):
        out[name] = dict(c, costs=[landed(c, category, n) for n in qtys])
    return out, pool


def run(item_id, qtys, limit=12):
    category = re.match(r"([a-z_]+)-", item_id).group(1)
    views = item_views(item_id)
    view_embs = _embed_images(views)
    modifier = pick_attribute(view_embs)
    query = f"{CAT_DE.get(category, category)} {modifier}"
    scanned, skipped, cands = [], [], []
    for shop in SHOPS:
        if shop.get("env") and not os.environ.get(shop["env"], ""):
            skipped.append(shop["name"] + " (no API key)")
            continue
        got = PROVIDERS[shop["kind"]](shop, query, limit)
        scanned.append(f"{shop['name']} ({len(got)} candidates)")
        cands += got
        print(f"  {shop['name']:38s} {len(got)} candidates", flush=True)
    scored = score_candidates(view_embs, cands, category)
    scored.sort(key=lambda c: -c["similarity"])
    tier, pool = tiers(scored, category, qtys)
    return {"item": item_id, "category": category, "query": query,
            "destination": DEST, "vat_note": "listed prices include 19% German VAT",
            "similarity_floor": SIM_FLOOR,
            "companies_scanned": scanned, "companies_skipped": skipped,
            "candidates_total": len(cands), "candidates_scored": len(scored),
            "above_floor": len([c for c in scored
                                if c.get("similarity", 0) >= SIM_FLOOR]),
            "tiers": tier,
            "all_matches": scored[:20],
            "claim": "cheapest among the companies scanned above — not the whole internet",
            "generated_utc": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--item", required=True)
    ap.add_argument("--qty", nargs="*", type=int, default=[1, 10])
    ap.add_argument("--json", default=None)
    a = ap.parse_args()
    r = run(a.item, a.qty)
    if a.json:
        Path(a.json).parent.mkdir(parents=True, exist_ok=True)
        Path(a.json).write_text(json.dumps(r, indent=1, ensure_ascii=False),
                                encoding="utf-8")
    for name, t in r["tiers"].items():
        c1 = t["costs"][0]
        print(f"{name:9s} {t['shop_name']:24s} sim={t['similarity']:.2f} "
              f"{c1['unit_price']:8.2f}€ +ship {c1['shipping']:6.2f}€ "
              f"= {c1['landed_total']:8.2f}€   {t['title'][:44]}")
    print(f"scanned: {len(r['companies_scanned'])} companies, "
          f"{r['candidates_scored']} scored, {r['above_floor']} above floor")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
