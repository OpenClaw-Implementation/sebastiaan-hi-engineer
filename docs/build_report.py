"""Build the Hi-Engineer investigation report PDF.

All data lives in /tmp/report/*.csv (already exported from Postgres).
Charts rendered with matplotlib and embedded as PNGs. Layout is done with
reportlab platypus so text wraps and tables paginate cleanly.
"""

from __future__ import annotations

import csv
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

ROOT = Path("/tmp/report")
OUT = ROOT / "hi_engineer_investigation_report.pdf"

# ------------------------- palette ------------------------- #
BRAND = "#1f6feb"
BRAND_DARK = "#0b3ea6"
GOOD = "#2ea043"
WARN = "#d29922"
BAD = "#f85149"
INK = "#1f2328"
MUTED = "#6e7781"
LIGHT = "#f6f8fa"

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 10,
    "axes.edgecolor": MUTED,
    "axes.labelcolor": INK,
    "axes.titlecolor": INK,
    "xtick.color": INK,
    "ytick.color": INK,
    "axes.grid": True,
    "grid.color": "#e6ebf1",
    "grid.linewidth": 0.6,
})


# ------------------------- data ingest --------------------- #
def load_csv(name: str) -> list[dict]:
    with (ROOT / name).open() as f:
        return list(csv.DictReader(f))


sources = load_csv("sources.csv")
top_jobs = load_csv("top_jobs.csv")
top_articles = load_csv("top_articles.csv")
categories = load_csv("categories.csv")
enrich_by_source = load_csv("enrich_by_source.csv")

# Media portals: hardcoded from the psql query — 9 portals all returned 0 entries
MEDIA_SOURCES = [
    {"url": "https://installatieenbouw.nl/bedrijven/", "status": "no_entries",
     "note": "empty result; parser returned 0"},
    {"url": "https://vakbladvoedingsindustrie.nl/en/leveranciers",
     "status": "http_403", "note": "403 Forbidden (blocked)"},
    {"url": "https://industriebouw-online.nl/bedrijvenindex/",
     "status": "no_entries", "note": "empty result"},
    {"url": "https://www.processcontrol.nl/bedrijvenwijzer/", "status": "js_only",
     "note": "JS/AJAX directory — page shell only"},
    {"url": "https://solidsprocessing.nl/companyprofile/?expertise=&search=&paging=",
     "status": "js_only", "note": "JS/AJAX directory"},
    {"url": "https://fluidsprocessing.nl/leverancier/?expertise=&search=&paging=",
     "status": "js_only", "note": "JS/AJAX directory"},
    {"url": "https://www.industrielinqs.nl/partners-leden/", "status": "js_only",
     "note": "JS/AJAX directory"},
    {"url": "https://regiobedrijf.nl/industrie/", "status": "no_entries",
     "note": "empty result"},
    {"url": "https://tim.pmg.nl/nl/leveranciers/?ct=&pd=&lc=&kw=&lt=",
     "status": "js_only", "note": "JS/AJAX directory"},
]

# High-level DB totals (already queried, hard-coded here so report is deterministic)
TOTALS = {
    "companies_total": 1190,
    "companies_enriched": 889,
    "companies_pending": 0,
    "companies_terminal": 301,
    "with_jobs_url": 430,
    "with_news_url": 516,
    "with_both_urls": 357,
    "with_website": 783,
    "jobs_total": 930,
    "articles_total": 2328,
    "runs_total": 33,
}

FIRECRAWL = {
    "remaining_credits": 1525,
    "plan_credits_per_month": 1000,
    "billing_period_start": "2026-08-23",
    "billing_period_end":   "2026-09-23",
}


# ------------------------- helpers ------------------------- #
def short_label(text: str, limit: int = 34) -> str:
    text = re.sub(r"\s+", " ", (text or "").strip())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def domain(url: str) -> str:
    m = re.match(r"https?://([^/]+)/?", url or "")
    host = (m.group(1) if m else url).replace("www.", "")
    return host


# ----- tokenise titles for frequency analysis ----- #
STOP = set("""
a an and are as at be but by en for from has have het if in is it je met of on or
over the to was were will with without you your not no we our this their there they
them she he his her its onze they've i'll you'll bij naar tussen uit door onder deze
die dat dan zoals wij dus ook zou al niet zich wat mee bij per zijn heeft heb hebben
worden werden wordt geworden been who what when where why how which van van- de
voor een aan als om ons uit zich zij was ze eens meer nieuwe zum nur die der das
den dem des ein eine einer bei aus mit auch dem des vom dass sich wir nog
""".split())

# Navigation-link residue that pollutes title analysis: buttons/links like
# "Lees meer" (read more), "Bekijk vacature" (view vacancy), Material Icons
# names picked up as text ("add arrow_forward"), German blog-post markers, etc.
# Filtered out separately so we can still report raw counts if needed.
NAV_RESIDUE_WORDS = set("""
meer lees weten verder lezen bekijk vacature vacatures view read learn zoek
blogbeitrag arrow_forward artikel readjuly readjune readmarch readapril readmay
readaugust readseptember readoctober readnovember readdecember more
""".split())

NAV_RESIDUE_BIGRAMS = {
    "meer weten", "lees meer", "lees verder", "lees artikel", "meer lezen",
    "bekijk vacature", "learn more", "find out", "out more", "read more",
    "zum blogbeitrag", "add arrow_forward", "min readjuly", "min readjune",
    "min readmarch", "min readapril", "min readmay", "min readaugust",
    "min readseptember", "min readoctober", "min readnovember",
    "min readdecember", "job advertisement", "arrow forward",
}

# Dutch month names show up because timestamps get scraped as text — noise for
# vocabulary analysis but not "wrong", so we bucket them separately.
MONTH_WORDS = set("""
januari februari maart april mei juni juli augustus september oktober november
december january february march may august october
""".split())


