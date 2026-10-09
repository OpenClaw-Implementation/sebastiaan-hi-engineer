"""Build the Hi-Engineer manual-review Excel workbook.

Two content areas — jobs (930 rows) and articles (2,328 rows) — each with:
  * a summary tab: category counts + sample titles + a Relevant? column
  * a detail tab: every row with derived category + blank Relevant? / Notes

Titles are bucketed by keyword hit against the lower-cased title, first
matching keyword wins. Order of the rules IS the priority.
"""

from __future__ import annotations

import csv
import re
from collections import Counter, defaultdict
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.filters import AutoFilter

ROOT = Path("/tmp/report")
OUT = ROOT / "hi_engineer_review.xlsx"


# ---------------------------------------------------------------- palette --
BRAND = "1F6FEB"
BRAND_DARK = "0B3EA6"
INK = "1F2328"
LIGHT = "F6F8FA"
STRIPE = "F0F4F8"
BORDER = "D0D7DE"
MUTED = "6E7781"

thin = Side(style="thin", color=BORDER)
BOX = Border(left=thin, right=thin, top=thin, bottom=thin)


# ---------------------------------------------------------------- rules ---
# Job categories — order matters, first match wins. Values are compiled regexes.
# Word-boundary matching (\b) is applied where sensible; Dutch words often
# appear as roots so we keep patterns loose but still specific.
JOB_RULES: list[tuple[str, re.Pattern]] = [
    ("Intern / Trainee / Junior",
     re.compile(r"\b(intern|stagi?air|stagi?aire|stage|trainee|junior|entry level)\b")),
    ("Executive / C-Level",
     re.compile(r"\b(ceo|cto|cfo|coo|cio|chief|directeur|director|managing director|"
                r"algemeen directeur|algeheel|president|voorzitter)\b")),
    ("Management / Team Lead",
     re.compile(r"\b(manager|leader|leidinggevende|team\s*lead|teamlead|hoofd\b|"
                r"head of|supervisor|coordinator|coördinator)\b")),
    ("Software / IT",
     re.compile(r"\b(software|developer|ontwikkelaar|programmer|devops|data (engineer|scientist)|"
                r"cybersecurity|cloud|frontend|backend|full[- ]?stack|it[- ]|systeem beheer|"
                r"systeem administrator|network engineer|python|java|react)\b")),
    ("Engineering / R&D",
     re.compile(r"\b(engineer|ingenieur|technic|technisch|r&?d\b|research|"
                r"mechanic|mechanical|electric|electronic|process engineer|"
                r"product engineer|application engineer|constructeur|construction eng)\b")),
    ("Sales / Business Dev",
     re.compile(r"\b(sales|commercieel|commercial|account (manager|executive)|"
                r"business development|verkoop|new business|inside sales|"
                r"vertegenwoordig|key account)\b")),
    ("Marketing / Communications",
     re.compile(r"\b(marketing|communicatie|communication|content|brand|social media|"
                r"copywriter|seo|pr\b|public relations)\b")),
    ("Service / Field / Installation",
     re.compile(r"\b(service|monteur|installer|installatie|installation|field|"
                r"maintenance|onderhoud|technician|technicus|buitendienst|"
                r"servicetechnicus|first line|onsite)\b")),
    ("Production / Operations / Logistics",
     re.compile(r"\b(production|productie|operations|operator|logisti|warehouse|"
                r"magazijn|planner|planning|foreman|uitvoerder|voorman|"
                r"assemblage|assembly|machin(ist|e))\b")),
    ("HR / Office / Admin",
     re.compile(r"\b(hr\b|human resources|human capital|administratief|administratie|"
                r"office manager|receptionist|receptioniste|secretari|personeel|payroll|"
                r"office assistant|recruiter|recruitment|talent acquisition)\b")),
    ("Finance / Accounting",
     re.compile(r"\b(finance|financieel|boekhoud|accountant|controller|"
                r"credit control|invoice|debiteur|crediteur)\b")),
    ("Purchasing / Procurement",
     re.compile(r"\b(purchase|purchasing|inkoop|inkoper|procurement|buyer)\b")),
    ("Quality / Safety / QHSE",
     re.compile(r"\b(quality|kwaliteit|qhse|hse|qa\b|iso|safety|veiligheid|arbo)\b")),
    ("Consultant / Advisor / Coach",
     re.compile(r"\b(consultant|adviseur|advisor|coach|trainer|specialist)\b")),
    ("Design / Creative",
     re.compile(r"\b(design(er)?|ontwerp|ux\b|ui\b|creative|kunst|styling|"
                r"graphic|art director)\b")),
    ("Support / Customer / Helpdesk",
     re.compile(r"\b(support|helpdesk|customer service|klantenservice)\b")),
    ("Legal / Compliance",
     re.compile(r"\b(legal|compliance|jurist|counsel|regulatory)\b")),
    ("Education / Academic",
     re.compile(r"\b(docent|teacher|instructor|lecturer|professor|academic|"
                r"onderwijs|opleider|student|learner)\b")),
    ("Care / Health / Welfare",
     re.compile(r"\b(zorg|verpleeg|caregiver|caretaker|welzijn|maatschappelijk|"
                r"beveiliging(sservice)?|beveiliging|security guard)\b")),
    ("Navigation residue / non-title",
     re.compile(r"\b(apply now|solliciteer|bekijk vacature|read more|lees meer|"
                r"learn more|meer weten|open sollicitatie|view job|see more|"
                r"details|arrow_forward|null)\b")),
]

