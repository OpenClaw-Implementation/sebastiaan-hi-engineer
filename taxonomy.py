"""Canonical EPCM taxonomy — the 10 top-level categories from the master
Excel 'topics' sheet with their sub-categories.

Importing this module seeds nothing on its own; call `seed()` to upsert into
the `taxonomy_terms` table (idempotent). The free-form string in
`companies.category_1` is mapped to canonical via `map_to_canonical()` at
import time.
"""

from __future__ import annotations

import re
from typing import Iterable

import db

# Each top-level category + its direct sub-categories.
# The order determines sort_order in the UI (left-rail / taxonomy chip row).
TAXONOMY: list[tuple[str, str, list[tuple[str, str]]]] = [
    ("manufacturing_production", "Manufacturing & Production", [
        ("additive_manufacturing", "Additive Manufacturing"),
        ("process_engineering",    "Process Engineering"),
        ("production_planning",    "Production Planning"),
        ("supply_chain_logistics", "Supply Chain & Logistics"),
    ]),
    ("building_facilities", "Building & Facilities", [
        ("infrastructure", "Infrastructure"),
        ("facilities",     "Facilities (Maintenance, Security)"),
    ]),
    ("design_engineering", "Design & Engineering", [
        ("structural",            "Structural Engineering"),
        ("architectural",         "Architectural Design"),
        ("mechanical",            "Mechanical Engineering"),
        ("electrical",            "Electrical Engineering"),
        ("plumbing_fire",         "Plumbing & Fire Protection"),
    ]),
    ("sustainability_env", "Sustainability & Environment", []),
    ("safety_health", "Safety, Health", [
        ("fire_safety", "Fire Safety"),
    ]),
    ("project_mgmt_strategy", "Project Management & Strategy", [
        ("capex",       "CapEx"),
        ("pmo",         "PMO"),
        ("procurement", "Procurement"),
    ]),
    ("construction_mgmt", "Construction Management", []),
    ("equipment_machinery", "Equipment & Machinery", [
        ("prod_line_assembly", "Production Line / Assembly Line"),
        ("packaging",          "Packaging"),
    ]),
    ("plant_mgmt", "Plant Management", []),
    ("smart_manufacturing", "Smart Manufacturing", [
        ("industrial_automation", "Industrial Automation"),
        ("advanced_tech",         "Advanced Technologies"),
        ("robotics",              "Robotics"),
        ("digitalization_ai",     "Digitalization & AI"),
        ("software",              "Software"),
    ]),
    # Addendum from the Excel (also used for jobs/articles classification)
    ("construction_renovation", "Construction & Renovation", []),
]

TOP_LEVEL_SLUGS = [slug for slug, _, _ in TAXONOMY]


# ---------------------------------------------------------------- lookup -- #
TOP_BY_SLUG = {slug: name for slug, name, _ in TAXONOMY}
SUB_BY_SLUG = {
    sub_slug: (slug, name, sub_name)
    for slug, name, subs in TAXONOMY
    for sub_slug, sub_name in subs
}

# Keyword rules for mapping free-form Excel category strings into canonical
# slugs. First match wins; checked in order.
_MAP_RULES: list[tuple[str, re.Pattern]] = [
    ("smart_manufacturing",     re.compile(r"smart manufacturing|robotic|automatisering|digit|\bsoftware\b|\bai\b|artificial intel", re.I)),
    ("manufacturing_production",re.compile(r"manufactur|product|voeding|food|chemie|chemi|vervaardig", re.I)),
    ("building_facilities",     re.compile(r"facilit|building|bouw(?!werk)|infrastruct|insulated|floors?|wand|plafond", re.I)),
    ("design_engineering",      re.compile(r"design & engineer|design\b|engineering - ontwerp|architecten|technisch(e)? ontwerp|mechanical|electrical|plumbing|fire protection|structural", re.I)),
    ("sustainability_env",      re.compile(r"sustain|duurzaam|environment", re.I)),
    ("safety_health",           re.compile(r"safety|veiligheid|fire\b|health|gezondheid", re.I)),
    ("project_mgmt_strategy",   re.compile(r"project management|strategy|capex|pmo|procurement|inkoop", re.I)),
    ("construction_mgmt",       re.compile(r"construction management|bouwmanagement|project management", re.I)),
    ("equipment_machinery",     re.compile(r"equipment|machinery|machines?|apparatuur|packaging", re.I)),
    ("plant_mgmt",              re.compile(r"plant management|plant mgr", re.I)),
    ("construction_renovation", re.compile(r"construction|renovat|bouw", re.I)),
    # fallback for the common free-form 'Engineering - *' pattern
    ("design_engineering",      re.compile(r"\bengineering\b", re.I)),
]


def map_to_canonical(free_text: str | None) -> tuple[str | None, str | None]:
    """Return (top_level_slug, sub_level_slug) or (None, None) for a free-form
    category string. Only the top-level is attempted at the moment — sub-level
    inference is left to a later pass.
    """
    if not free_text:
        return (None, None)
    s = str(free_text).strip()
    for slug, rx in _MAP_RULES:
        if rx.search(s):
            return (slug, None)
    return (None, None)


# ---------------------------------------------------------------- seed -- #
def flatten() -> list[dict]:
    """Flatten TAXONOMY into [{name, slug, parent_slug?, sort_order}, ...]
    with parents emitted before children."""
    rows: list[dict] = []
    for i, (slug, name, subs) in enumerate(TAXONOMY):
        rows.append({"name": name, "slug": slug, "sort_order": i})
    for i, (parent_slug, _, subs) in enumerate(TAXONOMY):
        for j, (sub_slug, sub_name) in enumerate(subs):
            rows.append({
                "name": sub_name, "slug": sub_slug,
                "parent_slug": parent_slug, "sort_order": j,
            })
    return rows


def seed() -> None:
    """Upsert the canonical taxonomy into Postgres. Safe to run many times."""
    db.seed_taxonomy(flatten())


if __name__ == "__main__":
    db.init_db()
    seed()
    print("Seeded taxonomy_terms with", len(flatten()), "rows.")