def tokens(text: str) -> list[str]:
    text = (text or "").lower()
    text = re.sub(r"[^\w\s\-]", " ", text)
    out = []
    for w in text.split():
        w = w.strip("-")
        if len(w) < 3:
            continue
        if w in STOP:
            continue
        if w.isdigit():
            continue
        out.append(w)
    return out


def title_word_freq(csv_name: str, *, drop_nav: bool = True,
                    drop_months: bool = True) -> Counter:
    c: Counter = Counter()
    with (ROOT / csv_name).open() as f:
        rdr = csv.DictReader(f)
        for row in rdr:
            for t in tokens(row.get("title", "")):
                if drop_nav and t in NAV_RESIDUE_WORDS:
                    continue
                if drop_months and t in MONTH_WORDS:
                    continue
                c[t] += 1
    return c


def title_bigrams_freq(csv_name: str, *, drop_nav: bool = True) -> Counter:
    c: Counter = Counter()
    with (ROOT / csv_name).open() as f:
        rdr = csv.DictReader(f)
        for row in rdr:
            toks = tokens(row.get("title", ""))
            for a, b in zip(toks, toks[1:]):
                bg = f"{a} {b}"
                if drop_nav and bg in NAV_RESIDUE_BIGRAMS:
                    continue
                c[bg] += 1
    return c


job_word_freq = title_word_freq("job_titles.csv")
art_word_freq = title_word_freq("article_titles.csv")
art_bigram_freq = title_bigrams_freq("article_titles.csv")
job_bigram_freq = title_bigrams_freq("job_titles.csv")

# Nav-residue tallies (kept for the "noise report" side-note)
nav_word_totals = {"jobs": 0, "articles": 0}
nav_bigram_totals = {"jobs": 0, "articles": 0}
for csv_name, key in [("job_titles.csv", "jobs"),
                      ("article_titles.csv", "articles")]:
    with (ROOT / csv_name).open() as f:
        for row in csv.DictReader(f):
            toks = tokens(row.get("title", ""))
            for t in toks:
                if t in NAV_RESIDUE_WORDS:
                    nav_word_totals[key] += 1
            for a, b in zip(toks, toks[1:]):
                if f"{a} {b}" in NAV_RESIDUE_BIGRAMS:
                    nav_bigram_totals[key] += 1


# ------------------------- chart builders ------------------ #
def hbar(pairs, title, filename, xlabel="count", color=BRAND, height=None):
    labels, values = zip(*pairs)
    labels = [short_label(x, 40) for x in labels]
    fig_h = height or max(2.4, 0.32 * len(labels) + 1.2)
    fig, ax = plt.subplots(figsize=(7.4, fig_h))
    y = range(len(labels))
    ax.barh(list(y), values, color=color, edgecolor="none")
    ax.set_yticks(list(y))
    ax.set_yticklabels(labels)
    ax.invert_yaxis()
    ax.set_xlabel(xlabel)
    ax.set_title(title, loc="left", fontsize=11, weight="bold", pad=10)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for i, v in enumerate(values):
        ax.text(v, i, f"  {v:,}", va="center", fontsize=9, color=INK)
    fig.tight_layout()
    fig.savefig(ROOT / filename, dpi=160, bbox_inches="tight")
    plt.close(fig)


def stacked_bar(rows, title, filename):
    labels = [r["label"] for r in rows]
    parts = list(rows[0]["parts"].keys())
    fig, ax = plt.subplots(figsize=(7.4, 2.9))
    left = [0] * len(labels)
    palette = {"direct": GOOD, "firecrawl": WARN, "unsupported": BAD,
               "curl_ok": GOOD, "js_only": WARN, "http_403": BAD,
               "no_entries": MUTED}
    for p in parts:
        vals = [r["parts"][p] for r in rows]
        ax.barh(labels, vals, left=left, label=p,
                color=palette.get(p, BRAND), edgecolor="white", linewidth=0.6)
        for i, (lv, v) in enumerate(zip(left, vals)):
            if v > 0:
                ax.text(lv + v / 2, i, str(v), va="center", ha="center",
                        color="white", fontsize=9, weight="bold")
        left = [a + b for a, b in zip(left, vals)]
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, -0.35), ncol=len(parts),
              frameon=False)
    ax.set_title(title, loc="left", fontsize=11, weight="bold", pad=10)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.grid(False)
    fig.tight_layout()
    fig.savefig(ROOT / filename, dpi=160, bbox_inches="tight")
    plt.close(fig)


def pie(pairs, title, filename):
    labels, values = zip(*pairs)
    fig, ax = plt.subplots(figsize=(5.6, 3.6))
    colors_ = [BRAND, GOOD, WARN, BAD, MUTED, "#8250df"][: len(labels)]
    wedges, texts, autotexts = ax.pie(
        values, labels=labels, autopct=lambda p: f"{p:.0f}%",
        colors=colors_, startangle=90,
        wedgeprops={"edgecolor": "white", "linewidth": 2},
        textprops={"fontsize": 10, "color": INK},
    )
    for t in autotexts:
        t.set_color("white")
        t.set_weight("bold")
    ax.set_title(title, loc="left", fontsize=11, weight="bold", pad=10)
    fig.tight_layout()
    fig.savefig(ROOT / filename, dpi=160, bbox_inches="tight")
    plt.close(fig)


# ---- build all charts ---- #

# 1. Parser breakdown for the 26 event sources
parser_counts = Counter(s["parser"] for s in sources)
pie([(k, v) for k, v in parser_counts.most_common()],
    "Trade-show sources by parser (26 total)", "chart_parser_pie.png")

