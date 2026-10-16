# 0007 — AI classification fills empty fields only, and logs every write
Status: accepted
Source: task 2026-10-09 (AI classification run).

**Decision.** `ai_classify.py` uses Claude to fill only empty category, sub-category, specialities, job role and
news topic fields, with answers constrained to allowed values, and logs every value in `ai_enrichment_log`.
Specialities are written in English.
**Consequence.** Any batch can be audited or rolled back; rerunning only touches new empty rows. Menu links stored
as jobs (`not_a_job`) and news noise (`nav_residue`) are hidden in the UI by default.
