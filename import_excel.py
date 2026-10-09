"""Import the master EPCM Guide Netherlands Excel into the DB.

Usage:
    python import_excel.py <path/to/EPCM Guide_Netherlands.xlsx> [--dry-run]

Does, in order:
  1. seed taxonomy_terms (idempotent)
  2. upsert every row of 'Companies' sheet into `companies`
     - setting category_canonical via taxonomy.map_to_canonical
     - preserving scraper-side fields (news_url/jobs_url DB wins)
  3. import 'Contacts' sheet into `contacts` with role_bucket inferred from title
  4. import each role sheet (project engineers / project managers / senior
     technical / architecten / product manager / safety / rest / construction
     managers / freelance) with role_bucket pinned to the sheet name
     (forward-filling the company column from merged cells)
  5. upsert 'Sources' sheet into `event_sources` where appropriate

Prints a summary of inserts/updates/skips per sheet.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from openpyxl import load_workbook

import db
import taxonomy

# ---------------------- role-bucket classifier ---------------------- #
# Order matters — first match wins.
ROLE_RULES: list[tuple[str, re.Pattern]] = [
    ("project_engineer_mep",       re.compile(r"\bmep\b", re.I)),
    ("project_engineer_civil",     re.compile(r"\bcivil\b|burger", re.I)),
    ("project_engineer_structural",re.compile(r"\bstructural\b|constructeur", re.I)),
    ("project_engineer_process",   re.compile(r"\bprocess (eng|engineer)", re.I)),
    ("project_engineer_automation",re.compile(r"\bautomation (eng|engineer)|automatisering", re.I)),
    ("project_engineer_ei",        re.compile(r"\be&?i\b", re.I)),
    ("project_engineer_bim",       re.compile(r"\bbim\b", re.I)),
    ("project_engineer",           re.compile(r"\bproject engineer\b|\bengineer\b|ingenieur", re.I)),
    ("project_manager",            re.compile(r"\bproject manager\b|\bpm\b|projectleider|project leider", re.I)),
    ("construction_manager",       re.compile(r"\bconstruction manager\b|bouwmanager|bouwkundige", re.I)),
    ("architect",                  re.compile(r"\barchitect\b", re.I)),
    ("product_manager",            re.compile(r"\bproduct manager\b|productmanager", re.I)),
    ("plant_manager",              re.compile(r"\bplant manager\b|plant mgr|fabriek(s)?manager", re.I)),
    ("hse_safety",                 re.compile(r"\b(hse|hs&e|safety|health)\b|veiligheid", re.I)),
    ("procurement",                re.compile(r"\b(procurement|purchasing|inkoop|buyer)\b|contract manager", re.I)),
    ("senior_technical",           re.compile(r"\bsenior (technical|consultant|director)\b|business unit", re.I)),
    ("executive",                  re.compile(r"\b(ceo|cto|cfo|coo|director|managing director|directeur|president|founder)\b", re.I)),
    ("sales_commercial",           re.compile(r"\b(sales|commercial|account|business development|verkoop)\b", re.I)),
    ("marketing",                  re.compile(r"\b(marketing|communication|comms|brand|pr)\b", re.I)),
    ("hr",                         re.compile(r"\bhr\b|human resources|talent|recruiter|recruitment", re.I)),
]

# Explicit mapping used when a contact comes from a role-labelled sheet.
# These override the title-based inference above.
SHEET_TO_ROLE: dict[str, str] = {
    "project engineers":    "project_engineer",
    "project managers":     "project_manager",
    "senior technical":     "senior_technical",
    "architecten":          "architect",
    "product manager":      "product_manager",
    "safety":               "hse_safety",
    "construction managers":"construction_manager",
    "rest":                 "project_other",
    "freelance":            "freelance",
    "plant managers":       "plant_manager",
    "HR":                   "hr",
    "Commerce":             "sales_commercial",
}


def classify_role(title: str | None) -> str | None:
    if not title:
        return None
    for role, rx in ROLE_RULES:
        if rx.search(title):
            return role
    return None


# ---------------------- helpers ---------------------- #
def _s(cell) -> str:
    if cell is None:
        return ""
    return str(cell).strip()


def _s_or_none(cell) -> str | None:
    v = _s(cell)
    return v or None


def _is_email(s: str | None) -> bool:
    return bool(s) and "@" in s and "." in s and " " not in s


# ---------------------- importers ---------------------- #
def import_companies(wb, dry_run: bool) -> dict:
    """Upsert the Companies sheet. Returns {inserted, updated, skipped}."""
    ws = wb["Companies"]
    inserted = updated = skipped = 0

    rows = list(ws.iter_rows(values_only=True))
    header = rows[0]  # col 1 is COMPANY, col 3 is Category, etc.

    for row in rows[1:]:
        name = _s(row[0]) if row else ""
        if not name:
            skipped += 1
            continue

        category_raw = _s_or_none(row[2]) if len(row) > 2 else None
        location     = _s_or_none(row[3]) if len(row) > 3 else None
        tel          = _s_or_none(row[4]) if len(row) > 4 else None
        email        = _s_or_none(row[5]) if len(row) > 5 else None
        if email and not _is_email(email):
            email = None
        website      = _s_or_none(row[6]) if len(row) > 6 else None
        news_url     = _s_or_none(row[7]) if len(row) > 7 else None
        jobs_url     = _s_or_none(row[8]) if len(row) > 8 else None
        linkedin     = _s_or_none(row[9]) if len(row) > 9 else None
        pitch        = _s_or_none(row[10]) if len(row) > 10 else None
        li_industry  = _s_or_none(row[11]) if len(row) > 11 else None
        summary      = _s_or_none(row[12]) if len(row) > 12 else None
        specialities = _s_or_none(row[13]) if len(row) > 13 else None
        event_source = _s_or_none(row[14]) if len(row) > 14 else None
        event_pitch  = _s_or_none(row[15]) if len(row) > 15 else None
        event_profile= _s_or_none(row[16]) if len(row) > 16 else None

        cat_top, cat_sub = taxonomy.map_to_canonical(category_raw)

        if dry_run:
            inserted += 1
            continue

        # Upsert the base row preserving scraper-side news_url / jobs_url when
        # the DB already has them (DB wins for those two columns because the
        # scraper discovers more than LinkedIn SalesNav knows about).
        try:
            with db._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        insert into companies
                            (name, category_1, category_canonical,
                             subcategory_canonical, location, tel, email,
                             website, news_url, jobs_url,
                             linkedin_url, linkedin_industry, summary,
                             specialities, event_source, event_pitch,
                             event_profile, enrich_source)
                        values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        on conflict (name) do update set
                            category_1            = coalesce(excluded.category_1,            companies.category_1),
                            category_canonical    = coalesce(excluded.category_canonical,    companies.category_canonical),
                            subcategory_canonical = coalesce(excluded.subcategory_canonical, companies.subcategory_canonical),
                            location              = coalesce(excluded.location,              companies.location),
                            tel                   = coalesce(excluded.tel,                   companies.tel),
                            email                 = coalesce(excluded.email,                 companies.email),
                            website               = coalesce(excluded.website,               companies.website),
                            news_url              = coalesce(companies.news_url, excluded.news_url),
                            jobs_url              = coalesce(companies.jobs_url, excluded.jobs_url),
                            linkedin_url          = coalesce(excluded.linkedin_url,          companies.linkedin_url),
                            linkedin_industry     = coalesce(excluded.linkedin_industry,     companies.linkedin_industry),
                            summary               = coalesce(excluded.summary,               companies.summary),
                            specialities          = coalesce(excluded.specialities,          companies.specialities),
                            event_source          = coalesce(excluded.event_source,          companies.event_source),
                            event_pitch           = coalesce(excluded.event_pitch,           companies.event_pitch),
                            event_profile         = coalesce(excluded.event_profile,         companies.event_profile),
                            updated_at            = now()
                        returning (xmax = 0) as inserted
                        """,
                        (name, category_raw, cat_top, cat_sub, location, tel,
                         email, website, news_url, jobs_url, linkedin,
                         li_industry, summary, specialities, event_source,
                         event_pitch, event_profile, "excel_import"),
                    )
                    was_insert = cur.fetchone()[0]
            if was_insert:
                inserted += 1
            else:
                updated += 1
        except Exception as e:  # noqa: BLE001
            print(f"  !!  failed to upsert '{name}': {e}", file=sys.stderr)
            skipped += 1

    return {"inserted": inserted, "updated": updated, "skipped": skipped}