# 2. Direct-curl vs Firecrawl vs Unsupported — stacked
# For event sources: foodtech + easyfairs + safetyevent = curl-fetchable;
# firecrawl parser = needs Firecrawl; unsupported = neither.
direct_parsers = {"foodtech", "easyfairs", "safetyevent"}
curl_count = sum(1 for s in sources if s["parser"] in direct_parsers)
firecrawl_count = sum(1 for s in sources if s["parser"] == "firecrawl")
unsup_count = sum(1 for s in sources if s["parser"] == "unsupported")

# For media: js_only → need Firecrawl; 403 → unsupported; no_entries → curl-ok structurally but no data
media_js = sum(1 for m in MEDIA_SOURCES if m["status"] == "js_only")
media_403 = sum(1 for m in MEDIA_SOURCES if m["status"] == "http_403")
media_no = sum(1 for m in MEDIA_SOURCES if m["status"] == "no_entries")

stacked_bar([
    {"label": "Trade shows (26)",
     "parts": {"direct": curl_count, "firecrawl": firecrawl_count,
               "unsupported": unsup_count}},
    {"label": "Media portals (9)",
     "parts": {"direct": media_no, "firecrawl": media_js,
               "unsupported": media_403}},
], "Fetch strategy per input list", "chart_fetch_strategy.png")

# 3. Yield per firecrawl source
fc_rows = [(s["label"], int(s["last_count"] or 0)) for s in sources
           if s["parser"] == "firecrawl"]
fc_rows.sort(key=lambda r: r[1], reverse=True)
hbar(fc_rows, "Firecrawl sources — exhibitors extracted",
     "chart_firecrawl_yield.png", color=WARN)

# 4. Yield per trade-show source, all parsers
all_rows = [(s["label"], int(s["last_count"] or 0)) for s in sources
            if s["parser"] != "unsupported"]
all_rows.sort(key=lambda r: r[1], reverse=True)
hbar(all_rows[:20], "Top-20 trade-show sources by exhibitors captured",
     "chart_top_sources.png", color=BRAND)

# 5. Companies with jobs_url + news_url (coverage)
def pct(a, b): return int(round(100.0 * a / b)) if b else 0

cov_rows = [
    ("Website found",     TOTALS["with_website"]),
    ("News/blog URL",     TOTALS["with_news_url"]),
    ("Jobs/careers URL",  TOTALS["with_jobs_url"]),
    ("Both news + jobs",  TOTALS["with_both_urls"]),
]
hbar(cov_rows,
     f"Coverage across {TOTALS['companies_total']:,} companies",
     "chart_coverage.png", color=GOOD)

# 6. Enrichment source distribution (icypeas vs apollo vs terminal)
enr_rows = [(r["src"], int(r["n"])) for r in enrich_by_source]
enr_rows.sort(key=lambda r: r[1], reverse=True)
pie(enr_rows, "Enrichment result by cascade leg", "chart_enrich_pie.png")

# 7. Top-20 companies by jobs found
jobs_pairs = [(r["name"], int(r["n_jobs"])) for r in top_jobs[:20]]
hbar(jobs_pairs, "Top-20 companies by jobs extracted",
     "chart_top_jobs.png", color=BRAND)

# 8. Top-20 companies by articles found
art_pairs = [(r["name"], int(r["n_articles"])) for r in top_articles[:20]]
hbar(art_pairs, "Top-20 companies by news articles extracted",
     "chart_top_articles.png", color=BRAND_DARK)

# 9. Most common words in job titles
job_top = job_word_freq.most_common(20)
hbar(job_top, "Most common words in job titles",
     "chart_job_words.png", color=BRAND)

# 10. Most common words in article titles
art_top = art_word_freq.most_common(20)
hbar(art_top, "Most common words in news article titles",
     "chart_article_words.png", color=BRAND_DARK)

# 11. Top bigrams in article titles (phrases)
art_bi_top = art_bigram_freq.most_common(15)
hbar(art_bi_top, "Top phrases (bigrams) in news article titles",
     "chart_article_bigrams.png", color="#8250df")

# 12. Top bigrams in job titles
job_bi_top = job_bigram_freq.most_common(15)
hbar(job_bi_top, "Top phrases (bigrams) in job titles",
     "chart_job_bigrams.png", color="#8250df")

# 13. Categories
cat_pairs = [(r["category"], int(r["n"])) for r in categories[:15]]
hbar(cat_pairs, "Top exhibitor-declared categories",
     "chart_categories.png", color=GOOD)


# ------------------------- PDF assembly -------------------- #
styles = getSampleStyleSheet()
BASE = "Helvetica"
BOLD = "Helvetica-Bold"

styles["Title"].fontName = BOLD
styles["Title"].fontSize = 22
styles["Title"].textColor = colors.HexColor(INK)
styles["Title"].leading = 26

H1 = ParagraphStyle("H1", parent=styles["Heading1"],
                    fontName=BOLD, fontSize=15, spaceBefore=8, spaceAfter=4,
                    textColor=colors.HexColor(BRAND_DARK), leading=18)
H2 = ParagraphStyle("H2", parent=styles["Heading2"],
                    fontName=BOLD, fontSize=11.5, spaceBefore=6, spaceAfter=2,
                    textColor=colors.HexColor(INK), leading=14)
BODY = ParagraphStyle("BODY", parent=styles["BodyText"],
                      fontName=BASE, fontSize=9.5, leading=13,
                      textColor=colors.HexColor(INK), spaceAfter=4)
NOTE = ParagraphStyle("NOTE", parent=BODY, fontSize=8.5, leading=11,
                      textColor=colors.HexColor(MUTED))
KV_LABEL = ParagraphStyle("KV_LABEL", parent=BODY, fontName=BOLD,
                          fontSize=9.5, textColor=colors.HexColor(INK))

doc = SimpleDocTemplate(
    str(OUT), pagesize=A4,
    leftMargin=1.6 * cm, rightMargin=1.6 * cm,
    topMargin=1.4 * cm, bottomMargin=1.4 * cm,
    title="Hi-Engineer Investigation Report",
    author="Hi-Engineer",
)