# News categories — same first-match logic
NEWS_RULES: list[tuple[str, re.Pattern]] = [
    ("Product / Launch",
     re.compile(r"\b(nieuw(e|s)? (product|systeem|serie|reeks|generatie)|new product|"
                r"launch|lancering|introduc(es|ing|tion|eer)|unveil|presenteer|"
                r"presenteren|introduceer|beschikbaar|nu leverbaar|now available)\b")),
    ("Partnership / M&A",
     re.compile(r"\b(partnership|samenwerking|partner(s|schap)?|acquis(e|ition)|"
                r"overname|neemt over|joint venture|alliance|merger|fusie|integratie|"
                r"acquires|acquired)\b")),
    ("Trade show / Event",
     re.compile(r"\b(beurs|hannover messe|foodtech|food ?tech|trade show|"
                r"exhibition|fair|hosts?|presenting at|op de beurs|op beurs|"
                r"exposition|expo\b|stand\b|standhouder|congres|conference)\b")),
    ("Award / Recognition",
     re.compile(r"\b(award|prijs\b|prize|winner|winnaar|gouden|best[e]? |top[- ]?100|"
                r"nomination|nominated|erkenning|erkend|shortlist|finalist)\b")),
    ("Sustainability / ESG",
     re.compile(r"\b(duurzaam|sustainab|green\b|circulair|circular|esg\b|co2|co-?2|"
                r"klimaat|climate|emissies?|energy transition|net[- ]?zero|"
                r"renewable|hernieuwbaar|energiebesparing|verduurzaming)\b")),
    ("Innovation / Technology / R&D",
     re.compile(r"\b(innovatie|innovation|technology|technologie|research|"
                r"development|r&?d\b|patent|breakthrough|doorbraak|whitepaper|"
                r"artificial intelligence|ai\b|machine learning|automation|"
                r"digitalisering|digitalisation|robotics|robot|industry 4)\b")),
    ("Facility / Expansion / Opening",
     re.compile(r"\b(nieuwe (locatie|vestiging|fabriek|kantoor)|new (facility|plant|factory|"
                r"office|location)|expansion|uitbreid|opening|opent|opens|"
                r"grand opening|relocation|verhuis|verhuizing|nieuwbouw|move to)\b")),
    ("Personnel / Appointment",
     re.compile(r"\b(new (ceo|cto|cfo|coo|director|president|managing director)|"
                r"appointment|appointed|benoem|aanstelling|opvolging|opvolger|"
                r"joins|welcomes|nieuwe directeur|nieuwe ceo|new cco)\b")),
    ("Financial / Results",
     re.compile(r"\b(omzet|revenue|results|financial|quarter|kwartaal|jaarverslag|"
                r"annual report|q[1-4]\b|profit|winst|earnings|forecast|"
                r"outlook|full[- ]year)\b")),
    ("Case study / Customer",
     re.compile(r"\b(case study|casestudy|customer story|klantverhaal|klantcase|"
                r"reference project|referentieproject|success story|succesverhaal|"
                r"customer case|project case|case:\b)\b")),
    ("Interview / Opinion / Column",
     re.compile(r"\b(interview|column|opinion|opinie|mening|meningsstuk|"
                r"question and answer|q&a\b|in gesprek met|aan het woord)\b")),
    ("Webinar / Training / Workshop",
     re.compile(r"\b(webinar|workshop|seminar|training|masterclass|course|cursus|"
                r"opleiding)\b")),
    ("Regulation / Policy / Legal",
     re.compile(r"\b(regulation|regulatory|wet|wetgeving|policy|beleid|richtlijn|"
                r"cbam|reach|compliance|nis2|gdpr|avg\b)\b")),
    ("Blog / Article marker",
     re.compile(r"\b(blog|nieuws\b|news\b|artikel|article|update|newsletter|"
                r"nieuwsbrief|leestijd|read time|min read)\b")),
    ("Navigation residue / non-title",
     re.compile(r"\b(read more|lees meer|meer weten|zum blogbeitrag|find out more|"
                r"add arrow_forward|continue reading|primary button|news primary)\b")),
]

