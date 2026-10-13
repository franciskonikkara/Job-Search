"""Conservative company de-duplication.

The USCIS/DOL data contains true duplicates that are just spelling or
abbreviation variants of the SAME full legal name, e.g.:
  - "Deloitte & Touche Llp" vs "Deloitte Touche Llp"      (& dropped)
  - "Tata Consultancy Services" vs "Tata Consultancy Svcs" (abbreviation)
  - "Amazon Development Center U S" vs "... Us"            (spacing)
  - "Microsoft Corporation" vs "Microsoft Corportion"      (typo)

It also contains distinct entities that merely SHARE A PREFIX and must NOT be
merged, e.g. "Amazon Advertising" vs "Amazon Studios", or unrelated companies
like "Tata Elxsi" vs "Tatango". So we deliberately do NOT merge by prefix.

Strategy: build a canonical key by expanding common abbreviations and removing
punctuation, then merge ONLY companies whose full canonical key is identical.
The survivor is the entity with the most USCIS approvals; its stats absorb the
others (max of scores/counts) and all jobs/contacts are re-pointed to it.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from . import models
from .utils import normalize_name

# Abbreviation -> canonical expansion (applied token-wise on normalized names).
_ABBREV = {
    "svcs": "services",
    "svc": "services",
    "consult": "consultancy",
    "concultancy": "consultancy",  # common misspelling seen in data
    "intl": "international",
    "natl": "national",
    "mgmt": "management",
    "tech": "technologies",
    "techs": "technologies",
    "sys": "systems",
    "solns": "solutions",
    "assoc": "associates",
    "corportion": "corporation",  # typo seen in data
    "us": "usa",
    "u s": "usa",
}


def canonical_key(name: str) -> str:
    """Expanded, punctuation-free key. Same key => same company."""
    norm = normalize_name(name)  # already strips inc/llc/corp/etc.
    norm = norm.replace("&", " ")
    norm = re.sub(r"\s+", " ", norm).strip()
    tokens = [_ABBREV.get(t, t) for t in norm.split()]
    # Collapse the 'u s'->'usa' two-token case handled via join+resplit.
    joined = " ".join(tokens)
    joined = joined.replace("u s", "usa")
    return joined.strip()


@dataclass
class DedupeResult:
    groups_merged: int = 0
    companies_removed: int = 0
    dry_run: bool = True
    examples: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "groups_merged": self.groups_merged,
            "companies_removed": self.companies_removed,
            "dry_run": self.dry_run,
            "examples": self.examples,
        }


def _absorb(survivor: models.Company, other: models.Company) -> None:
    """Merge `other`'s H-1B stats into `survivor` (take the stronger values)."""
    survivor.h1b_filings_total = max(
        survivor.h1b_filings_total or 0, other.h1b_filings_total or 0
    )
    survivor.h1b_filings_recent = max(
        survivor.h1b_filings_recent or 0, other.h1b_filings_recent or 0
    )
    survivor.h1b_certified = max(
        survivor.h1b_certified or 0, other.h1b_certified or 0
    )
    # USCIS approval counts: sum across the merged entities.
    survivor.uscis_initial_approvals = (
        (survivor.uscis_initial_approvals or 0)
        + (other.uscis_initial_approvals or 0)
    )
    survivor.uscis_initial_denials = (
        (survivor.uscis_initial_denials or 0) + (other.uscis_initial_denials or 0)
    )
    survivor.uscis_continuing_approvals = (
        (survivor.uscis_continuing_approvals or 0)
        + (other.uscis_continuing_approvals or 0)
    )
    survivor.uscis_continuing_denials = (
        (survivor.uscis_continuing_denials or 0)
        + (other.uscis_continuing_denials or 0)
    )
    survivor.uscis_last_fiscal_year = max(
        survivor.uscis_last_fiscal_year or 0, other.uscis_last_fiscal_year or 0
    ) or None
    survivor.sponsorship_score = max(
        survivor.sponsorship_score or 0, other.sponsorship_score or 0
    )
    if not survivor.careers_url and other.careers_url:
        survivor.careers_url = other.careers_url
    if not survivor.industry and other.industry:
        survivor.industry = other.industry


def _approvals(c: models.Company) -> int:
    return (c.uscis_initial_approvals or 0) + (c.uscis_continuing_approvals or 0)


def deduplicate(db: Session, *, dry_run: bool = True, limit_examples: int = 25) -> DedupeResult:
    result = DedupeResult(dry_run=dry_run)

    companies = db.execute(select(models.Company)).scalars().all()
    groups: dict[str, list[models.Company]] = defaultdict(list)
    for c in companies:
        key = canonical_key(c.name)
        if key:
            groups[key].append(c)

    for key, members in groups.items():
        if len(members) < 2:
            continue
        # Survivor = most approvals, then highest score, then lowest id.
        members.sort(key=lambda c: (-_approvals(c), -(c.sponsorship_score or 0), c.id))
        survivor = members[0]
        losers = members[1:]

        if len(result.examples) < limit_examples:
            names = " + ".join(f"'{m.name}'" for m in members)
            result.examples.append(f"[{key}] {names} -> '{survivor.name}'")

        result.groups_merged += 1
        result.companies_removed += len(losers)

        if dry_run:
            continue

        loser_ids = [c.id for c in losers]
        # Re-point jobs and contacts to the survivor.
        db.execute(
            update(models.Job)
            .where(models.Job.company_id.in_(loser_ids))
            .values(company_id=survivor.id)
        )
        db.execute(
            update(models.Contact)
            .where(models.Contact.company_id.in_(loser_ids))
            .values(company_id=survivor.id)
        )
        for loser in losers:
            _absorb(survivor, loser)
            db.delete(loser)

    if not dry_run:
        db.commit()
    return result
