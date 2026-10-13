"""Curated directory of cyber-hiring companies with ATS slugs, plus a resolver
that maps top H-1B sponsor companies to their live ATS boards.

Each entry is (display_name, platform, slug). A wrong slug just returns 0 jobs,
so the list degrades gracefully. Users can extend it without code changes.
"""
from __future__ import annotations

import re

import requests
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models

_UA = {"User-Agent": "Mozilla/5.0 (compatible; JobCopilot/1.0)"}

# (display name, platform, slug) — seeded from well-known security employers
# and companies on community security-hiring lists that use these ATS boards.
COMPANIES: list[tuple[str, str, str]] = [
    # Greenhouse
    ("Databricks", "greenhouse", "databricks"),
    ("Cloudflare", "greenhouse", "cloudflare"),
    ("Stripe", "greenhouse", "stripe"),
    ("Robinhood", "greenhouse", "robinhood"),
    ("Coinbase", "greenhouse", "coinbase"),
    ("Okta", "greenhouse", "okta"),
    ("Datadog", "greenhouse", "datadog"),
    ("Elastic", "greenhouse", "elastic"),
    ("GitLab", "greenhouse", "gitlab"),
    ("Dropbox", "greenhouse", "dropbox"),
    ("Reddit", "greenhouse", "reddit"),
    ("Pinterest", "greenhouse", "pinterest"),
    ("Instacart", "greenhouse", "instacart"),
    ("Affirm", "greenhouse", "affirm"),
    ("Twilio", "greenhouse", "twilio"),
    ("Samsara", "greenhouse", "samsara"),
    ("Lyft", "greenhouse", "lyft"),
    ("Airtable", "greenhouse", "airtable"),
    ("Flexport", "greenhouse", "flexport"),
    ("Gusto", "greenhouse", "gusto"),
    ("Brex", "greenhouse", "brex"),
    ("Chime", "greenhouse", "chime"),
    ("Discord", "greenhouse", "discord"),
    ("Figma", "greenhouse", "figma"),
    ("Asana", "greenhouse", "asana"),
    ("DoorDash", "greenhouse", "doordashusa"),
    ("Roblox", "greenhouse", "roblox"),
    ("Unity", "greenhouse", "unity3d"),
    ("Nutanix", "greenhouse", "nutanix"),
    ("Grammarly", "greenhouse", "grammarly"),
    ("Mozilla", "greenhouse", "mozilla"),
    ("Verkada", "greenhouse", "verkada"),
    ("Rubrik", "greenhouse", "rubrik"),
    ("Zscaler", "greenhouse", "zscaler"),
    ("SentinelOne", "greenhouse", "sentinelone"),
    ("HashiCorp", "greenhouse", "hashicorp67"),
    # Lever
    ("Palantir", "lever", "palantir"),
    ("Netflix", "lever", "netflix"),
    ("Spotify", "lever", "spotify"),
    ("KnowBe4", "lever", "knowbe4"),
    # Ashby
    ("Ramp", "ashby", "ramp"),
    ("Notion", "ashby", "notion"),
    ("OpenAI", "ashby", "openai"),
    ("Vanta", "ashby", "vanta"),
    ("Snyk", "ashby", "snyk"),
    ("Linear", "ashby", "linear"),
    ("Anthropic", "ashby", "anthropic"),
    ("Cohere", "ashby", "cohere"),
    ("Mercury", "ashby", "mercury"),
    ("Clerk", "ashby", "clerk"),
]


def default_companies() -> list[tuple[str, str, str]]:
    seen: set[tuple[str, str]] = set()
    out: list[tuple[str, str, str]] = []
    for name, plat, slug in COMPANIES:
        key = (plat, slug)
        if key not in seen:
            seen.add(key)
            out.append((name, plat, slug))
    return out


# --- Sponsor -> ATS slug resolution ---------------------------------------

def _slugify(name: str) -> list[str]:
    """Generate candidate ATS slugs from a company display name."""
    base = name.lower()
    base = re.sub(r"\b(inc|llc|ltd|corp|corporation|co|company|the|group|"
                  r"holdings|usa|technologies|technology|systems|services|"
                  r"solutions|software|labs|global)\b", " ", base)
    base = re.sub(r"[^a-z0-9 ]", " ", base).strip()
    tokens = base.split()
    if not tokens:
        return []
    cands = []
    cands.append("".join(tokens))          # "acmesecurity"
    cands.append(tokens[0])                 # "acme"
    if len(tokens) >= 2:
        cands.append("".join(tokens[:2]))   # "acmesecurity"
        cands.append("-".join(tokens[:2]))  # "acme-security"
    # De-dup, keep order, drop very short.
    seen = set()
    out = []
    for c in cands:
        if len(c) >= 3 and c not in seen:
            seen.add(c)
            out.append(c)
    return out


def _probe(platform: str, slug: str) -> bool:
    """Return True if this ATS board exists (has a jobs endpoint)."""
    try:
        if platform == "greenhouse":
            url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
        elif platform == "lever":
            url = f"https://api.lever.co/v0/postings/{slug}?mode=json&limit=1"
        elif platform == "ashby":
            url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
        else:
            return False
        r = requests.get(url, headers=_UA, timeout=15)
        if r.status_code != 200:
            return False
        data = r.json()
        if platform == "lever":
            return isinstance(data, list) and len(data) > 0
        return len(data.get("jobs", [])) > 0
    except Exception:
        return False


def resolve_sponsor_companies(
    db: Session, *, top_n: int = 40, max_resolved: int = 25
) -> list[tuple[str, str, str]]:
    """Find ATS boards for the top H-1B sponsor companies.

    Takes the highest-scoring sponsors, generates candidate slugs, and probes
    Greenhouse/Lever/Ashby. Returns verified (name, platform, slug) tuples.
    Capped to avoid long fetches / rate pressure.
    """
    sponsors = db.execute(
        select(models.Company)
        .where(models.Company.sponsorship_score > 0)
        .order_by(models.Company.sponsorship_score.desc(),
                  models.Company.uscis_initial_approvals.desc())
        .limit(top_n)
    ).scalars().all()

    resolved: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str]] = set()
    for comp in sponsors:
        if len(resolved) >= max_resolved:
            break
        for slug in _slugify(comp.name):
            hit = None
            for platform in ("greenhouse", "lever", "ashby"):
                if (platform, slug) in seen:
                    continue
                if _probe(platform, slug):
                    hit = (comp.name, platform, slug)
                    seen.add((platform, slug))
                    break
            if hit:
                resolved.append(hit)
                break
    return resolved
