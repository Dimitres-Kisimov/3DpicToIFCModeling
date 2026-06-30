# SCS 3DpicToIFCModeling — Production Cost Model

**Purpose:** what it costs to run this once SCS monetizes it, and how to architect it so the recurring bill stays near-zero and is borne by the business, not by any individual.

Two cost types hide in "how much does it cost":

1. **Licence royalties** — fees owed to model/dataset authors when you sell the product.
2. **Infrastructure / compute** — GPU, hosting, storage, bandwidth, LLM calls.

---

## Track A — Commercial-safe / shippable stack

This is the real product. Only MIT/Apache/BSD-grade components.

### A.1 Licence royalties = **$0, forever**

| Component | Licence | Royalty when monetized |
|---|---|---|
| TripoSR / InstantMesh / TRELLIS (3D gen) | MIT / Apache-2.0 / MIT | $0 |
| OR-Tools CP-SAT (layout solver) | Apache-2.0 | $0 |
| IfcOpenShell (IFC export) | LGPL-3.0 (used as library) | $0 |
| xeokit-sdk (browser viewer) | MIT | $0 |
| Depth Anything V2 **Small** | Apache-2.0 | $0 |
| Mistral-7B / Qwen-Apache (brief→constraints LLM, self-hosted) | Apache-2.0 | $0 |

No per-seat, no per-use, no revenue share, no matter SCS's revenue. This is the whole point of the licence posture ([[scs-license-constraints]]).

### A.2 Infrastructure — the only recurring cost

**Unit assumptions** (tune to real data): avg room ≈ 10 furniture items; DINOv2 retrieval over the ABO catalog covers ~70–80% of items, so only **2–3 items/room** need fresh 3D generation; ~30 s GPU per generated item; 1 LLM brief-translation call/room (~3k tokens); solver <1 s CPU/room; output scene XKT ~2 MB/room; catalog meshes stored once (~4–8 GB).

**LLM brief-translation cost per room** (if using a hosted API instead of self-hosting):

| Model | $/1M in | $/1M out | ~Cost/room (3k tok) |
|---|---|---|---|
| Claude Haiku 4.5 | $1.00 | $5.00 | ~$0.007 |
| Claude Sonnet 4.6 | $3.00 | $15.00 | ~$0.02 |
| Claude Opus 4.8 | $5.00 | $25.00 | ~$0.035 |

Prompt caching cuts the input side hard: cache **read** ≈ 0.1× input, cache **write** ≈ 1.25× (5-min) / 2× (1-hr). A fixed system prompt + constraint schema cached once → repeat briefs bill input at ~$0.10/1M (Haiku). **Self-hosting Mistral-7B on the same GPU = $0/call** and is the recommended path for zero marginal cost.

**Monthly totals — two configs:**

| Rooms/mo | Serverless GPU (pay-per-use) | Self-hosted dedicated GPU (flat) |
|---|---|---|
| 100 | **~$37** (GPU ~$5 + LLM ~$1 + host $30 + storage $1) | ~$251 (GPU idle — overkill) |
| 1,000 | **~$85** | ~$253 |
| 10,000 | ~$565 | **~$255** (1 GPU $220 + host $30 + storage $5) |
| 100,000 | ~$5,000 | **~$1,850** (≈8 GPUs $1,760 + self-host LLM $0 + $90) |

**Crossover ≈ 5k rooms/mo:** below it, serverless is cheaper (low fixed, pay-per-use); above it, a dedicated GPU with a self-hosted LLM wins and drives **marginal cost per room toward $0**.

**Per-room cost:** ~$0.05 (serverless, low volume) down to **<$0.005** (self-hosted at scale). Negligible against any realistic SaaS price (e.g. $5/room or $50/seat/mo → COGS well under 2%).

**Levers that minimize / zero out marginal cost ("I don't pay per use"):**
- Self-host the open models (3D gen + Mistral LLM) on a fixed/owned GPU → no per-call API tax.
- OR-Tools solver runs on CPU → effectively free.
- Use **Cloudflare R2** for mesh/XKT delivery → **$0 egress** (vs S3 $0.09/GB).
- Cache the LLM system prompt + constraint schema → near-zero input billing if you keep an API in the loop.

---

## Track B — Best-in-class benchmark (incl. non-commercial) — **NEVER SHIP**

Reference yardstick only, to see the quality ceiling before committing to Track A. Most academic scene-synthesis (ATISS, LayoutGPT, Holodeck, DiffuScene, 3D-FRONT dataset) is research-/non-commercial-licensed.