OTHER = "Uncategorised / needs review"
NAV_LABEL = "Navigation residue / non-title"

# Exact-match nav-residue phrases (case-insensitive). Add to this list rather
# than re-writing regex — it's cheaper to maintain and less risky than tuning
# word-boundary matches that already fire on real titles.
NAV_EXACT: set[str] = {s.lower() for s in {
    # Read-more chrome in every language
    "read more", "lees meer", "lees verder", "lees artikel", "meer lezen",
    "weiterlesen", "en savoir plus", "más información", "mas informacion",
    "learn more", "meer weten", "find out more", "discover more",
    "bekijk meer", "bekijk", "bekijk de vacature", "bekijk deze vacature",
    "bekijk onze vacatures", "bekijk de volledige vacature",
    "meer informatie", "naar de vacature",
    # Job-board navigation
    "apply now", "solliciteer", "solliciteren", "open sollicitatie",
    "job advertisement", "applicant portal", "vacancies", "vacature",
    "vacant positions", "see position", "career", "careers",
    "initiativbewerbung", "unsolicited application", "download pdf",
    "inschrijven", "zoek een nieuwe baan", "search current opportunities",
    "find new jobs worldwide", "lees interview", "see all jobs", "view all",
    # Site navigation
    "gallerie", "gallery", "home", "contact", "about us", "over ons",
    "search", "zoeken", "meer nieuws", "all news",
    "newer posts", "older posts", "older post", "newer post",
    "english", "nederlands", "deutsch", "français", "espanol",
    # Menu-style job categories that leaked from a job-board sidebar
    "leger en beveiligingsservices", "retailpartner", "vastgoed", "techniek",
    "ondernemerschap", "ondersteuning", "onderzoek", "personeelszaken",
    "productmanagement", "carrières", "carrieres", "consultancy",
    "financiën", "financien", "gezondheidszorg", "helpcentrum",
    "juridisch", "kwaliteitsborging", "bedrijfsontwikkeling",
    # Article-list noise
    "0 reactie's", "0 reacties", "text link", "video", "arrow_forward",
    "primary button", "read news",
    # Country-name filters from a global careers page sidebar
    "united kingdom", "united states", "netherlands", "belgium", "germany",
    "france", "italy", "spain", "portugal", "sweden", "denmark", "norway",
    "finland", "poland", "romania", "hungary", "slovakia", "czechia",
    "czech republic", "austria", "switzerland", "ireland", "croatia",
    "slovenia", "estonia", "latvia", "lithuania", "china", "japan",
    "singapore", "india", "vietnam", "australia", "canada", "brazil",
    "mexico", "nordics", "benelux", "middle east", "asia pacific",
    "worldwide", "global", "europe",
    "mededeling voor werving- en selectiebureaus",
    "stages en afstudeeropdrachten", "beurzen",
    "blogs en artikelen", "sign up", "menno sappé",
}}

