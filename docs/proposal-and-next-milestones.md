# Hi-Engineer — Proposal & Next Milestones

## Next Milestones (to complete the project)

The scraping foundation, Supabase persistence, and Logs+Costs observability are
live, so the remaining work is:

1. **Normalize Module 01** — convert today's raw JSONB scrape blobs into a
   structured, deduplicated supplier directory (company name, website, location,
   SBI/KvK category) and widen ingestion beyond food-tech-event to the full
   event/portal source list plus the **KvK Chamber-of-Commerce API**.
2. **Enrich** — add AI-generated category tags and a short summary per supplier
   (Claude) and ship the GDPR-friendly **"Claim your profile"** flow.
3. **Build the real Module 02 Content Engine** — RSS/feed detection, a
   **scheduled daily fetch**, clean-markdown article scraping, **100-word AI
   summaries with category + source attribution in NL & EN**, and a published
   categorized feed (article summarization, distinct from today's directory
   scraping).
4. **Automate & schedule** both pipelines to run daily within the
   5,000-articles / 5,000-records fair-use tier.
5. **Go-live & handover** — production checks, GDPR-compliant data structure,
   documentation, and a ready feed/API for the hi-engineer.ai frontend and
   Circle.so.

Parallel track (client): supply the priority source list, build the frontend,
run the Circle subscription, moderate, and approach suppliers for profile claims.

### Status vs. proposal (snapshot)

| Area | Done | Remaining |
|------|------|-----------|
| Scraping (direct cURL, no Firecrawl/Apify) | ✅ exhibitor list + 9 media portals | broaden to full source list + KvK API |
| Persistence | ✅ Supabase (JSONB cache + run/cost logs) | normalize into structured supplier tables |
| Enrichment | ✅ Icypeas find-people (contacts) | AI category tags + summaries; claim-profile flow |
| Content Engine (Module 02) | ⚠️ directory scraping only | RSS detection, daily fetch, AI summaries (NL+EN), feed |
| Automation | ❌ manual triggers | daily scheduling |
| Observability | ✅ Logs+Costs tab | — |
| Go-live/handover | ⚠️ app live on Heroku | GDPR structure, docs, handover |

---

## Monthly Run-Cost Estimate (full build)

Architecture: **cURL → Firecrawl fallback** (scraping), **Icypeas → AI Ark fallback**
(enrichment), **Claude** (summaries/tags), Heroku + Supabase. Volumes: **100+
articles/month** and **1,000 companies/month extracted + enriched with leads**.

**Headline: ≈ €90–€130/month (~$95–$140) in tools + infrastructure**, dominated by
the two enrichment providers. Excludes the build (€2,950 one-time) / maintenance
retainer and the client-paid Circle.so.

| Layer | Service | Why this tier | Monthly |
|---|---|---|---|
| Scrape (primary) | cURL | free; handles ~70–80% of pages | $0 |
| Scrape (fallback) | Firecrawl | JS/blocked pages + clean markdown (~300–500 pages); fits free 1,000 cr/mo | $0 (→ $16 Hobby) |
| Enrich (primary) | Icypeas | find-people 0.02 cr/result + ~1,500 email cr → Premium 4,000 cr | $39 |
| Enrich (fallback) | AI Ark | catches Icypeas misses; Starter 5,000 cr (free is only 100 cr/mo) | $49 |
| AI summaries/tags | Claude Haiku 4.5 | ~0.5M in / 0.05M out @ $1/$5 per M | ~$2 |
| Hosting | Heroku Basic + free Scheduler | runs both engines daily | $7 |
| Database | Supabase | Free fits this volume (Pro for production reliability) | $0 (→ $25 Pro) |
| **Total** | | | **≈ $97 lean · ~$138 with Supabase Pro + Firecrawl buffer** |

**Drivers & levers**
- Enrichment is ~90% of the bill ($88). **Leads without separate email-finding**
  (contact name/title/LinkedIn only) drops Icypeas to Basic $19 and lets AI Ark stay
  free/PAYG → **~$30–50/mo**. **Leads with verified emails** (1–2/supplier) → the ~$97 figure.