- **Production cost: $0 — because it never goes to production.** These cannot be monetized at any price (non-commercial licences), so there is no recurring cost line.
- **One-time benchmark cost: ~$10** of rented GPU (same RunPod approach as the 4-way 3D bake-off) to generate comparison layouts internally, then discard.
- **Hard boundary:** outputs from a research-licensed model carry the licence with them. Keep any Track B run strictly internal/offline — its layouts cannot feed the Track A product, even as "inspiration data."

---

## "I don't pay for it" — positioning

1. **Licence royalties:** $0 on Track A; Track B is not commercially licensable at any price (hence benchmark-only).
2. **Infrastructure is a business cost (COGS), not personal.** Set up a **company-owned cloud billing account** (SCS's card/entity), not a personal card. Every GPU/hosting/storage line bills to SCS.
3. **Architecture → near-zero marginal cost.** Self-hosted open models + R2 zero-egress + OR-Tools means monetization is almost pure margin; the business funds a small fixed infra base, not a per-customer tax.
4. **Pricing passes compute through.** Even at ~$0.03/room COGS, any per-room/seat price covers infra many times over.
5. **Get it in writing.** Whether SCS funds infra and who owns the product IP / output should be explicit in your employment or contractor agreement. *This is a business/legal point, not legal advice — confirm with SCS's terms or a professional.*

---

## Heilbronn / Germany localization (EUR, 2026)

SCS is in **Heilbronn (Baden-Württemberg)**, so costs are in EUR at German rates, and EU/German hosting is a *bonus* — it keeps data EU-resident (GDPR-clean) and aligns with the commercial-must-work-in-EU licence posture.

**2026 electricity (the number you asked for):**
- German commercial tariff (*Gewerbestrom*, ≤100,000 kWh/yr, new contract): **≈ 25.0 ct/kWh** average.
- Baden-Württemberg average: **≈ 24.4 ct/kWh**.
- Use **€0.25/kWh** for Heilbronn on-prem.

**VAT:** all figures below are **net**. 19% MwSt is added on invoices but is reclaimable input tax (*Vorsteuerabzug*) for a registered business → net = true cost.

**Claude API in EUR** (USD-billed, €1≈$1.08): Haiku ~€0.93/€4.63, Sonnet ~€2.78/€13.89, Opus ~€4.63/€23.15 per 1M in/out. ~€0.0065/room (Haiku). Self-hosted Mistral on the same GPU = €0.

**GPU options:**

| Option | What | Cost (net) | Notes |
|---|---|---|---|
| **Hetzner cloud GPU** (DE) | GEX44, RTX 4000 Ada 20 GB | **€184/mo** + ~€79 setup | Cheapest German DC; electricity baked in (no separate power bill); GDPR-clean |
| **On-prem Heilbronn** | Owned RTX 4090/4000 box | **~€175/mo** = elec ~€90 + amort ~€85 | Power: ~0.45–0.6 kW × 24/7 ≈ 324–432 kWh/mo × €0.25 = €80–108 |
| **STACKIT** (Schwarz Group, local) | Sovereign GPU VMs, pay-as-you-go | enterprise-tier (via calculator) | Same city as **IPAI Heilbronn**; pick for German sovereignty / IPAI ties |

**Monthly totals (EUR), Heilbronn — one GPU covers ~10–14k rooms/mo:**

| Rooms/mo | Hetzner GPU (fixed) | On-prem Heilbronn (elec @ €0.25) |
|---|---|---|
| 1,000 | **~€195** | **~€185** |
| 10,000 | ~€200 | ~€185 |
| 100,000 | ~€1,500 (≈8× GEX44) | ~€1,400 (≈8 boxes) |

**Per-room cost:** ~€0.19 at 1k rooms, **~€0.019 at 10k**, falling further at scale. Marginal cost per room ≈ €0 once on a fixed GPU (electricity already in the fixed line). Licence royalties still €0.

**Local LLM vendor option:** Aleph Alpha (Heidelberg, ~40 km) is an EU/commercial LLM if SCS wants a German vendor for brief-translation instead of self-hosting or Claude.

*Sources: German/BW electricity — [strom-report.com](https://strom-report.com/strompreis-gewerbe/), [stromauskunft.de](https://www.stromauskunft.de/stromversorger/baden-wuerttemberg/); Hetzner GEX44 — [hetzner.com](https://www.hetzner.com/dedicated-rootserver/gex44/); STACKIT/IPAI — [stackit.com](https://stackit.com/en), [IPAI (Wikipedia)](https://en.wikipedia.org/wiki/Innovation_Park_Artificial_Intelligence).*

---

*Numbers are estimates with stated assumptions; re-baseline against real volume and the GPU rates you actually rent. Licence facts per [[scs-license-constraints]]. Pairs with the room-layout method research (in progress).*