# Regex nav-residue: date-only titles, "add arrow_forward" from Material Icons,
# comment counts, etc.
NAV_REGEX: list[re.Pattern] = [
    # Dates (month names + optional day + year, or purely numeric)
    re.compile(r"^(january|february|march|april|may|june|july|august|"
               r"september|october|november|december)\s+\d{1,2},?\s*\d{2,4}$",
               re.I),
    re.compile(r"^(january|february|march|april|may|june|july|august|"
               r"september|october|november|december)\s+\d{2,4}$", re.I),
    re.compile(r"^(januari|februari|maart|april|mei|juni|juli|augustus|"
               r"september|oktober|november|december)\s+\d{1,2},?\s*\d{2,4}$",
               re.I),
    re.compile(r"^\d{1,2}[\-\./]\d{1,2}[\-\./]\d{2,4}$"),
    re.compile(r"^\d+\s+reactie'?s?$", re.I),
    re.compile(r"^add\s+arrow_forward$", re.I),
    re.compile(r"^(min\s+read|reading time|leestijd).*", re.I),
    re.compile(r"^\d+\s+min(uut(en)?|s)?\s+lez.*", re.I),
]


def is_nav_residue(title: str) -> bool:
    if not title:
        return False
    t = title.strip().lower()
    if t in NAV_EXACT:
        return True
    for rx in NAV_REGEX:
        if rx.match(t):
            return True
    return False

# Extra job rules for patterns spotted in the Uncategorised bucket.
# These extend JOB_RULES *before* the "Uncategorised" fallback.
JOB_RULES_EXTRA: list[tuple[str, re.Pattern]] = [
    ("Skilled trades / Craft",
     re.compile(r"\b(timmer(man)?|schoonmaker|schoonmaak|elektromonteur|electricien|"
                r"loodgieter|plumber|lasser|welder|metselaar|mason|stukadoor|"
                r"heftruck|forklift|chauffeur|driver|grondwerker|ground worker|"
                r"lasser|monteur\b|installateur|dakdekker|roofer)\b")),
    ("General staff / Medewerker",
     # `medewerker\b` matches any compound noun ending in `medewerker`
     # (e.g. `assemblagemedewerker`, `productiemedewerker`) — the Dutch language
     # glues role words together as one token.
     re.compile(r"medewerker\b|\b(employee|vakantiekracht|zzp|uitzendkracht)\b")),
    ("Editorial / Content",
     re.compile(r"\b(redacteur|editor|webredacteur|copywriter|content creator|"
                r"content writer|journalist)\b")),
    ("Project management",
     re.compile(r"\b(project (leader|manager|lead)|projectleider|projectmanager|"
                r"programma|programmemanager|projectcoordinator|werkvoorbereider|"
                r"planner|scheduler)\b")),
    ("Navigation residue / non-title",
     re.compile(r"^(explore elite|how to apply|locations|professions|training|"
                r"freelance|stages|bedrijfsontwikkeling|carri(è|e)res|consultancy|"
                r"financi(ë|e)n|gezondheidszorg|helpcentrum|juridisch|"
                r"kwaliteitsborging|leger|ondernemerschap|ondersteuning|onderzoek|"
                r"personeelszaken|productmanagement|apply now|solliciteer|"
                r"bekijk vacature|read more|lees meer|learn more|meer weten|"
                r"open sollicitatie|see all jobs|view all|gallerie|gallery|"
                r"arrow_forward)$")),
]

