"""Role classifier for scraped jobs — maps a job title to an EPCM role bucket.

Mirrors the contact role buckets so that a Project Engineer MEP job and a
Project Engineer MEP contact share the same filter. Keep the ROLE_RULES
list in sync with `import_excel.ROLE_RULES`.
"""

from __future__ import annotations

import re

# Order matters — first match wins. Each entry: (bucket, regex).
ROLE_RULES: list[tuple[str, re.Pattern]] = [
    ("project_engineer_mep",       re.compile(r"\bmep\b|mechanical.?electrical", re.I)),
    ("project_engineer_civil",     re.compile(r"\bcivil\b|civiele?\s*techniek|burger", re.I)),
    ("project_engineer_structural",re.compile(r"\bstructural\b|constructeur|structural engineer", re.I)),
    ("project_engineer_process",   re.compile(r"\bprocess (eng|engineer|technic)", re.I)),
    ("project_engineer_automation",re.compile(r"\bautomation (eng|engineer)|automatisering", re.I)),
    ("project_engineer_ei",        re.compile(r"\be&?i\b|elektro ?instrumentat", re.I)),
    ("project_engineer_bim",       re.compile(r"\bbim\b|building information model", re.I)),
    ("project_engineer",           re.compile(r"\bproject engineer\b|\bengineer\b|ingenieur", re.I)),
    ("project_manager",            re.compile(r"\bproject manager\b|\bpm\b|projectleider|projectmanager", re.I)),
    ("construction_manager",       re.compile(r"\bconstruction manager\b|bouwmanager|bouwkundige|site manager", re.I)),
    ("architect",                  re.compile(r"\barchitect\b", re.I)),
    ("product_manager",            re.compile(r"\bproduct manager\b|productmanager", re.I)),
    ("plant_manager",              re.compile(r"\bplant manager\b|plant mgr|fabriek(s)?manager", re.I)),
    ("hse_safety",                 re.compile(r"\b(hse|hs&e|safety|health|qhse|qa)\b|veiligheid|arbo", re.I)),
    ("procurement",                re.compile(r"\b(procurement|purchasing|inkoop|buyer)\b|contract manager", re.I)),
    ("senior_technical",           re.compile(r"\bsenior (technical|consultant|director)\b|business unit", re.I)),
    ("executive",                  re.compile(r"\b(ceo|cto|cfo|coo|managing director|directeur|president|founder)\b|\bdirector\b|\bhead of\b|\bchief\b", re.I)),
    ("sales_commercial",           re.compile(r"\b(sales|commercial|commercieel|account|business development|verkoop|key account)\b", re.I)),
    ("marketing",                  re.compile(r"\b(marketing|communication|communicatie|comms|brand|pr|seo|content)\b", re.I)),
    ("hr",                         re.compile(r"\bhr\b|human resources|talent|recruiter|recruitment|personeelszaken|payroll", re.I)),
    ("finance",                    re.compile(r"\b(finance|financieel|boekhoud|controller|accountant)\b", re.I)),
    ("service_field",              re.compile(r"\b(service|monteur|installer|installatie|installation|field|maintenance|onderhoud|technician|technicus|buitendienst)\b", re.I)),
    ("production_ops",             re.compile(r"\b(production|productie|operations|operator|logisti|warehouse|magazijn)\b", re.I)),
    ("design_creative",            re.compile(r"\b(design(er)?|ontwerp|ux|ui|graphic)\b", re.I)),
    ("intern_trainee",             re.compile(r"\b(intern|stage|trainee|junior|entry)\b", re.I)),
    ("consultant",                 re.compile(r"\b(consultant|adviseur|advisor|coach|trainer|specialist)\b", re.I)),
    ("admin_office",               re.compile(r"\b(administratief|administratie|office|receptionist|secretari)\b|medewerker\b", re.I)),
]


def classify(title: str | None) -> str | None:
    """Return the role bucket for a job title, or None if nothing matched."""
    if not title:
        return None
    for role, rx in ROLE_RULES:
        if rx.search(title):
            return role
    return None


# Human-readable labels for the UI
ROLE_LABELS: dict[str, str] = {
    "project_engineer_mep":        "Project Engineer — MEP",
    "project_engineer_civil":      "Project Engineer — Civil",
    "project_engineer_structural": "Project Engineer — Structural",
    "project_engineer_process":    "Project Engineer — Process",
    "project_engineer_automation": "Project Engineer — Automation",
    "project_engineer_ei":         "Project Engineer — E&I",
    "project_engineer_bim":        "Project Engineer — BIM",
    "project_engineer":            "Project Engineer (other)",
    "project_manager":             "Project Manager",
    "construction_manager":        "Construction Manager",
    "architect":                   "Architect",
    "product_manager":             "Product Manager",
    "plant_manager":               "Plant Manager",
    "hse_safety":                  "HSE / Safety",
    "procurement":                 "Procurement",
    "senior_technical":            "Senior Technical",
    "executive":                   "Executive",
    "sales_commercial":            "Sales / Commercial",
    "marketing":                   "Marketing",
    "hr":                          "HR",
    "finance":                     "Finance",
    "service_field":               "Service / Field",
    "production_ops":              "Production / Ops",
    "design_creative":             "Design / Creative",
    "intern_trainee":              "Intern / Trainee",
    "consultant":                  "Consultant",
    "admin_office":                "Admin / Office",
    "project_other":               "Project (other)",
    "freelance":                   "Freelance",
    "unclassified":                "No role matched",
}


# EPCM-priority roles (shown first on dashboards + filters)
EPCM_PRIORITY_ROLES = [
    "project_engineer_mep", "project_engineer_civil",
    "project_engineer_structural", "project_engineer_process",
    "project_engineer_automation", "project_engineer_ei",
    "project_engineer_bim", "project_engineer",
    "project_manager", "construction_manager", "architect",
    "hse_safety", "procurement", "plant_manager", "senior_technical",
]