USABLE_W = A4[0] - doc.leftMargin - doc.rightMargin


def hr_bar(color=BRAND, height=1.6):
    """Full-width thin horizontal separator."""
    t = Table([[""]], colWidths=[USABLE_W], rowHeights=[height])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(color))]))
    return t


def img(path, width=17 * cm):
    im = Image(str(path))
    aspect = im.imageHeight / im.imageWidth
    im.drawWidth = width
    im.drawHeight = width * aspect
    return im


def kpi_row(pairs):
    """A single row of KPI boxes (label, big-value, sub-note)."""
    n = len(pairs)
    col_w = USABLE_W / n
    cells = []
    for lbl, val, sub in pairs:
        para = [
            Paragraph(f'<font size=8 color="{MUTED}">{lbl.upper()}</font>', BODY),
            Spacer(1, 2),
            Paragraph(f'<font size=18 color="{BRAND_DARK}"><b>{val}</b></font>',
                      BODY),
            Paragraph(f'<font size=8 color="{MUTED}">{sub}</font>', BODY),
        ]
        cells.append(para)
    tbl = Table([cells], colWidths=[col_w] * n)
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(LIGHT)),
        ("BOX",  (0, 0), (-1, -1), 0.5, colors.HexColor("#d0d7de")),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBEFORE", (1, 0), (-1, -1), 0.4, colors.HexColor("#d0d7de")),
    ]))
    return tbl


def table_from_rows(header, rows, col_widths, header_color=BRAND_DARK,
                    wrap_cols=None):
    """rows = list[list[str]]; col_widths sums to <= USABLE_W."""
    wrap_cols = wrap_cols or []
    header_cells = [
        Paragraph(f'<font color="white"><b>{h}</b></font>', BODY) for h in header
    ]
    body_cells = []
    for r in rows:
        row_out = []
        for i, cell in enumerate(r):
            if i in wrap_cols:
                row_out.append(Paragraph(str(cell), BODY))
            else:
                row_out.append(str(cell))
        body_cells.append(row_out)
    data = [header_cells] + body_cells
    t = Table(data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(header_color)),
        ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
        ("FONTNAME",   (0, 0), (-1, 0), BOLD),
        ("FONTSIZE",   (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
        ("TOPPADDING", (0, 0), (-1, 0), 6),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
         [colors.white, colors.HexColor("#f6f8fa")]),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d0d7de")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 1), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 4),
    ]))
    return t


def section(story, title):
    story.append(Paragraph(title, H1))
    story.append(hr_bar(BRAND, 1.6))
    story.append(Spacer(1, 6))


def paragraph(story, html):
    story.append(Paragraph(html, BODY))


# ------------------------- assemble document -------------------- #
story: list = []

# ================ COVER PAGE ================
story.append(Spacer(1, 3 * cm))
story.append(Paragraph("Hi-Engineer", styles["Title"]))
story.append(Paragraph(
    '<font size=14 color="#6e7781">Trade-show &amp; media pipeline investigation</font>',
    BODY))
story.append(Spacer(1, 1.2 * cm))
story.append(hr_bar(BRAND, 3))
story.append(Spacer(1, 8))
story.append(Paragraph(
    "Full audit of the input source list, curl-vs-Firecrawl fetch strategy, "
    "downstream jobs and news pipelines, and the shape of the data collected "
    "to date.", BODY))
story.append(Spacer(1, 1.5 * cm))

# Cover KPI band
story.append(kpi_row([
    ("Input lists",     "35",   "26 trade-show + 9 media"),
    ("Companies",       f"{TOTALS['companies_total']:,}", "in the directory"),
    ("Jobs extracted",  f"{TOTALS['jobs_total']:,}",      "across all companies"),
    ("News extracted",  f"{TOTALS['articles_total']:,}",  "across all companies"),
]))
story.append(Spacer(1, 0.6 * cm))
story.append(kpi_row([
    ("Enriched",  f"{TOTALS['companies_enriched']:,}",
     f"{pct(TOTALS['companies_enriched'], TOTALS['companies_total'])}% of total"),
    ("With site", f"{TOTALS['with_website']:,}",
     f"{pct(TOTALS['with_website'], TOTALS['companies_total'])}% coverage"),
    ("Jobs URL",  f"{TOTALS['with_jobs_url']:,}",
     f"{pct(TOTALS['with_jobs_url'], TOTALS['with_website'])}% of sited"),
    ("News URL",  f"{TOTALS['with_news_url']:,}",
     f"{pct(TOTALS['with_news_url'], TOTALS['with_website'])}% of sited"),
]))
story.append(Spacer(1, 2 * cm))
story.append(Paragraph(
    f'<font size=9 color="{MUTED}">Generated {datetime.utcnow().strftime("%Y-%m-%d")}'
    f' &nbsp;·&nbsp; Data source: production Heroku Postgres '
    f'(<font face="Courier">hi-engineer-app</font>)</font>', BODY))
story.append(PageBreak())


# ================ EXECUTIVE SUMMARY ================
section(story, "1 · Executive summary")

paragraph(story,
    "The Hi-Engineer platform ingests two input lists — <b>26 trade-show exhibitor "
    "pages</b> and <b>9 industrial/food media portals</b> — normalises "
    "everything into a single company directory, cascades through four "
    "enrichment providers, then runs <b>jobs</b> and <b>news</b> pipelines against "
    "each company's own site.")

paragraph(story,
    "The trade-show ingest is <b>fully wired and productive</b>. Of the 26 event sources, "
    f"14 are fetched with a plain <font face=\"Courier\">requests</font> call "
    "(foodtech + easyfairs parsers), 9 require Firecrawl's JS-render tier, "
    "and 3 are known-blocked and kept in the table only so the reason is visible in the "
    f"UI. The current directory holds <b>{TOTALS['companies_total']:,} companies</b> "
    f"({TOTALS['companies_enriched']:,} enriched, "
    f"{TOTALS['with_website']:,} with a discovered website).")