NEWS_RULES_EXTRA: list[tuple[str, re.Pattern]] = [
    ("Trade show / Event",
     re.compile(r"\b(op de\b|op\s+het\s+|at the\s+|bezoek\s+(ons\s+)?op|bezoek\s+"
                r"[a-z\|]+\s+op|blechexpo|sheet metal event|hannover messe|"
                r"foodtech|technishow|bouwbeurs|vsk|esef|foodspec|"
                r"aquatech|maintenance next|infratech|provada|empack|"
                r"solids|pumps ?[&+] ?valves)\b")),
    ("Customer story / Reference",
     re.compile(r"\b(kiest\s+(opnieuw\s+)?voor|het verhaal van|success story|"
                r"succesverhaal|customer case|klant case|klantcase|klantverhaal|"
                r"case:|reference|referentie|testimonial|installatie bij|"
                r"plaatsing\b|nieuwe installatie)\b")),
    ("Personnel / Employee story",
     re.compile(r"\b(werken bij|carri(è|e)re|the story of|meet our|onze mensen)\b")),
    ("Navigation residue / non-title",
     re.compile(r"^(gallerie|gallery|newsletter|see all|read all|view all|home|"
                r"contact|about us|search|zoeken|meer nieuws|all news|older posts?|"
                r"newer posts?)$")),
]


def normalise_title(t: str) -> str:
    """Undo the two biggest extractor artefacts:
      * CamelCase glue (e.g. "NieuwAdministratief medewerker" ->
        "Nieuw Administratief medewerker") introduced when scraped listings
        stitch several nodes together without whitespace;
      * letter/digit glue ("medewerkerAMSTERDAM" -> "medewerker AMSTERDAM").
    Then collapse repeated whitespace.
    """
    if not t:
        return ""
    t = re.sub(r"([a-z])([A-Z])", r"\1 \2", t)
    t = re.sub(r"([A-Z]{2,})([A-Z][a-z])", r"\1 \2", t)
    t = re.sub(r"([a-zA-Z])(\d)", r"\1 \2", t)
    t = re.sub(r"(\d)([a-zA-Z])", r"\1 \2", t)
    return re.sub(r"\s+", " ", t).strip()


def classify(title: str, rules: list[tuple[str, re.Pattern]]) -> str:
    if not title:
        return OTHER
    # Nav-residue check runs first: an "Apply now" button shouldn't be filed as
    # a Sales role just because it's on a sales team's page.
    if is_nav_residue(title):
        return NAV_LABEL
    t = normalise_title(title).lower()
    for name, rx in rules:
        if rx.search(t):
            return name
    return OTHER


# --------------------------------------------------------------- helpers --
def load_rows(name: str) -> list[dict]:
    with (ROOT / name).open() as f:
        return list(csv.DictReader(f))


jobs = load_rows("jobs_full.csv")
articles = load_rows("articles_full.csv")

# Nav-residue rule should stay the LAST specific rule (so real categories win
# when a title contains both a role word and a nav word). Extras are inserted
# *before* the existing nav-residue rule.
def merge_rules(base: list[tuple[str, re.Pattern]],
                extras: list[tuple[str, re.Pattern]]) -> list[tuple[str, re.Pattern]]:
    nav_idx = next((i for i, (n, _) in enumerate(base)
                    if n.startswith("Navigation residue")), len(base))
    return base[:nav_idx] + extras + base[nav_idx:]


JOB_RULES = merge_rules(JOB_RULES, JOB_RULES_EXTRA)
NEWS_RULES = merge_rules(NEWS_RULES, NEWS_RULES_EXTRA)

for row in jobs:
    row["category"] = classify(row["title"], JOB_RULES)
for row in articles:
    row["category"] = classify(row["title"], NEWS_RULES)


# ------------------------------------------------------------- styling ---
def header_font(): return Font(bold=True, color="FFFFFF", size=11, name="Calibri")
def body_font():   return Font(color=INK, size=10, name="Calibri")
def muted_font():  return Font(color=MUTED, size=10, name="Calibri", italic=True)
def big_font():    return Font(bold=True, color=BRAND_DARK, size=14, name="Calibri")


