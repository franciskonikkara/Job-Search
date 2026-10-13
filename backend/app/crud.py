"""Reusable data-access helpers shared by API routes and the importer."""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import models, schemas
from .utils import normalize_name, normalize_title


def get_or_create_company(
    db: Session,
    name: str | None,
    *,
    sponsorship_status: models.SponsorshipStatus | None = None,
) -> models.Company | None:
    if not name or not name.strip():
        return None
    norm = normalize_name(name)
    company = db.execute(
        select(models.Company).where(models.Company.normalized_name == norm)
    ).scalar_one_or_none()
    if company is None:
        company = models.Company(name=name.strip(), normalized_name=norm)
        if sponsorship_status is not None:
            company.sponsorship_status = sponsorship_status
        db.add(company)
        db.flush()
    return company


def find_duplicate_job(
    db: Session, company_id: int | None, title: str
) -> models.Job | None:
    """A job is a duplicate if same normalized title + same company."""
    norm_title = normalize_title(title)
    stmt = select(models.Job).where(models.Job.normalized_title == norm_title)
    if company_id is None:
        stmt = stmt.where(models.Job.company_id.is_(None))
    else:
        stmt = stmt.where(models.Job.company_id == company_id)
    return db.execute(stmt).scalars().first()


def create_job(db: Session, data: schemas.JobCreate) -> models.Job:
    company = get_or_create_company(db, data.company_name)
    company_id = company.id if company else None
    existing = find_duplicate_job(db, company_id, data.title)
    if existing is not None:
        return existing
    job = models.Job(
        company_id=company_id,
        title=data.title,
        normalized_title=normalize_title(data.title),
        description=data.description,
        location=data.location,
        job_url=data.job_url,
        source=data.source,
        sponsorship_status=data.sponsorship_status,
        sponsorship_evidence=data.sponsorship_evidence,
        match_score=data.match_score,
        date_discovered=data.date_discovered or date.today(),
    )
    db.add(job)
    db.flush()
    return job


def create_application(
    db: Session, data: schemas.ApplicationCreate
) -> models.Application:
    """Create an application, creating an inline Job if job_id not given."""
    if data.job_id is not None:
        job = db.get(models.Job, data.job_id)
        if job is None:
            raise ValueError(f"Job {data.job_id} not found")
    else:
        company = get_or_create_company(
            db, data.company_name, sponsorship_status=data.sponsorship_status
        )
        company_id = company.id if company else None
        title = data.position or "Untitled Position"
        job = find_duplicate_job(db, company_id, title)
        if job is None:
            job = models.Job(
                company_id=company_id,
                title=title,
                normalized_title=normalize_title(title),
                description=data.description,
                location=data.location,
                job_url=data.link,
                sponsorship_status=data.sponsorship_status,
            )
            db.add(job)
            db.flush()

    app = models.Application(
        job_id=job.id,
        resume_version_id=data.resume_version_id,
        status=data.status,
        date_applied=data.date_applied,
        ats_match=data.ats_match,
        missing_keywords=data.missing_keywords,
        application_url=data.application_url or data.link,
        credential_reference=data.credential_reference,
        response=data.response,
        last_contact=data.last_contact,
        notes=data.notes,
    )
    db.add(app)
    db.flush()
    return app


def compute_dashboard(db: Session) -> schemas.DashboardStats:
    S = models.ApplicationStatus
    week_ago = date.today() - timedelta(days=7)

    def count_status(*statuses: models.ApplicationStatus) -> int:
        return (
            db.execute(
                select(func.count())
                .select_from(models.Application)
                .where(models.Application.status.in_(statuses))
            ).scalar_one()
        )

    total = db.execute(
        select(func.count()).select_from(models.Application)
    ).scalar_one()

    applied_this_week = db.execute(
        select(func.count())
        .select_from(models.Application)
        .where(models.Application.date_applied >= week_ago)
    ).scalar_one()

    interviews = count_status(
        S.INTERVIEW, S.TECHNICAL_INTERVIEW, S.FINAL_INTERVIEW
    )
    offers = count_status(S.OFFER)
    rejections = count_status(S.REJECTED)
    pending = count_status(S.APPLIED, S.UNDER_REVIEW, S.RECRUITER_CONTACTED)
    saved_not_applied = count_status(S.SAVED, S.READY_TO_APPLY)

    follow_ups_due = db.execute(
        select(func.count())
        .select_from(models.FollowUp)
        .where(
            models.FollowUp.status == models.FollowUpStatus.PENDING,
            models.FollowUp.due_date <= date.today(),
        )
    ).scalar_one()

    by_status_rows = db.execute(
        select(models.Application.status, func.count())
        .group_by(models.Application.status)
    ).all()
    by_status = [
        schemas.StatusCount(status=row[0].value, count=row[1])
        for row in by_status_rows
    ]

    by_sponsor_rows = db.execute(
        select(models.Job.sponsorship_status, func.count())
        .select_from(models.Application)
        .join(models.Job, models.Application.job_id == models.Job.id)
        .group_by(models.Job.sponsorship_status)
    ).all()
    by_sponsorship = [
        schemas.StatusCount(status=row[0].value, count=row[1])
        for row in by_sponsor_rows
    ]

    return schemas.DashboardStats(
        total_applications=total,
        applied_this_week=applied_this_week,
        interviews=interviews,
        offers=offers,
        rejections=rejections,
        pending_response=pending,
        follow_ups_due=follow_ups_due,
        jobs_saved_not_applied=saved_not_applied,
        by_status=by_status,
        by_sponsorship=by_sponsorship,
    )