def import_contacts_main_sheet(wb, dry_run: bool) -> dict:
    """Contacts sheet: Company name · Employees · Contact Linkedin · Contact
    name · Title · Email. Classify role_bucket from Title."""
    ws = wb["Contacts"]
    inserted = updated = skipped = 0

    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i == 0:
            continue
        if not row or not any(row):
            continue
        company_name   = _s_or_none(row[0]) if len(row) > 0 else None
        employees      = _s_or_none(row[1]) if len(row) > 1 else None
        linkedin       = _s_or_none(row[2]) if len(row) > 2 else None
        name           = _s_or_none(row[3]) if len(row) > 3 else None
        title          = _s_or_none(row[4]) if len(row) > 4 else None
        email_raw      = _s_or_none(row[5]) if len(row) > 5 else None
        email = email_raw if _is_email(email_raw or "") else None

        if not name:
            skipped += 1
            continue

        payload = {
            "company_name":     company_name,
            "name":             name,
            "title":            title,
            "email":            email,
            "employees_bucket": employees,
            "linkedin_url":     linkedin,
            "role_bucket":      classify_role(title),
            "source":           "excel_contacts",
        }

        if dry_run:
            inserted += 1
            continue

        cid = db.upsert_contact(payload)
        if cid:
            inserted += 1
        else:
            skipped += 1

    return {"inserted": inserted, "updated": updated, "skipped": skipped}


