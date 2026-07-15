# Procurement methodology — how the search is satisfied and the price proven

*(v4 · Dimitres Kisimov · the in-app tool is 🛒 /procurement.html; the live study
is /procurement_study.html)*

## The question

Given an item our AI engines generated (e.g. the TRELLIS bed, the TRELLIS chair,
the TripoSG stool), find the **cheapest real product that is visually very
similar and of acceptable quality**, delivered to **Bildungscampus, 74076
Heilbronn**, with cost tiers the financial department can plan with.

## Why this design (the "smartest most efficient way")

A raw crawler of "the whole internet" cannot *prove* a cheapest price: search
engines and most shops block automated crawlers, coverage would be unknowable,
and the claim would be unverifiable. The provable formulation is:

> **"cheapest among the companies scanned"** — with the company list printed on
> every report.

So the system is built as a **shop registry with per-company adapters**, and the
report is honest about which rows produced candidates.

## Pipeline (6 stages)

1. **Views** — the item's rendered views (thumbnail + preview) are embedded with
   **CLIP ViT-B/32** locally (RTX 4050 or CPU; the model downloads once, ~600 MB).
2. **Query building** — the item category maps to a German retail term
   (bed→"bett", stool→"hocker"…), and CLIP zero-shot attribute matching picks a
   material/colour modifier (wood / black metal / white / upholstered / leather),
   e.g. `hocker holz`.
3. **Multi-company sweep** — the registry today:

   | company | how | status |
   |---|---|---|
   | IKEA Deutschland | public search JSON (prices, images, ratings) | live, keyless |
   | OTTO | headless-Chrome rendered DOM + generic tile extractor | live, keyless |
   | POCO Einrichtungsmärkte | headless-Chrome rendered DOM | live, keyless |
   | home24 | rendered DOM | registered; currently bot-walled |
   | Möbel Boss | rendered DOM | registered; prices load post-render |
   | Kaiserkraft (B2B) | rendered DOM | registered; B2B prices gated |
   | eBay.de | official Browse API — **exact shipping to 74076** | plug-in: free API key |
   | Google Shopping (SerpAPI) | **hundreds of shops at once** | plug-in: API key |

   The generic tile extractor pairs every € price in the rendered DOM with the
   nearest product link and image — recall over precision, because stage 4
   filters visually. Fetches are cached 24 h and rate-limited (1.5 s gap);
   headless Chrome renders JavaScript shops exactly as a customer sees them.
4. **Visual match + quality gate** — every candidate's product photo is
   CLIP-scored (cosine) against our views; candidates under the **0.55
   similarity floor** are dropped as lookalikes. Ratings gate quality where the
   shop provides them (IKEA, Google Shopping); the tie-breaker favours rated
   products. This is why capable engines matter: clean geometry → honest
   renders → reliable matching.
5. **Landed cost to 74076 Heilbronn** — German list prices include 19% VAT.
   Delivery is modelled per shop and per bulk class: parcel rates for small
   items (amortized ~3 units/package for multi-unit orders) vs one
   **Spedition** fee per order for bulky categories (bed, sofa, desk…). eBay's
   API returns the seller's exact shipping. IKEA additionally gets the
   **pickup alternative**: IKEA Ludwigsburg, ~90 km round trip at 0.30 €/km ≈
   27 €. Estimates are flagged; the product link always shows the exact
   checkout figure.
6. **Business tiers** — from the above-floor pool, preferring distinct
   products: **Budget** = lowest landed price · **Standard** = best
   similarity-per-euro · **Premium** = highest similarity × quality. Each tier
   is costed for a single unit and a bulk quantity (default 10). At N ≥ 10 the
   report recommends requesting a written quote — retail bulk discounts are
   not public data and are never invented.

## Honesty limits (printed on every report)

- The claim is **"cheapest among the companies scanned"**, never "cheapest on
  the internet". The scanned list (with candidate counts) is part of the report.
- Shipping figures marked *estimate* use each shop's published standard rates.
- Availability and prices change; every report carries its generation date and
  live product links.
- Performance: one scan = one CLIP load + ~6 page renders + ~30 image
  downloads → 1–3 minutes, one scan at a time, everything cached — no risk to
  the machine.

## Scaling the company list

Two switches multiply coverage without new code: a free **eBay developer key**
(env `EBAY_OAUTH_TOKEN`) adds every eBay.de seller with exact shipping; a
**SerpAPI key** (env `SERPAPI_KEY`) adds Google Shopping — hundreds of German
shops per query. New per-shop adapters are ~20 lines each in
`backend/python-scripts/procurement.py` (SHOPS registry).
