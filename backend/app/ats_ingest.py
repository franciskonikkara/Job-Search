"""Fetch live cybersecurity jobs from company ATS APIs into the Jobs table.

This replaces the stale GitHub feeds as the primary job source. It queries each
company's live ATS board (Greenhouse/Lever/Ashby), keeps only currently-open
cybersecurity roles, links them to the company (inheriting H-1B sponsorship
history when the company is already in the sponsor DB), and dedupes.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import crud, models
from .ats_directory import default_companies
from .ats_fetch import ATSJob, fetch_company
from .cyber_taxonomy import categorize, is_cyber, is_entry_level
from .utils import normalize_title


@dataclass
class ATSIngestResult:
    companies_queried: int = 0
    jobs_seen: int = 0
    cyber_matched: int = 0
    inserted: int = 0
    duplicates: int = 0
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "companies_queried": self.companies_queried,
            "jobs_seen": self.jobs_seen,
            "cyber_matched": self.cyber_matched,
            "inserted": self.inserted,
            "duplicates": self.duplicates,
            "errors": self.errors[:10],
        }


def _url_exists(db: Session, url: str | None) -> bool:
    if not url:
        return False
    return db.execute(
        select(models.Job.id).where(models.Job.job_url == url).limit(1)
    ).first() is not None


def ingest_ats(
    db: Session,
    *,
    entry_only: bool = False,
    remote_only: bool = False,
    include_sponsors: bool = False,
    companies: list[tuple[str, str, str]] | None = None,
    progress=None,
) -> ATSIngestResult:
    result = ATSIngestResult()
    if companies is None:
        companies = default_companies()
        if include_sponsors:
            from .ats_directory import resolve_sponsor_companies
            extra = resolve_sponsor_companies(db)
            # Merge, de-duping by (platform, slug).
            have = {(p, s) for _, p, s in companies}
            for name, plat, slug in extra:
                if (plat, slug) not in have:
                    companies.append((name, plat, slug))
                    have.add((plat, slug))

    seen_urls: set[str] = set()
    seen_keys: set[tuple[int | None, str]] = set()

    for name, platform, slug in companies:
        result.companies_queried += 1
        fetched = fetch_company(platform, slug, name)
        result.errors.extend(fetched.errors)
        if progress is not None:
            progress(result)

        for job in fetched.jobs:
            result.jobs_seen += 1
            if not is_cyber(job.title):
                continue
            if entry_only and not is_entry_level(job.title):
                continue
            if remote_only and not job.remote:
                continue
            result.cyber_matched += 1

            company = crud.get_or_create_company(db, job.company)
            company_id = company.id if company else None
            key = (company_id, normalize_title(job.title))

            if job.url and job.url in seen_urls:
                result.duplicates += 1
                continue
            if key in seen_keys:
                result.duplicates += 1
                continue
            if _url_exists(db, job.url):
                result.duplicates += 1
                continue
            if crud.find_duplicate_job(db, company_id, job.title) is not None:
                result.duplicates += 1
                continue

            if job.url:
                seen_urls.add(job.url)
            seen_keys.add(key)

            # Inherit sponsorship status from the company's H-1B history.
            spons = models.SponsorshipStatus.UNKNOWN
            if company and company.sponsorship_status:
                spons = company.sponsorship_status

            cat = categorize(job.title)
            new_job = models.Job(
                company_id=company_id,
                title=job.title,
                normalized_title=normalize_title(job.title),
                location=job.location + (" (Remote)" if job.remote and job.location and "remote" not in job.location.lower() else "")
                if job.location else ("Remote" if job.remote else None),
                job_url=job.url,
                source=f"ats:{job.platform}" + (f":{cat}" if cat else ""),
                sponsorship_status=spons,
                sponsorship_evidence=models.SponsorshipEvidence.COMPANY_CAREER_PAGE,
            )
            db.add(new_job)
            result.inserted += 1

    db.commit()
    return result