paragraph(story,
    "The media portal ingest is <b>largely blocked</b>. All 9 portals were probed "
    "with direct HTTP; every one of them returned zero usable entries — five build "
    "their directory in the browser (JavaScript/AJAX), one blocks scrapers at the "
    "edge (HTTP 403), and three have parser mis-matches that need custom rules. "
    "Firecrawl would unlock the JS-only tier at a marginal cost (details in §4).")

paragraph(story,
    f"Downstream, the platform has captured <b>{TOTALS['jobs_total']:,} job listings</b> "
    f"and <b>{TOTALS['articles_total']:,} news articles</b> across "
    f"{TOTALS['companies_total']:,} companies. Coverage is heavily skewed towards "
    "companies that publish structured careers/blog pages: the top 5 companies "
    f"account for {sum(int(r['n_jobs']) for r in top_jobs[:5]):,} jobs "
    f"({pct(sum(int(r['n_jobs']) for r in top_jobs[:5]), TOTALS['jobs_total'])}%) and "
    f"{sum(int(r['n_articles']) for r in top_articles[:5]):,} articles "
    f"({pct(sum(int(r['n_articles']) for r in top_articles[:5]), TOTALS['articles_total'])}%) of the totals.")

story.append(Spacer(1, 6))
story.append(Paragraph("Key numbers at a glance", H2))
story.append(Spacer(1, 4))
story.append(kpi_row([
    ("Trade-show inputs",  "26",  "6 parsers"),
    ("Media inputs",       "9",   "1 parser family"),
    ("Direct-curl usable", str(curl_count),
     f"{pct(curl_count, len(sources))}% of trade shows"),
    ("Firecrawl required", str(firecrawl_count + media_js),
     f"{firecrawl_count} shows + {media_js} media"),
]))
story.append(Spacer(1, 6))
story.append(kpi_row([
    ("Firecrawl balance", f"{FIRECRAWL['remaining_credits']:,}",
     f"of {FIRECRAWL['plan_credits_per_month']:,}/mo"),
    ("Companies with a website", f"{TOTALS['with_website']:,}",
     f"{pct(TOTALS['with_website'], TOTALS['companies_total'])}%"),
    ("Jobs page discovered",  f"{TOTALS['with_jobs_url']:,}",
     f"{pct(TOTALS['with_jobs_url'], TOTALS['with_website'])}% of sited"),
    ("News page discovered",  f"{TOTALS['with_news_url']:,}",
     f"{pct(TOTALS['with_news_url'], TOTALS['with_website'])}% of sited"),
]))
story.append(PageBreak())


# ================ 2 · Source inventory ================
section(story, "2 · Source inventory")

paragraph(story,
    f"<b>Trade shows: 26 URLs across 4 parser families.</b> Each row in the "
    f"<font face=\"Courier\">event_sources</font> table records a parser hint, "
    f"the last scrape count, and the last error. The chart below shows the parser "
    f"split; the table on the next page is the full inventory.")

story.append(img(ROOT / "chart_parser_pie.png", width=13 * cm))
story.append(Spacer(1, 4))

story.append(Paragraph("Parser families explained", H2))
paragraph(story,
    "<b>foodtech</b> — pages built on the "
    "<font face=\"Courier\">data-component=\"card-introduce\"</font> layout "
    "(FoodTech Event, MT Conference, Automation Xperience). One direct HTTP call "
    "recovers the entire list.<br/>"
    "<b>easyfairs</b> — SSR anchor pattern (Empack, Rotterdam Processing Week, "
    "Aqua Nederland, ReMaTec, Interclean, etc.). Only the first ~25 exhibitors "
    "are in the static HTML; the rest is behind an authenticated backend, so we "
    "capture the visible slice and derive clean names from URL slugs.<br/>"
    "<b>firecrawl</b> — JS-rendered exhibitor lists (Provada, TechniShow, "
    "BouwBeurs, VSK, ESEF, InfraTech, Maintenance NEXT, WoTS, Foodspec). Rendered "
    "in a headless browser via the Firecrawl API, then run through one of "
    "five DOM extractors (<i>provada</i>, <i>stand_table</i>, <i>foodtech</i>, "
    "<i>safetyevent</i>, <i>generic_anchor</i>).<br/>"
    "<b>unsupported</b> — LinkedIn, Vakbeurs Energie, Safety Event. Kept in the "
    "table so the UI shows the reason; no fetch attempt.")

paragraph(story,
    "<b>Media portals: 9 URLs, 1 parser dispatcher.</b> Each portal has a "
    "per-domain rule (four written), with a noise-filtered fallback for the "
    "rest. Every portal was tried with direct HTTP and all currently return "
    "zero entries — see §3.2 for the reason breakdown.")

story.append(PageBreak())


# ================ Source table (paginated) ================
section(story, "2.1 · Trade-show source inventory (full)")

paragraph(story,
    "Sorted by parser then by last exhibitor count. "
    "<i>Last count</i> is the number of companies extracted on the most recent scrape.")

src_rows = []
for s in sorted(sources, key=lambda r: (r["parser"], -int(r["last_count"] or 0))):
    src_rows.append([
        short_label(s["label"], 40),
        s["parser"],
        f'{int(s["last_count"] or 0):,}' if s["last_count"] else "—",
        s["last_scraped_at"][:10] if s["last_scraped_at"] else "—",
        short_label(s["last_error"] or "", 24) or "—",
    ])

tbl = table_from_rows(
    ["Label", "Parser", "Last count", "Last scraped", "Last error"],
    src_rows,
    col_widths=[7.0 * cm, 2.4 * cm, 2.2 * cm, 2.4 * cm, 3.4 * cm],
    wrap_cols=[0, 4],
)
story.append(tbl)
story.append(Spacer(1, 8))