def fill(hex_color): return PatternFill("solid", fgColor=hex_color)


def style_header_row(ws, row_idx: int, ncols: int, color=BRAND_DARK):
    for c in range(1, ncols + 1):
        cell = ws.cell(row=row_idx, column=c)
        cell.font = header_font()
        cell.fill = fill(color)
        cell.alignment = Alignment(vertical="center", horizontal="left",
                                   wrap_text=True)
        cell.border = BOX
    ws.row_dimensions[row_idx].height = 26


def set_col_widths(ws, widths):
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w


def zebra_stripe(ws, first_row: int, last_row: int, ncols: int):
    for r in range(first_row, last_row + 1):
        if (r - first_row) % 2 == 1:
            for c in range(1, ncols + 1):
                ws.cell(row=r, column=c).fill = fill(STRIPE)


# --------------------------------------------------------------- workbook
wb = Workbook()

# ============ Sheet: README =============================================
ws = wb.active
ws.title = "README"
ws.sheet_view.showGridLines = False

ws["A1"] = "Hi-Engineer manual-review workbook"
ws["A1"].font = Font(bold=True, size=18, color=BRAND_DARK, name="Calibri")
ws.merge_cells("A1:D1")

ws["A2"] = ("Sheets for reviewing every job and news item captured by the "
            "Hi-Engineer platform. Mark each row Relevant? = Yes / No / Maybe "
            "and use the Notes column freely.")
ws["A2"].font = body_font()
ws["A2"].alignment = Alignment(wrap_text=True, vertical="top")
ws.merge_cells("A2:D2")
ws.row_dimensions[2].height = 44

# KPI band
kpis = [
    ("Total job listings",   f"{len(jobs):,}"),
    ("Total news articles",  f"{len(articles):,}"),
    ("Distinct job titles",  f"{len({j['title'] for j in jobs}):,}"),
    ("Distinct article titles", f"{len({a['title'] for a in articles}):,}"),
    ("Job categories used",   f"{len({j['category'] for j in jobs}):,}"),
    ("News categories used",  f"{len({a['category'] for a in articles}):,}"),
]
for i, (label, val) in enumerate(kpis):
    r = 4 + i
    ws.cell(row=r, column=1, value=label).font = body_font()
    ws.cell(row=r, column=2, value=val).font = big_font()

ws["A11"] = "Sheets in this workbook"
ws["A11"].font = Font(bold=True, size=13, color=BRAND_DARK, name="Calibri")

sheet_desc = [
    ("Jobs — by category",
     "Aggregated view of jobs grouped by derived category. "
     "One row per category with count, top titles and companies. "
     "Use the Relevant? column to accept or reject entire categories at once."),
    ("Jobs — all listings",
     "Every job listing (930 rows) with title, company, URL, derived category, "
     "and blank Relevant? + Notes columns. Filters enabled — filter by category "
     "then bulk-flag."),
    ("News — by category",
     "Same aggregated view for news / articles. 2,328 articles bucketed."),
    ("News — all listings",
     "Full article list with title, company, URL, derived category, "
     "Relevant? and Notes columns."),
    ("Categories rulebook",
     "The keyword rules used to bucket titles into categories. Order matters — "
     "first match wins. Adjust or extend to re-classify."),
]
for i, (name, desc) in enumerate(sheet_desc):
    r = 12 + i
    ws.cell(row=r, column=1, value=name).font = Font(bold=True, size=11,
                                                     color=INK, name="Calibri")
    ws.cell(row=r, column=2, value=desc).font = body_font()
    ws.cell(row=r, column=2).alignment = Alignment(wrap_text=True, vertical="top")
    ws.row_dimensions[r].height = 42

ws["A19"] = ("Relevant? column: leave blank if undecided. Suggested values: "
             "Yes, No, Maybe. Use Excel's data-validation drop-down if you like.")
ws["A19"].font = muted_font()
ws["A19"].alignment = Alignment(wrap_text=True, vertical="top")
ws.merge_cells("A19:D19")

