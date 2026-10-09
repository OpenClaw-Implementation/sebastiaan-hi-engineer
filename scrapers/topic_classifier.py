"""Topic classifier for scraped articles — maps article title → EPCM-oriented
topic tag that aligns with the canonical taxonomy.

Topics (slug → human label):
  product_launch        · Product launch / new release
  partnership_ma        · Partnership / M&A
  trade_show            · Trade show / event / fair
  award                 · Award / recognition
  sustainability        · Sustainability / ESG
  innovation_rd         · Innovation / R&D / technology
  facility_expansion    · Facility expansion / opening
  personnel             · Personnel / appointment
  financial             · Financial results
  customer_case         · Customer case / reference project
  interview_opinion     · Interview / opinion / column
  webinar_training      · Webinar / training / workshop
  regulation_policy     · Regulation / policy / legal
  blog_update           · Blog / newsletter / general update
  nav_residue           · Not a real article — Read-more link, button, date
"""

from __future__ import annotations

import re

TOPIC_LABELS: dict[str, str] = {
    "product_launch":     "Product / launch",
    "partnership_ma":     "Partnership / M&A",
    "trade_show":         "Trade show / event",
    "award":              "Award / recognition",
    "sustainability":     "Sustainability / ESG",
    "innovation_rd":      "Innovation / R&D",
    "facility_expansion": "Facility expansion",
    "personnel":          "Personnel / appointment",
    "financial":          "Financial results",
    "customer_case":      "Customer case / reference",
    "interview_opinion":  "Interview / opinion",
    "webinar_training":   "Webinar / training",
    "regulation_policy":  "Regulation / policy",
    "blog_update":        "Blog / update",
    "nav_residue":        "Navigation noise",
    "unclassified":       "No topic matched",
}

TOPIC_RULES: list[tuple[str, re.Pattern]] = [
    ("nav_residue",       re.compile(r"^(lees meer|lees verder|meer weten|read more|"
                                     r"zum blogbeitrag|weiterlesen|en savoir plus|"
                                     r"más información|discover more|bekijk meer|"
                                     r"text link|video|english|nederlands|deutsch|"
                                     r"gallerie|gallery)$", re.I)),
    ("nav_residue",       re.compile(r"^(january|february|march|april|may|june|july|"
                                     r"august|september|october|november|december|"
                                     r"januari|februari|maart|mei|juni|juli|augustus|"
                                     r"oktober)\s+\d", re.I)),
    ("product_launch",    re.compile(r"\b(nieuw(e|s)?\s+(product|systeem|serie|reeks|generatie)|"
                                     r"new product|launch|lancering|introduc(es|ing|tion|eer)|"
                                     r"unveil|presenteer|introduceer|nu leverbaar|now available|"
                                     r"new release|product release)\b", re.I)),
    ("partnership_ma",    re.compile(r"\b(partner(ship|s|schap)?|samenwerking|acquis|overname|"
                                     r"neemt over|joint venture|alliance|merger|fusie|"
                                     r"acquires|acquired)\b", re.I)),
    ("trade_show",        re.compile(r"\b(beurs|hannover messe|foodtech|food tech|trade show|"
                                     r"exhibition|fair|hosts?|presenting at|op de beurs|"
                                     r"expo\b|stand\b|congres|conference|blechexpo|op de\s)\b", re.I)),
    ("award",             re.compile(r"\b(award|prijs|prize|winner|winnaar|gouden|best[e]? |"
                                     r"nomination|nominated|erkenning|erkend|shortlist|finalist|"
                                     r"top-?100)\b", re.I)),
    ("sustainability",    re.compile(r"\b(duurzaam|sustainab|green\b|circulair|circular|esg|co2|"
                                     r"klimaat|climate|emissies?|net[- ]?zero|renewable|"
                                     r"hernieuwbaar|verduurzaming|energie(besparing|transitie))\b", re.I)),
    ("innovation_rd",     re.compile(r"\b(innovatie|innovation|technology|technologie|research|"
                                     r"development|r&?d|patent|breakthrough|doorbraak|whitepaper|"
                                     r"artificial intelligence|ai\b|machine learning|automation|"
                                     r"digitalisering|digitalisation|robotics|robot|industry 4)\b", re.I)),
    ("facility_expansion",re.compile(r"\b(nieuwe (locatie|vestiging|fabriek|kantoor)|"
                                     r"new (facility|plant|factory|office|location)|"
                                     r"expansion|uitbreid|opening|opent|opens|grand opening|"
                                     r"relocation|nieuwbouw|move to)\b", re.I)),
    ("personnel",         re.compile(r"\b(new (ceo|cto|cfo|coo|director|president|managing director)|"
                                     r"appointment|appointed|benoem|aanstelling|opvolging|opvolger|"
                                     r"joins|welcomes|nieuwe directeur|nieuwe ceo)\b", re.I)),
    ("financial",         re.compile(r"\b(omzet|revenue|results|financial|quarter|kwartaal|"
                                     r"jaarverslag|annual report|q[1-4]\b|profit|winst|earnings|"
                                     r"forecast|outlook|full[- ]year)\b", re.I)),
    ("customer_case",     re.compile(r"\b(case study|casestudy|customer story|klantverhaal|"
                                     r"klantcase|reference project|referentieproject|succesverhaal|"
                                     r"customer case|kiest\s+(opnieuw\s+)?voor|installatie bij|"
                                     r"nieuwe installatie)\b", re.I)),
    ("interview_opinion", re.compile(r"\b(interview|column|opinion|opinie|mening|in gesprek met|"
                                     r"aan het woord|het verhaal van|q&a)\b", re.I)),
    ("webinar_training",  re.compile(r"\b(webinar|workshop|seminar|training|masterclass|course|"
                                     r"cursus|opleiding)\b", re.I)),
    ("regulation_policy", re.compile(r"\b(regulation|regulatory|wet(geving)?|policy|beleid|"
                                     r"richtlijn|cbam|reach|compliance|nis2|gdpr|avg)\b", re.I)),
    ("blog_update",       re.compile(r"\b(blog|nieuws|news|artikel|article|update|newsletter|"
                                     r"nieuwsbrief|leestijd|read time|min read)\b", re.I)),
]


def classify(title: str | None) -> str | None:
    if not title:
        return None
    t = title.strip().lower()
    for topic, rx in TOPIC_RULES:
        if rx.search(t):
            return topic
    return None