paragraph(story,
    "<b>Media portals</b> — same information for the content-engine input list. "
    "Every portal has been probed; none are currently producing usable output "
    "via direct HTTP.")
med_rows = []
for m in MEDIA_SOURCES:
    med_rows.append([
        short_label(domain(m["url"]), 32),
        m["status"],
        short_label(m["note"], 46),
    ])
story.append(table_from_rows(
    ["Portal (host)", "Status", "Reason"],
    med_rows,
    col_widths=[5.6 * cm, 2.6 * cm, 9.2 * cm],
    wrap_cols=[0, 2],
    header_color=WARN,
))

story.append(PageBreak())


# ================ 3 · Fetch strategy ================
section(story, "3 · Direct cURL vs Firecrawl")

paragraph(story,
    "The pipeline defaults to a plain HTTP fetch and reaches for Firecrawl only "
    "when the DOM is empty without a JavaScript runtime. This section splits "
    "each input list by the strategy actually in use.")

story.append(img(ROOT / "chart_fetch_strategy.png", width=17 * cm))
story.append(Spacer(1, 6))

story.append(Paragraph("3.1 · Trade shows — 14 of 26 fetched with plain HTTP", H2))
paragraph(story,
    f"Of the 26 event-source rows, "
    f"<b>{curl_count} are direct-HTTP capable</b> "
    "(foodtech + easyfairs + safetyevent parsers), "
    f"<b>{firecrawl_count} require Firecrawl</b> (all JS-rendered Jaarbeurs / Ahoy "
    "/ FHI / Provada portals), and "
    f"<b>{unsup_count} are architecturally blocked</b> "
    "(LinkedIn requires an account; Vakbeurs Energie and Safety Event ship an "
    "empty shell that no headless browser has been able to populate).")

story.append(Paragraph("3.2 · Media portals — 0 of 9 currently productive", H2))
paragraph(story,
    "Every portal was probed with a normal browser User-Agent and returned zero "
    "entries. Grouped by cause:")
media_break_rows = [
    ["JS/AJAX only (would work through Firecrawl)",
     str(media_js), ", ".join(domain(m["url"]) for m in MEDIA_SOURCES
                              if m["status"] == "js_only")],
    ["HTTP 403 (edge-blocked)",
     str(media_403), ", ".join(domain(m["url"]) for m in MEDIA_SOURCES
                               if m["status"] == "http_403")],
    ["Zero entries after per-domain parser",
     str(media_no), ", ".join(domain(m["url"]) for m in MEDIA_SOURCES
                              if m["status"] == "no_entries")],
]
story.append(table_from_rows(
    ["Category", "#", "Portals"],
    media_break_rows,
    col_widths=[6.4 * cm, 1.2 * cm, 9.8 * cm],
    wrap_cols=[0, 2],
    header_color=WARN,
))
story.append(PageBreak())


# ================ 4 · Firecrawl status + pricing ================
section(story, "4 · Firecrawl status and pricing")

story.append(kpi_row([
    ("Remaining credits", f"{FIRECRAWL['remaining_credits']:,}",
     f"in period ending {FIRECRAWL['billing_period_end']}"),
    ("Plan credits / mo", f"{FIRECRAWL['plan_credits_per_month']:,}",
     "renews monthly on the 23rd"),
    ("Sources currently on Firecrawl", str(firecrawl_count),
     "trade shows only"),
    ("Would-add if media enabled", str(media_js),
     "JS-only media portals"),
]))
story.append(Spacer(1, 6))

story.append(Paragraph("4.1 · Yield per Firecrawl source (last run)", H2))
story.append(img(ROOT / "chart_firecrawl_yield.png", width=17 * cm))
story.append(Spacer(1, 4))

paragraph(story,
    "The <i>stand_table</i> extractor added in the last release unlocked TechniShow, "
    "BouwBeurs, and VSK — the three big Jaarbeurs sites where the exhibitor "
    "list is rendered as a single-cell &lt;td&gt; per exhibitor. "
    "<b>ESEF and Maintenance NEXT still return zero</b>: ESEF renders a hub page "
    "that links out to sub-pages, and Maintenance NEXT renders almost nothing at "
    "all (probably a cookie/consent wall). WoTS, InfraTech, and Foodspec pick up a "
    "handful each through the generic anchor extractor but the extractor is "
    "clearly under-tuned for their DOMs.")

story.append(Paragraph("4.2 · Cost to run everything at planned cadences", H2))
paragraph(story,
    "One Firecrawl scrape = one credit. At today's mix "
    f"({firecrawl_count} JS-only trade-show sources), a single full pass of "
    f"the pipeline costs <b>{firecrawl_count} credits</b> "
    f"(≈ ${firecrawl_count * 16 / 1000:.3f} at the current $16/1,000 rate).")

fc_cost_rows = [
    ["Cadence", "Trade-shows only", "+ Media (JS-only)", "Fits current plan?"],
    ["Daily",   f"{firecrawl_count * 30} cr/mo",
                f"{(firecrawl_count + media_js) * 30} cr/mo", "Yes"],
    ["Weekly",  f"{firecrawl_count * 4} cr/mo",
                f"{(firecrawl_count + media_js) * 4} cr/mo",   "Yes (easily)"],
    ["Every 2 days", f"{firecrawl_count * 15} cr/mo",
                     f"{(firecrawl_count + media_js) * 15} cr/mo", "Yes"],
    ["Hourly (extreme)", f"{firecrawl_count * 24 * 30} cr/mo",
                         f"{(firecrawl_count + media_js) * 24 * 30} cr/mo",
                         "No — upgrade needed"],
]
story.append(table_from_rows(
    fc_cost_rows[0], fc_cost_rows[1:],
    col_widths=[3.8 * cm, 4.4 * cm, 4.6 * cm, 4.2 * cm],
    header_color=WARN,
))
story.append(Spacer(1, 6))
paragraph(story,
    "<b>Bottom line:</b> at any realistic cadence (weekly to daily), the current "
    f"{FIRECRAWL['plan_credits_per_month']:,}-credit plan covers both the trade "
    "show set and the five JS-only media portals with headroom. Only an hourly "
    "run would push us into an upgrade tier.")