def import_role_sheet(wb, sheet_name: str, dry_run: bool) -> dict:
    """A role-tagged sheet: col 0 = company (forward-fill), col 1 = company
    LinkedIn page, col 2 = person LinkedIn, col 3 = name, col 4 = title,
    col 5 = role_sub tag. Col 1 must never be used as the person key: it is
    shared by every person at the same company."""
    if sheet_name not in wb.sheetnames:
        return {"inserted": 0, "updated": 0, "skipped": 0, "missing": True}
    ws = wb[sheet_name]
    inserted = updated = skipped = 0

    last_company = None
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if not row or not any(row):
            continue
        if _s(row[0]):
            last_company = _s(row[0])
        name = _s_or_none(row[3]) if len(row) > 3 else None
        title = _s_or_none(row[4]) if len(row) > 4 else None
        tag   = _s_or_none(row[5]) if len(row) > 5 else None
        if not name:
            skipped += 1
            continue

        payload = {
            "company_name":       last_company,
            "name":               name,
            "title":              title,
            "linkedin_url":       _s_or_none(row[2]) if len(row) > 2 else None,
            "role_bucket":        SHEET_TO_ROLE.get(sheet_name) or classify_role(title),
            "role_sub":           tag,
            "source":             f"excel_role_{sheet_name.replace(' ', '_')}",
        }
        if dry_run:
            inserted += 1
            continue
        cid = db.upsert_contact(payload)
        if cid:
            inserted += 1
        else:
            skipped += 1
    return {"inserted": inserted, "updated": updated, "skipped": skipped}


# ---------------------- main ---------------------- #
def run(xlsx_path: Path, dry_run: bool = False) -> dict:
    wb = load_workbook(xlsx_path, data_only=True, read_only=True)

    print(f"Importing from {xlsx_path.name}  (dry_run={dry_run})")
    print(f"  sheets found: {wb.sheetnames}")

    if not dry_run:
        print("  seeding taxonomy_terms …")
        taxonomy.seed()

    print("  importing Companies …")
    comp = import_companies(wb, dry_run)
    print(f"    inserted={comp['inserted']:,}  updated={comp['updated']:,}  skipped={comp['skipped']:,}")

    print("  importing Contacts (main) …")
    con = import_contacts_main_sheet(wb, dry_run)
    print(f"    upserted={con['inserted']:,}  skipped={con['skipped']:,}")

    role_totals = {"inserted": 0, "skipped": 0}
    for sheet in ["project engineers", "project managers", "senior technical",
                  "architecten", "product manager", "safety",
                  "construction managers", "rest", "freelance",
                  "plant managers", "HR", "Commerce"]:
        r = import_role_sheet(wb, sheet, dry_run)
        if r.get("missing"):
            continue
        role_totals["inserted"] += r["inserted"]
        role_totals["skipped"]  += r["skipped"]
        print(f"  importing role sheet '{sheet}' …  upserted={r['inserted']:,}  skipped={r['skipped']:,}")

    print()
    print("=== SUMMARY ===")
    print(f"  Companies : {comp['inserted']:,} new / {comp['updated']:,} updated")
    print(f"  Contacts  : {con['inserted']:,} main + {role_totals['inserted']:,} role rows = "
          f"{con['inserted'] + role_totals['inserted']:,} total")
    return {"companies": comp, "contacts_main": con, "role_totals": role_totals}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?",
                    default="../tasks/EPCM Guide_Netherlands (2).xlsx")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    db.init_db()
    run(Path(args.path).expanduser().resolve(), dry_run=args.dry_run)
