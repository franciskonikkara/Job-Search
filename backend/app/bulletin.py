"""Bulletin / Google-dork query builder (the briansjobsearch.com method).

We do NOT scrape job boards. Instead we generate ready-to-click search-engine
URLs that target applicant-tracking-system (ATS) domains, e.g.:

    "Cybersecurity" site:greenhouse.io remote
    "Cybersecurity" site:lever.co remote -jobgether

The user clicks the link, reviews results, applies, and then adds the role to
their tracker via the existing "Mark Applied" flow. This keeps everything
terms-of-service friendly and free.
"""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote_plus

from .config import get_settings

settings = get_settings()

# ATS / job-board domains worth targeting with site: queries.
ATS_TARGETS: list[dict] = [
    {"key": "greenhouse", "label": "Greenhouse", "site": "greenhouse.io"},
    {"key": "greenhouse_boards", "label": "Greenhouse Boards",
     "site": "boards.greenhouse.io"},
    {"key": "lever", "label": "Lever", "site": "lever.co"},
    {"key": "ashby", "label": "Ashby", "site": "jobs.ashbyhq.com"},
    {"key": "workday", "label": "Workday", "site": "myworkdayjobs.com"},
    {"key": "smartrecruiters", "label": "SmartRecruiters",
     "site": "smartrecruiters.com"},
    {"key": "icims", "label": "iCIMS", "site": "icims.com"},
    {"key": "workable", "label": "Workable", "site": "apply.workable.com"},
    {"key": "breezy", "label": "Breezy", "site": "breezy.hr"},
    {"key": "jobvite", "label": "Jobvite", "site": "jobs.jobvite.com"},
    {"key": "rippling", "label": "Rippling", "site": "ats.rippling.com"},
]

# Preset entry-level cybersecurity roles for quick one-click discovery,
# grouped by the user's 8-category taxonomy.
CYBER_ROLES: list[str] = [
    # SOC & Blue Team
    "SOC Analyst", "SOC Analyst I", "Cybersecurity Analyst I",
    "Information Security Analyst", "Security Monitoring Analyst",
    "Incident Response Analyst",
    # Vulnerability & Offensive
    "Junior Penetration Tester", "Vulnerability Analyst",
    "Application Security Analyst",
    # GRC & Audit
    "GRC Analyst", "Junior Compliance Analyst", "IT Auditor",
    "Cyber Risk Analyst",
    # IAM
    "IAM Analyst", "Identity and Access Management Analyst",
    # Infra, Cloud & Network Security
    "Cloud Security Engineer", "Network Security Analyst",
    # Security Engineering & AppDev
    "Cybersecurity Engineer", "Security Engineer", "DevSecOps Engineer",
    # Threat Intel, Forensics & DFIR
    "Threat Intelligence Analyst", "Digital Forensics Analyst",
    "Threat Hunter",
    # Feeder & Bridge
    "Security Administrator", "Cybersecurity Technician",
]


@dataclass
class Query:
    label: str
    query: str
    url: str

    def as_dict(self) -> dict:
        return {"label": self.label, "query": self.query, "url": self.url}


def _search_url(query: str, engine_base: str | None = None) -> str:
    base = engine_base or settings.search_engine_base
    return base + quote_plus(query)


# location_mode values.
LOCATION_MODES = ("remote", "onsite", "any")


def _build_query_string(
    role: str,
    site: str,
    *,
    location_mode: str = "any",
    company: str | None = None,
    exclusions: list[str] | None = None,
    extra_terms: list[str] | None = None,
) -> str:
    parts = [f'"{role}"']
    if company:
        parts.append(f'"{company}"')
    parts.append(f"site:{site}")
    if location_mode == "remote":
        parts.append("remote")
    elif location_mode == "onsite":
        # On-site roles in the USA: include US signal, exclude remote-only.
        parts.append('"United States"')
        parts.append("-remote")
    for term in extra_terms or []:
        parts.append(term)
    for ex in exclusions or []:
        ex = ex.strip().lstrip("-")
        if ex:
            parts.append(f"-{ex}")
    return " ".join(parts)


def build_job_queries(
    role: str,
    *,
    location_mode: str = "any",
    company: str | None = None,
    exclusions: list[str] | None = None,
    targets: list[str] | None = None,
    engine_base: str | None = None,
) -> list[Query]:
    """Generate one bulletin query per ATS target for a role.

    `location_mode`: "remote" (remote roles), "onsite" (on-site USA roles),
    or "any". `targets` filters to specific ATS keys. `company` scopes the
    search to a single employer (used to search within H-1B sponsors).
    """
    if location_mode not in LOCATION_MODES:
        location_mode = "any"
    chosen = ATS_TARGETS
    if targets:
        wanted = set(targets)
        chosen = [t for t in ATS_TARGETS if t["key"] in wanted]

    queries: list[Query] = []
    for target in chosen:
        q = _build_query_string(
            role, target["site"], location_mode=location_mode, company=company,
            exclusions=exclusions,
        )
        label = target["label"]
        if company:
            label = f"{target['label']} — {company}"
        queries.append(Query(label=label, query=q, url=_search_url(q, engine_base)))
    return queries


def build_career_page_queries(company: str) -> list[Query]:
    """Generate queries to find a company's official careers page."""
    variants = [
        (f'"{company}" careers', "Careers page"),
        (f'"{company}" jobs cybersecurity', "Cyber roles"),
        (f'"{company}" site:greenhouse.io', "Greenhouse board"),
        (f'"{company}" site:myworkdayjobs.com', "Workday board"),
        (f'"{company}" site:lever.co', "Lever board"),
    ]
    return [
        Query(label=label, query=q, url=_search_url(q))
        for q, label in variants
    ]


def list_roles_and_targets() -> dict:
    return {
        "roles": CYBER_ROLES,
        "targets": [{"key": t["key"], "label": t["label"], "site": t["site"]}
                    for t in ATS_TARGETS],
    }