set_col_widths(ws, [30, 90])


# ============ helper: build the aggregate view ==========================
def build_agg_sheet(ws, rows, header_color):
    by_cat: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_cat[r["category"]].append(r)

    headers = ["Category", "Count", "% of total",
               "Top 3 titles", "Top 3 companies",
               "Sample URL", "Relevant?", "Notes"]
    ws.append(headers)
    style_header_row(ws, 1, len(headers), header_color)

    total = len(rows)
    # Sort by count desc, "Uncategorised" and "Nav residue" pushed to end
    def sort_key(kv):
        name, items = kv
        priority = 2 if name.startswith(("Nav", "Uncat")) else 1
        return (priority, -len(items))
    sorted_items = sorted(by_cat.items(), key=sort_key)

    row_idx = 2
    for cat, items in sorted_items:
        titles = Counter(r["title"] for r in items).most_common(3)
        top_titles = "\n".join(f"• {t} ({n:,})" for t, n in titles)
        companies = Counter(r["company"] for r in items).most_common(3)
        top_companies = "\n".join(f"• {c} ({n:,})" for c, n in companies)
        sample_url = next((r["url"] for r in items if r["url"]), "")
        pct = round(100.0 * len(items) / max(total, 1), 1)

        ws.cell(row=row_idx, column=1, value=cat)
        ws.cell(row=row_idx, column=2, value=len(items))
        ws.cell(row=row_idx, column=3, value=pct)
        ws.cell(row=row_idx, column=4, value=top_titles)
        ws.cell(row=row_idx, column=5, value=top_companies)
        ws.cell(row=row_idx, column=6, value=sample_url)
        ws.cell(row=row_idx, column=7, value="")  # Relevant?
        ws.cell(row=row_idx, column=8, value="")  # Notes

        for c in range(1, len(headers) + 1):
            cell = ws.cell(row=row_idx, column=c)
            cell.alignment = Alignment(wrap_text=True, vertical="top")
            cell.border = BOX
            cell.font = body_font()

        # highlight "residue"/"other" rows in a muted tone
        if cat.startswith(("Nav", "Uncat")):
            for c in range(1, len(headers) + 1):
                ws.cell(row=row_idx, column=c).fill = fill(LIGHT)
                ws.cell(row=row_idx, column=c).font = muted_font()

        ws.row_dimensions[row_idx].height = 60
        row_idx += 1

    # Totals row
    total_r = row_idx
    ws.cell(row=total_r, column=1, value="TOTAL").font = Font(bold=True,
                                                              color=INK,
                                                              name="Calibri")
    ws.cell(row=total_r, column=2, value=total).font = Font(bold=True,
                                                            color=INK,
                                                            name="Calibri")
    ws.cell(row=total_r, column=3, value=100.0).font = Font(bold=True,
                                                            color=INK,
                                                            name="Calibri")
    for c in range(1, len(headers) + 1):
        ws.cell(row=total_r, column=c).fill = fill(LIGHT)
        ws.cell(row=total_r, column=c).border = BOX

    set_col_widths(ws, [30, 8, 10, 55, 40, 55, 12, 40])
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{total_r - 1}"


# ============ Sheet: Jobs — by category =================================
ws_jc = wb.create_sheet("Jobs — by category")
build_agg_sheet(ws_jc, jobs, BRAND_DARK)


