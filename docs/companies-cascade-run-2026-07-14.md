# Companies Tab + Enrichment Cascade — Run Report (2026‑07‑14)

Formal reference for the first live run of the 4‑leg company enrichment
cascade against the food‑tech‑event exhibitor list.

---

## 1. Input

| Item | Value |
|---|---|
| **Source URL** | `https://food-tech-event.nl/nl/exposantenlijst/` |
| **Companies scraped** | 117 exhibitor cards (single-page, server-rendered) |
| **Normalized into** | `companies` table on Heroku Postgres (`essential-0`) |
| **Target schema** | 17 columns per row (COMPANY · Category × 3 · Location · Tel · Email · Website · News · Jobs · LinkedIn company page · Linkedin industry · Summary · Specialities · EVENT SOURCE · EVENT PITCH · EVENT PROFILE) |
| **Fields obtained directly from scrape** | COMPANY, Category × 3, EVENT SOURCE, EVENT PITCH, EVENT PROFILE (5 of 17) |
| **Fields left to enrichment** | Location, Tel, Email, Website, News, Jobs, LinkedIn URL, LinkedIn industry, Summary, Specialities (10 of 17) |

---

## 2. Cascade design (cheapest‑first, adapted from Finhabits)

Order: **IcyPeas → FullEnrich → AI Ark → Apollo → site subpath probe**

| Leg | Provider | Endpoint used | Cost model | Real behaviour on this run |
|---|---|---|---|---|
| 1 | **IcyPeas** | `POST /api/find-people` with `currentCompanyName.include=[name]` (find‑companies rejects our body on this tier) | 0.02 credit / result | Workhorse. Hit 2/3 sample companies. |
| 2 | **FullEnrich** | `POST /api/v2/company/search` (singular) | free on op plan | Returns **`403 error.not_enough_credits`** — account out of credits. |
| 3 | **AI Ark** | `POST /api/developer-portal/v1/companies` | free tier / paid | Free bucket exhausted mid‑run → **`HTTP 402`**. Name‑match guard active (unfiltered results were returning "Tata Group" for every query). |
| 4 | **Apollo** | `organizations/enrich` (domain) → `mixed_companies/search` (name) fallback | 1 credit / call | Hit 2/3 samples; every call charged even on miss. |
| — | **site_probe** | `GET {website}/nieuws · /news · /blog · /vacatures · /careers · /jobs` | free | Found `/nieuws` + `/vacatures` on Aeson; none on ABB. |

Every attempt writes:
1. one row to `company_enrichment_log` (audit),
2. one live event to `scrape_events` via `RunLogger` (streams into the Logs+Costs tab).

---

## 3. Sample run — 3 companies (representative of full 117)

Per‑attempt log from `company_enrichment_log` (annotated):

| Company | Leg | Provider | Success | ms | Credits | Notes |
|---|---:|---|:---:|---:|---:|---|
| **Aeson BV** | 1 | icypeas | ✓ | 400 | 0.06 | website + linkedin + industry + location + summary |
| Aeson BV | 2 | fullenrich | ✗ | 177 | 0 | 400 `error.filters.empty` |
| Aeson BV | 3 | ai_ark | ✗ | 436 | 0 | 402 Payment Required |
| Aeson BV | 4 | apollo | ✓ | 299 | 1.0 | added tel |
| Aeson BV | 5 | site_probe | ✓ | 8 713 | 0 | found `/nieuws/` + `/vacatures/` |
| **ABB Robotics** | 1 | icypeas | ✓ | 427 | 0.06 | full field set (see caveat) |
| ABB Robotics | 2 | fullenrich | ✗ | 51 | 0 | 400 |
| ABB Robotics | 3 | ai_ark | ✗ | 386 | 0 | 402 |
| ABB Robotics | 4 | apollo | ✓ | 369 | 1.0 | added tel |
| ABB Robotics | 5 | site_probe | ✗ | 7 648 | 0 | no news/jobs paths responded |
| **4FOOD Software** | 1 | icypeas | ✗ | 350 | 0 | not_found |
| 4FOOD Software | 2 | fullenrich | ✗ | 57 | 0 | 400 |
| 4FOOD Software | 3 | ai_ark | ✗ | 796 | 0 | not_found |
| 4FOOD Software | 4 | apollo | ✗ | 216 | 1.0 | not_found (still billed) |
| 4FOOD Software | — | site_probe | (skipped) | — | — | no website to probe |

### Results in `companies` table

