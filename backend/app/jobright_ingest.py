"""Ingest parsed Jobright jobs into the Jobs table.

- Optionally filter to cybersecurity-relevant titles.
- Link each job to a Company (matching the existing H-1B sponsor database when
  possible, so a fetched job inherits that company's sponsorship history).
- Map the Jobright H-1B tier to our sponsorship status/evidence.
- Dedupe by (company, normalized title) using the existing helper, and also
  skip if the same apply URL already exists.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import crud, models
from .cyber_taxonomy import categorize, is_cyber, is_entry_level
from .jobright_fetch import JobrightJob, fetch_all, fetch_jobright
from .utils import normalize_title


def _tier_to_sponsorship(tier: str) -> tuple[
    models.SponsorshipStatus, models.SponsorshipEvidence
]:
    if tier == "explicit":
        return (
            models.SponsorshipStatus.CONFIRMED_YES,
            models.SponsorshipEvidence.JOB_DESCRIPTION,
        )
    if tier == "history":
        return (
            models.SponsorshipStatus.PREVIOUSLY_SPONSORED,
            models.SponsorshipEvidence.USER_REPORT,
        )
    return (
        models.SponsorshipStatus.UNKNOWN,
        models.SponsorshipEvidence.UNKNOWN,
    )


@dataclass
class IngestResult:
    fetched: int = 0
    cyber_matched: int = 0
    inserted: int = 0
    duplicates: int = 0
    error: str | None = None

    def as_dict(self) -> dict:
        return {
            "fetched": self.fetched,
            "cyber_matched": self.cyber_matched,
            "inserted": self.inserted,
            "duplicates": self.duplicates,
            "error": self.error,
        }


def _url_exists(db: Session, url: str | None) -> bool:
    if not url:
        return False
    return db.execute(
        select(models.Job.id).where(models.Job.job_url == url).limit(1)
    ).first() is not None


def ingest_jobright(
    db: Session,
    *,
    cyber_only: bool = True,
    entry_only: bool = False,
    url: str | None = None,
    jobs: list[JobrightJob] | None = None,
) -> IngestResult:
    result = IngestResult()

    if jobs is None:
        # A specific url fetches just that source; otherwise fetch all
        # configured sources (H-1B feed + new-grad + internship).
        fetched = fetch_jobright(url) if url else fetch_all()
        if fetched.error:
            result.error = fetched.error
            return result
        jobs = fetched.jobs
    result.fetched = len(jobs)

    seen_urls: set[str] = set()
    seen_keys: set[tuple[int | None, str]] = set()

    for jr in jobs:
        if cyber_only and not is_cyber(jr.title):
            continue
        if entry_only and not is_entry_level(jr.title):
            continue
        result.cyber_matched += 1

        # Tag the job with its cyber category (falls back to feed category).
        cyber_cat = categorize(jr.title)

        company = crud.get_or_create_company(db, jr.company)
        company_id = company.id if company else None
        key = (company_id, normalize_title(jr.title))

        # Dedupe within this batch (uncommitted) AND against the DB.
        if jr.apply_url and jr.apply_url in seen_urls:
            result.duplicates += 1
            continue
        if key in seen_keys:
            result.duplicates += 1
            continue
        if _url_exists(db, jr.apply_url):
            result.duplicates += 1
            continue
        if crud.find_duplicate_job(db, company_id, jr.title) is not None:
            result.duplicates += 1
            continue

        if jr.apply_url:
            seen_urls.add(jr.apply_url)
        seen_keys.add(key)

        status, evidence = _tier_to_sponsorship(jr.h1b_tier)
        # If we have richer sponsor history for this company, keep the
        # explicit JD signal but don't downgrade a known sponsor.
        if company and company.sponsorship_status == (
            models.SponsorshipStatus.CURRENTLY_SPONSORING
        ) and status != models.SponsorshipStatus.CONFIRMED_YES:
            status = models.SponsorshipStatus.CURRENTLY_SPONSORING

        job = models.Job(
            company_id=company_id,
            title=jr.title,
            normalized_title=normalize_title(jr.title),
            location=jr.location,
            job_url=jr.apply_url,
            source="jobright" + (f":{cyber_cat}" if cyber_cat else ""),
            sponsorship_status=status,
            sponsorship_evidence=evidence,
        )
        # date_discovered has a DB default (today); only override if parsed.
        if jr.date_posted:
            job.date_discovered = jr.date_posted
        db.add(job)
        result.inserted += 1

    db.commit()
    return result