# ============ Sheet: Jobs — all listings ================================
def build_detail_sheet(ws, rows, header_color):
    headers = ["Category", "Title", "Company", "URL", "Source page",
               "First seen", "Relevant?", "Notes"]
    ws.append(headers)
    style_header_row(ws, 1, len(headers), header_color)

    # Sort by (category, company, title) so scanning is easy
    ordered = sorted(rows, key=lambda r: (r["category"], r["company"].lower(),
                                          r["title"].lower()))
    for i, r in enumerate(ordered, start=2):
        ws.cell(row=i, column=1, value=r["category"])
        ws.cell(row=i, column=2, value=r["title"])
        ws.cell(row=i, column=3, value=r["company"])
        ws.cell(row=i, column=4, value=r["url"])
        ws.cell(row=i, column=5, value=r["source_page"])
        ws.cell(row=i, column=6, value=r["first_seen"])
        ws.cell(row=i, column=7, value="")
        ws.cell(row=i, column=8, value="")
        for c in range(1, len(headers) + 1):
            cell = ws.cell(row=i, column=c)
            cell.font = body_font()
            cell.border = BOX
            if c in (2, 3, 4, 5, 8):
                cell.alignment = Alignment(wrap_text=False, vertical="top")
            else:
                cell.alignment = Alignment(vertical="top")

    zebra_stripe(ws, 2, 1 + len(ordered), len(headers))
    set_col_widths(ws, [28, 55, 32, 55, 40, 12, 12, 30])
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{1 + len(ordered)}"


ws_jd = wb.create_sheet("Jobs — all listings")
build_detail_sheet(ws_jd, jobs, BRAND_DARK)


# ============ Sheet: News — by category =================================
ws_nc = wb.create_sheet("News — by category")
build_agg_sheet(ws_nc, articles, BRAND)


# ============ Sheet: News — all listings ================================
ws_nd = wb.create_sheet("News — all listings")
build_detail_sheet(ws_nd, articles, BRAND)


# ============ Sheet: Categories rulebook ================================
ws_rb = wb.create_sheet("Categories rulebook")
ws_rb.sheet_view.showGridLines = False
ws_rb["A1"] = ("Categories are assigned by matching each title (lower-cased) "
               "against the regexes below, top-down. First match wins. "
               "'Uncategorised' means no regex matched.")
ws_rb["A1"].font = body_font()
ws_rb["A1"].alignment = Alignment(wrap_text=True, vertical="top")
ws_rb.merge_cells("A1:C1")
ws_rb.row_dimensions[1].height = 40

def dump_rules(ws, start_row, label, rules):
    ws.cell(row=start_row, column=1, value=label).font = Font(bold=True, size=13,
                                                              color=BRAND_DARK,
                                                              name="Calibri")
    headers = ["Priority", "Category", "Regex pattern"]
    for c, h in enumerate(headers, 1):
        cell = ws.cell(row=start_row + 1, column=c, value=h)
        cell.font = header_font()
        cell.fill = fill(BRAND_DARK)
        cell.alignment = Alignment(vertical="center")
        cell.border = BOX
    ws.row_dimensions[start_row + 1].height = 24
    for i, (name, rx) in enumerate(rules, 1):
        r = start_row + 1 + i
        ws.cell(row=r, column=1, value=i)
        ws.cell(row=r, column=2, value=name)
        ws.cell(row=r, column=3, value=rx.pattern)
        for c in range(1, 4):
            ws.cell(row=r, column=c).font = body_font()
            ws.cell(row=r, column=c).border = BOX
            ws.cell(row=r, column=c).alignment = Alignment(wrap_text=True,
                                                            vertical="top")
        ws.row_dimensions[r].height = 30
    return start_row + 1 + len(rules)

end_r = dump_rules(ws_rb, 3, "Job rules", JOB_RULES)
dump_rules(ws_rb, end_r + 3, "News rules", NEWS_RULES)
set_col_widths(ws_rb, [10, 34, 90])


# ---------------------------------------------------------------- write --
wb.save(OUT)
print(f"Wrote {OUT}  ({OUT.stat().st_size / 1024:.1f} KB)")

# quick stats print
print(f"  jobs categorised:      {len(jobs):,}")
print(f"  articles categorised:  {len(articles):,}")
print(f"  distinct job cats:     {len({j['category'] for j in jobs})}")
print(f"  distinct news cats:    {len({a['category'] for a in articles})}")

from collections import Counter
print("\n  jobs by category:")
for k, v in Counter(j["category"] for j in jobs).most_common():
    print(f"    {v:>4}  {k}")
print("\n  news by category:")
for k, v in Counter(a["category"] for a in articles).most_common():
    print(f"    {v:>4}  {k}")