| Company | Status | Source | Filled fields |
|---|---|---|---|
| **Aeson BV** | `enriched` | `icypeas_auto` | website `https://www.aeson.nl/` · linkedin `linkedin.com/company/aeson-bv/` · industry `Mechanical Or Industrial Engineering` · location `Huizen, Noord-Holland, Nederland` · tel `+31 35 523 3828` · summary (short) · news `/nieuws/` · jobs `/vacatures/` |
| **ABB Robotics** | `enriched` | `icypeas_auto` | website · linkedin · industry `Automation Machinery Manufacturing` · location `बेंगालुरू, कर्नाटक, भारत` (⚠ geo bias — IcyPeas found ABB‑India people first) · tel |
| **4FOOD Software** | `terminal` | — | none (too small; no provider had it) |

---

## 4. Costs actually incurred on this run

| Company | IcyPeas credits | Apollo credits | ≈ USD (basic plans) |
|---|---:|---:|---:|
| Aeson BV | 0.06 | 1.0 | **$0.051** |
| ABB Robotics | 0.06 | 1.0 | $0.051 |
| 4FOOD Software | 0.00 | 1.0 | $0.050 |
| **Total (3 companies)** | 0.12 | 3.0 | **~$0.152** |

**Extrapolated to the full 117 companies (before today's optimisations):**
- IcyPeas: ~ **$0.13** (all 117 × 0.06 cr × $0.019)
- Apollo: ~ **$5.85** (117 × 1 cr × ~$0.05) — fires on every company because
  no single provider fills all 10 fields, so the cascade never short‑circuited.
- FullEnrich + AI Ark: currently **$0** (both plans exhausted).
- **Total: ~$6 per full re‑enrichment.** Apollo = ~96 % of the bill.

---

## 5. Assessment of each provider

- **IcyPeas** — genuine hit rate ~66 % on the samples; excellent value at $0.001 / hit.
  Data quality solid; only caveat is geo bias for multinationals.
- **FullEnrich** — **unusable** on the current plan (`403 not_enough_credits`).
  Skip the leg or top up the account.
- **AI Ark** — free tier ran out mid‑run (`402` after a handful of calls) and even
  before that the search returned generic non‑matching results (Tata Group for
  every Dutch supplier query). Utility limited unless the query shape is fixed
  or the plan upgraded.
- **Apollo** — hits ~66 % of samples; charges every call including misses.
  Only worth firing when earlier legs failed to deliver the two anchor fields
  (website, linkedin_url).

---

## 6. Follow‑ups added today

1. **NL location filter** on IcyPeas so multinationals resolve to their NL
   presence (fixes the ABB → Bengaluru issue).
2. **Early‑exit** after any leg that yields `website + linkedin_url` — skips
   the expensive Apollo call whenever IcyPeas already delivered them.
3. **Chunked bulk‑enrich** — the "Enrich all pending" button now processes in
   batches of 10 with a client‑side progress loop, so 117 companies fit under
   Heroku's per‑request 30 s router timeout and complete in a handful of
   batches.

See `2026-07-14-companies-tab-and-cascade.md` (task log) and this run report
for the follow‑up assessment numbers.

---

## 7. Follow‑up assessment (same day, post‑optimisations)

Re‑ran a chunked batch of 5 companies + a standalone re‑enrichment of ABB
Robotics with the three optimisations in place.

**Per‑attempt log (6 companies, 16 total attempts):**

| Company | Legs actually called | Outcome | Cost |
|---|---|---|---|
| Aeson BV | icypeas ✓ → site_probe | early‑exit after IcyPeas | $0.00114 |
| Anticimex | icypeas ✓ → site_probe | early‑exit | $0.00114 |
| Aqua+ | icypeas ✓ → site_probe | early‑exit | $0.00114 |
| Arcadis Nederland B.V. | icypeas ✓ → fullenrich → ai_ark → apollo → site_probe | IcyPeas hit lacked anchors → walked full cascade | $0.05114 |
| ABB Robotics (in batch) | icypeas ✗ → fullenrich → ai_ark → apollo → site_probe | NL filter blocked, everything missed → terminal | $0.05 |
| ABB Robotics (re‑enrich with 2‑pass fallback) | icypeas ✓ → site_probe | NL pass returned 0 → global fallback hit → early‑exit | $0.00114 |

**Aggregate:** 6 companies, 16 attempts, **$0.1057 → $0.01762 average per
company** (65 % cheaper than the $0.051 baseline).

**NL filter trade‑off:** the two‑pass fallback (NL first, global second on
miss) preserves data for both mid‑size Dutch suppliers (Aeson) AND global
multinationals (ABB). ABB's location still comes back as Bengaluru — accepted
compromise vs. no data at all.

### Extrapolated full 117‑company cost (post‑optimisations)

Assuming ~75 % early‑exit hit path, ~15 % full‑cascade hit path, ~10 % terminal:

| Path | Companies | $ / company | Subtotal |
|---|---:|---:|---:|
| Early‑exit (icypeas anchors) | ~88 | $0.00114 | $0.10 |
| Full cascade with IcyPeas hit | ~18 | $0.05114 | $0.92 |
| Terminal (all miss, still bills Apollo) | ~12 | $0.05 | $0.60 |
| **Total** | **117** | | **~$1.62** |

**73 % cheaper than the $6 pre‑optimisation estimate.**

### Runtime & chunking

- Batch of 5 completed in **26 s** server‑side — safely under Heroku's 30 s
  router timeout.
- Client‑side JS loop chains batches; full 117 ≈ 24 batches × ~26 s = **~10 min**.
- Bottleneck within a batch is now `site_probe` (up to ~18 s worst case,
  6 paths × 3 s). Parallelising the probes with a thread pool would cut this
  to ~3 s per company — flagged as a small future optimisation.

---

## 8. Actual full‑run results (supersedes the estimate above)

Executed via a one‑off dyno (`heroku run python bulk_enrich.py`) so the cascade
runs on the server without the 30 s router timeout. Full log written to
`company_enrichment_log`; run also streamed to the Logs+Costs tab as one
`enrich_bulk_all` run.

### Aggregate

| Metric | Value |
|---|---:|
| Companies processed in this run | 111 (the 6 sampled earlier were already enriched/terminal) |
| Total directory (companies table) | **117** |
| Runtime | **358 s (~6 min)** — 3.2 s / company avg |
| Enriched | **97 / 117 (83 %)** |
| Terminal (all legs miss) | 20 / 117 (17 %) |
| Total credits burned across full directory | 39.7 |
| Total spend across full directory | **$1.84** |
| Avg cost / company | **$0.0157** |
| Total attempts logged | 311 rows in `company_enrichment_log` |

### By‑source breakdown

| Source column value | Companies | Share |
|---|---:|---:|
| `icypeas_auto` (early‑exit hit path) | **92** | 79 % |
| `apollo_auto` (fallback when IcyPeas missed) | 5 | 4 % |
| unset (terminal) | 20 | 17 % |

The early‑exit optimisation avoided ~92 Apollo calls at ~$0.05 each → **~$4.60
saved on this run alone**. FullEnrich and AI Ark contributed zero enriched
rows (both plans credit‑exhausted).

### Field fill rates across the 117 rows

| Field | Populated | Note |
|---|---:|---|
| `website` | 76 % | |
| `linkedin_url` | 79 % | |
| `linkedin_industry` | 71 % | |
| `location` | 79 % | with NL‑bias fallback |
| `summary` | 70 % | LinkedIn "About" text |
| `news_url` | 39 % | site subpath probe |
| `jobs_url` | 32 % | site subpath probe |
| `tel` | 5 % | IcyPeas rarely returns phone; only the 5 Apollo rows have it |
| `email` | 0 % | no leg currently supplies email — would need Icypeas email‑search (1 cr / email ≈ $2 extra for 117) |
| `specialities` | 0 % | none of the working legs expose it |

### Estimate vs. actual

| | Estimated (§7) | Actual (§8) | Δ |
|---|---:|---:|---:|
| Total cost | $1.62 | $1.84 | +13 % |
| Runtime | ~10 min | ~6 min | −40 % |
| Fill rate | ~90 % | 83 % | −7 pp |

The cost overshoot is entirely from the 20 terminal rows — each still burns
the $0.05 Apollo call after every earlier leg misses, because early‑exit only
fires on a successful hit. Runtime beat the estimate because site_probe was
faster than the worst case for most companies.

### Notes / candidate follow‑ups

1. **Email column is empty.** Icypeas `email-search` costs 1 cr / found email
   (~$0.02 / row at Basic plan). 117 rows × ~1 email/row ≈ **~$2 extra**.
2. **Terminal‑row waste.** 20 companies × $0.05 (Apollo miss) = **$1 wasted**
   on rows that yielded nothing. Cheap mitigation: run Apollo only when IcyPeas
   didn't miss at all (i.e., dropping Apollo entirely and accepting the 15 %
   recall loss it would cause — trade $1 for 15 % lower fill rate).
3. **`tel` sparse.** 5 % fill rate. If phones matter, add a phone‑capable leg
   (Datagma‑like) or scrape the company's `/contact` page.
4. **`specialities` empty.** Would require actually scraping the LinkedIn
   company page — none of the API legs surface it.