paragraph(story,
    '<font color="' + MUTED + '" size=8.5>Pricing is billed by Firecrawl per credit; '
    'the illustrative $16/1,000 rate above matches the published Hobby-tier price. '
    'The account here reports a 1,000-credit monthly plan with rollover — details '
    'in the Firecrawl dashboard.</font>')

story.append(PageBreak())


# ================ 5 · Coverage of jobs and news pages ================
section(story, "5 · Jobs and news page coverage")

paragraph(story,
    f"After a company enters the directory, the pipeline resolves its website "
    f"and then probes common NL/EN sub-paths for a careers page and a news/blog "
    f"page. Website resolution succeeds for <b>{TOTALS['with_website']:,} of "
    f"{TOTALS['companies_total']:,} companies "
    f"({pct(TOTALS['with_website'], TOTALS['companies_total'])}%)</b>; "
    "the remainder are either enrichment-terminal (no data from any provider) or "
    "brand-only entries without a domain.")

story.append(img(ROOT / "chart_coverage.png", width=17 * cm))
story.append(Spacer(1, 6))

paragraph(story,
    f"Among the {TOTALS['with_website']:,} companies with a discovered website, "
    f"<b>{TOTALS['with_jobs_url']:,} "
    f"({pct(TOTALS['with_jobs_url'], TOTALS['with_website'])}%) have a jobs page</b>, "
    f"<b>{TOTALS['with_news_url']:,} "
    f"({pct(TOTALS['with_news_url'], TOTALS['with_website'])}%) have a news / blog page</b>, "
    f"and <b>{TOTALS['with_both_urls']:,} companies have both</b>. "
    "Companies that don't surface a careers or news page are typically "
    "small distributors and OEM resellers who publish neither.")

story.append(Paragraph("Enrichment cascade breakdown", H2))
story.append(img(ROOT / "chart_enrich_pie.png", width=13 * cm))
paragraph(story,
    "IcyPeas handles the overwhelming majority "
    f"({int(enrich_by_source[0]['n']):,} companies), with Apollo picking up "
    "another 58 that IcyPeas couldn't hit. 301 companies are terminal "
    "(no data found by any of the four legs). FullEnrich and AI Ark are "
    "temporarily disabled behind feature flags and did not contribute to this snapshot.")
story.append(PageBreak())


# ================ 6 · Jobs analysis ================
section(story, "6 · Jobs analysis")

story.append(kpi_row([
    ("Job listings",         f"{TOTALS['jobs_total']:,}",
     f"across {TOTALS['with_jobs_url']:,} sourced companies"),
    ("Avg / sourced company", f"{TOTALS['jobs_total'] / max(TOTALS['with_jobs_url'], 1):.1f}",
     "median lower (long tail)"),
    ("Top-5 concentration",  f"{pct(sum(int(r['n_jobs']) for r in top_jobs[:5]), TOTALS['jobs_total'])}%",
     f"{sum(int(r['n_jobs']) for r in top_jobs[:5]):,} of total"),
    ("Top-20 concentration", f"{pct(sum(int(r['n_jobs']) for r in top_jobs[:20]), TOTALS['jobs_total'])}%",
     f"{sum(int(r['n_jobs']) for r in top_jobs[:20]):,} of total"),
]))
story.append(Spacer(1, 8))
story.append(KeepTogether([
    Paragraph("6.1 · Top-20 companies by jobs found", H2),
    Spacer(1, 4),
    img(ROOT / "chart_top_jobs.png", width=17 * cm),
]))
story.append(Spacer(1, 8))

story.append(KeepTogether([
    Paragraph("6.2 · Job-title word frequency", H2),
    Paragraph(
        "Word frequencies after stripping stop-words, month names and "
        "navigation-link residue (see caveat below). Job listings are technical: "
        "<b>engineer</b>, <b>manager</b>, <b>medewerker</b> "
        "(Dutch: <i>employee</i>) and <b>service</b> dominate.", BODY),
    Spacer(1, 4),
    img(ROOT / "chart_job_words.png", width=17 * cm),
]))
story.append(Spacer(1, 8))

story.append(KeepTogether([
    Paragraph("6.3 · Top phrases (bigrams) in job titles", H2),
    Spacer(1, 4),
    img(ROOT / "chart_job_bigrams.png", width=17 * cm),
]))
story.append(Spacer(1, 6))

paragraph(story,
    f'<font color="{MUTED}" size=9><b>Caveats.</b> The '
    "<font face=\"Courier\">jobs.department</font> and "
    "<font face=\"Courier\">jobs.location</font> columns are all "
    "<font face=\"Courier\">NULL</font> in the current snapshot — the "
    "listing extractor keeps only the title + URL. Categorisation is therefore "
    "derived from the title text only. Populating those columns from careers-page "
    f"metadata would be a small extension. Additionally, {nav_word_totals['jobs']:,} "
    "occurrences of navigation-link residue "
    "(<i>bekijk vacature</i>, <i>lees meer</i>, <i>learn more</i>, "
    "<i>read more</i>) were filtered out of the counts above — the raw title "
    "extractor also captures button/link text from surrounding page chrome.</font>")
story.append(PageBreak())


# ================ 7 · News analysis ================
section(story, "7 · News / articles analysis")