- Scraping is ~free at this volume (cURL + Firecrawl's free 1,000 cr/mo).
- Claude is negligible (~$2); even 5,000 articles/mo on Haiku ≈ $15–20.
- The proposal's €345/mo is higher because it bundles 4h maintenance labor + margin;
  the above is the pure tool/infra burn.

Sources: [AI Ark](https://ai-ark.com/pricing/) · [Firecrawl](https://www.firecrawl.dev/pricing) ·
[Icypeas pricing](https://www.icypeas.com/pricing) / [credit costs](https://api-doc.icypeas.com/how-works/credit-cost/) ·
[Claude API](https://platform.claude.com/docs/en/about-claude/pricing) · [Supabase](https://supabase.com/pricing)

---

## Source Documentation (Proposal)

## 01 — What We Heard

> "The industrial engineering world is a closed community. My goal is to become the Emerce of industrial engineering, and I'm replacing agencies with factory suppliers."
> — Sebastiaan

### Today

- Brand is established. Website is live.
- Built solo alongside a busy day job.
- Manual scraping in Excel.
- No content yet, no members yet.

### Where You Want to Go

- Media platform for industrial engineering.
- Paid community via Circle.so.
- Suppliers and factories in one place.
- Upsell via media, jobs, whitepapers.

---

## 02 — Two Challenges, Solvable Independently

Not everything at once. We tackle them as separate modules.

### Module 01 — Supplier Data

A structured database filled with suppliers from event sites, other portals, and proprietary sources. So your platform launches with real content — without hundreds of hours of manual scraping.

**Output:** Searchable supplier directory in Supabase.

### Module 02 — Content Engine

Daily blogs and news from suppliers and industrial portals, fetched, summarized with AI, and published on your platform — categorized, with source attribution and links to the original.

**Output:** Categorized content feed ready for your members.

---

## 03 — Module 01: Supplier Database

*Structuring company data, not outbound spamming.*

| Step | Description |
|------|-------------|
| 01 — Scrape sources | Event sites, exhibitor lists, industrial portals, Chamber of Commerce (KvK) |
| 02 — Normalize | Company name, website, location, SBI category, deduplication |
| 03 — Enrich | AI-generated category tags and summary per supplier |
| 04 — Ready in database | Searchable via your platform or via Circle |

### Phase 1 Recommendation: "Claim Your Profile" — Suppliers Complete Their Own Data

We build the base database. Each profile gets a "Claim this profile" button where suppliers can fill in their own contact details and specializations. More GDPR-friendly, faster, and it gives suppliers a direct reason to visit your platform.

---

## 04 — Module 02: Content Engine

*Summaries with source attribution, not copied articles.*

| Step | Description |
|------|-------------|
| 01 — Detect feeds | RSS from blogs and portals |
| 02 — Fetch daily | Pick up new articles |
| 03 — Scrape clean | Full text in markdown |
| 04 — AI summarize | 100 words + category |
| 05 — Publish | On platform or in Circle |

| Metric | Detail |
|--------|--------|
| **Volume** | 5,000+ articles per month processable, fair-use tier above that |
| **Sources** | 200 → 1,000+ scalable from starter pack to full coverage |
| **Language** | NL + EN — categorization and summaries in both languages |

---

## 05 — What We Deliberately Don't Do

Clear scope prevents future headaches. Three things we explicitly leave out of this proposal.

### No Cold Email Machine

You've indicated that outbound email doesn't fit the community model. We're not building automated outreach. The supplier database is for your platform, not for mass mailings.

### No Full-Text Content Copying

Original articles will not be placed 1-to-1 on your platform. We work with AI summaries plus clear source attribution and links — the way Google News and Feedly work. Better both legally and strategically.

### No Platform Development

We build the data and content engine, not the Circle.so community platform or an extensive custom frontend. You subscribe to that directly yourself. We deliver the feed ready for use.

---

## 06 — How It Fits Together

All automations feed into one central database. You build your platform on top of it.

```
┌─────────────────────────────┐   ┌──────────────────────────────┐
│ Module 01 | Supplier        │   │ Module 02 | Content          │
│ Scrapers                    │   │ Fetchers                     │
│ Apify + Firecrawl + KvK API │   │ RSS + Firecrawl + Claude AI  │
└──────────────┬──────────────┘   └──────────────┬───────────────┘
               │                                  │
               ▼                                  ▼
       ┌──────────────────────────────────────────────┐
       │           n8n + Supabase                      │
       │  Orchestration of all workflows + 1 central   │
       │  database for suppliers and content           │
       └──────────┬─────────────────────┬──────────────┘
                  │                     │
                  ▼                     ▼
       ┌──────────────────┐   ┌────────────────────────┐
       │ hi-engineer.ai   │   │ Circle.so community    │
       │ Directory +      │   │ Discussions, members,  │
       │ content feed on  │   │ paid subscription      │
       │ your own domain  │   │ (managed by you)       │
       └──────────────────┘   └────────────────────────┘
```

---

## 07 — Timeline

4 to 6 weeks from agreement to live. Content engine first, supplier database right after.

| Phase | Duration | Description |
|-------|----------|-------------|
| **Week 1** | 5 days | **Discovery** — Source inventory, ICP, main stack choice (own frontend vs Circle), test setup |
| **Week 2–3** | 8 days | **Build content engine** — RSS detection, fetching, scraping, AI summarization, database, test feed |
| **Week 4–5** | 8 days | **Build supplier database** — Source scrapers, normalization, KvK integration, claim-profile flow |
| **Week 6** | 3 days | **Go-live + handover** — Production checks, documentation, your onboarding, first 30 days monitoring |

---

## 08 — Investment

One-time setup for building both modules. Monthly for tools, hosting, and maintenance.

### Setup (One-Time): €2,950

Build of Module 01 (Supplier database) and Module 02 (Content engine). Includes discovery, testing, delivery, and first 30 days of monitoring.

**Optional:** Contact enrichment layer — Apollo integration for 1–2 contacts per supplier: **+€650**

### Monthly: €345/month

**Includes:** n8n cloud, Firecrawl, Apify, Claude API, Supabase database and hosting, plus 4 hours per month maintenance.

**Fair-use limit:** Up to 5,000 articles and 5,000 supplier records per month. Scalable tier above that.

> Circle.so subscription (from $89/month) is paid directly to Circle and falls outside this proposal.

---

## 09 — Clear Delineation

### We Do — Build, Hosting & Maintenance

- Technically build both modules in n8n
- Manage and pay for tools and API costs
- Host and back up Supabase database
- Set up GDPR-compliant data structure
- Monthly maintenance and small updates
- Documentation and handover at delivery

### You Do — Strategy, Brand & Community

- Provide list of priority sources
- Build out the hi-engineer.ai frontend
- Circle.so subscription and management
- Content moderation and community building
- Sales to members and upsell strategy
- Approach suppliers for profile claims
