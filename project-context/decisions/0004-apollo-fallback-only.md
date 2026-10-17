# 0004 — Apollo as a fallback only
Status: accepted
Source: meeting 2026-10-09; enrichment cost guide sent 2026-10-09 (measured hit rates); client approval of the cheaper enrichment option on WhatsApp 2026-10-09.

**Decision.** Apollo is not part of the default enrichment route; it is kept only as a fallback for gaps no other
integration fills. Reasons: a resale clause in its terms of service, and a low measured hit rate (22% of
attempts vs 70% for IcyPeas) while it billed for every call.
**Consequence.** Run bulk enrichment with `ENABLE_APOLLO=false` unless a ticket says otherwise. The code still
has Apollo on by default — the setting must be changed before the next bulk run.