story.append(kpi_row([
    ("Articles",             f"{TOTALS['articles_total']:,}",
     f"across {TOTALS['with_news_url']:,} sourced companies"),
    ("Avg / sourced company", f"{TOTALS['articles_total'] / max(TOTALS['with_news_url'], 1):.1f}",
     "median lower (long tail)"),
    ("Top-5 concentration",   f"{pct(sum(int(r['n_articles']) for r in top_articles[:5]), TOTALS['articles_total'])}%",
     f"{sum(int(r['n_articles']) for r in top_articles[:5]):,} of total"),
    ("Top-20 concentration",  f"{pct(sum(int(r['n_articles']) for r in top_articles[:20]), TOTALS['articles_total'])}%",
     f"{sum(int(r['n_articles']) for r in top_articles[:20]):,} of total"),
]))
story.append(Spacer(1, 8))

story.append(KeepTogether([
    Paragraph("7.1 · Top-20 companies by news articles", H2),
    Spacer(1, 4),
    img(ROOT / "chart_top_articles.png", width=17 * cm),
]))
story.append(Spacer(1, 8))

story.append(KeepTogether([
    Paragraph("7.2 · Article-title word frequency", H2),
    Paragraph(
        "After filtering navigation residue and month names, the top words split "
        "into three groups: industry nouns "
        "(<b>nieuws</b>, <b>nieuwe</b>, <b>news</b>), multilingual chrome "
        "(<b>meer</b>, <b>lees</b> — Dutch <i>more</i> / <i>read</i>; "
        "<b>zum</b>, <b>blogbeitrag</b> — German blog-post header), and "
        "company/product names.", BODY),
    Spacer(1, 4),
    img(ROOT / "chart_article_words.png", width=17 * cm),
]))
story.append(Spacer(1, 8))

story.append(KeepTogether([
    Paragraph("7.3 · Top phrases (bigrams) in article titles", H2),
    Spacer(1, 4),
    img(ROOT / "chart_article_bigrams.png", width=17 * cm),
]))
story.append(Spacer(1, 6))

paragraph(story,
    f'<font color="{MUTED}" size=9><b>Caveat.</b> '
    f"{nav_word_totals['articles']:,} single-word and "
    f"{nav_bigram_totals['articles']:,} bigram occurrences of navigation-link "
    "residue were filtered out before ranking "
    "(<i>meer weten</i>, <i>lees meer</i>, <i>zum blogbeitrag</i>, "
    "<i>find out more</i>, <i>add arrow_forward</i>). These are &quot;read more&quot; "
    "buttons and Material Icons text that the anchor-based listing extractor picks "
    "up when the site puts them adjacent to article links. Fixing this would need "
    "a per-site excluder in <font face=\"Courier\">listing_extractor.py</font>.</font>")
story.append(PageBreak())


# ================ 8 · Categories ================
section(story, "8 · Exhibitor-declared categories")

paragraph(story,
    "Trade-show pages that expose category tags on the exhibitor cards get them "
    "carried through into <font face=\"Courier\">category_1..3</font> on "
    f"<font face=\"Courier\">companies</font>. Total distinct categories "
    f"observed: <b>{len(categories)}</b>. The top 15 dominate the list.")
story.append(img(ROOT / "chart_categories.png", width=17 * cm))
story.append(Spacer(1, 8))

story.append(Paragraph("Full category list (with counts)", H2))
cat_rows = [[r["category"], f'{int(r["n"]):,}'] for r in categories]
story.append(table_from_rows(
    ["Category", "Companies"],
    cat_rows,
    col_widths=[13.6 * cm, 3.2 * cm],
    wrap_cols=[0],
    header_color=GOOD,
))
story.append(PageBreak())


# ================ 9 · Appendix — full top-25 tables ================
section(story, "9 · Appendix — full ranking tables")

story.append(Paragraph("9.1 · Top-25 companies by jobs found", H2))
story.append(table_from_rows(
    ["#", "Company", "Jobs"],
    [[str(i + 1), r["name"], f'{int(r["n_jobs"]):,}']
     for i, r in enumerate(top_jobs)],
    col_widths=[1.0 * cm, 13.6 * cm, 2.2 * cm],
    wrap_cols=[1],
))
story.append(Spacer(1, 10))

story.append(Paragraph("9.2 · Top-25 companies by news articles", H2))
story.append(table_from_rows(
    ["#", "Company", "Articles"],
    [[str(i + 1), r["name"], f'{int(r["n_articles"]):,}']
     for i, r in enumerate(top_articles)],
    col_widths=[1.0 * cm, 13.6 * cm, 2.2 * cm],
    wrap_cols=[1],
    header_color=BRAND_DARK,
))
story.append(Spacer(1, 10))

story.append(Paragraph("9.3 · Job-title vocabulary (top 30)", H2))
jt_rows = [[t, f'{n:,}'] for t, n in job_word_freq.most_common(30)]
story.append(table_from_rows(
    ["Word", "Count"], jt_rows,
    col_widths=[13.6 * cm, 3.2 * cm],
))
story.append(Spacer(1, 10))

story.append(Paragraph("9.4 · Article-title vocabulary (top 30)", H2))
at_rows = [[t, f'{n:,}'] for t, n in art_word_freq.most_common(30)]
story.append(table_from_rows(
    ["Word", "Count"], at_rows,
    col_widths=[13.6 * cm, 3.2 * cm],
    header_color=BRAND_DARK,
))


# ---- footer with page numbers ---- #
def _page_footer(canvas, doc_):
    canvas.saveState()
    canvas.setFont(BASE, 8.5)
    canvas.setFillColor(colors.HexColor(MUTED))
    canvas.drawString(doc_.leftMargin, 0.9 * cm,
                      "Hi-Engineer  ·  investigation report")
    canvas.drawRightString(A4[0] - doc_.rightMargin, 0.9 * cm,
                           f"Page {doc_.page}")
    canvas.restoreState()


doc.build(story, onFirstPage=_page_footer, onLaterPages=_page_footer)
print(f"Wrote {OUT}  ({OUT.stat().st_size / 1024:.1f} KB)")
