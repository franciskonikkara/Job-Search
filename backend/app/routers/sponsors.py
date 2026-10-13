"""Sponsor (H-1B company) listing and career-page link generation."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import bulletin, models, schemas
from ..database import get_db

router = APIRouter(prefix="/api/sponsors", tags=["sponsors"])

# A sponsor counts as "recent" if it filed/approved within this many years.
_RECENT_YEARS = 2


@router.get("", response_model=list[schemas.SponsorOut])
def list_sponsors(
    db: Session = Depends(get_db),
    search: str | None = Query(default=None),
    min_score: int = Query(default=0),
    recent_only: bool = Query(default=False),
    limit: int = Query(default=100, le=500),
):
    # Total approvals used as the tie-break so the strongest sponsors come
    # first among the many companies that reach score 100.
    total_appr = (
        models.Company.uscis_initial_approvals
        + models.Company.uscis_continuing_approvals
    )
    stmt = (
        select(models.Company)
        .where(models.Company.h1b_filings_total > 0)
        .order_by(
            models.Company.sponsorship_score.desc(),
            total_appr.desc(),
            models.Company.h1b_filings_total.desc(),
        )
    )
    if search:
        stmt = stmt.where(models.Company.name.ilike(f"%{search.lower()}%"))
    if min_score:
        stmt = stmt.where(models.Company.sponsorship_score >= min_score)
    if recent_only:
        cutoff = date.today().year - _RECENT_YEARS
        # Recent by either DOL recent filings or USCIS recent fiscal year.
        stmt = stmt.where(
            (models.Company.h1b_filings_recent > 0)
            | (func.coalesce(models.Company.uscis_last_fiscal_year, 0) >= cutoff)
        )
    stmt = stmt.limit(limit)
    return db.execute(stmt).scalars().all()


@router.get("/{company_id}/career-links", response_model=list[schemas.QueryOut])
def career_links(company_id: int, db: Session = Depends(get_db)):
    company = db.get(models.Company, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")
    return [q.as_dict() for q in bulletin.build_career_page_queries(company.name)]


@router.get("/{company_id}/job-links", response_model=list[schemas.QueryOut])
def job_links(
    company_id: int,
    role: str = Query(default="Cybersecurity"),
    location_mode: str = Query(default="any"),
    db: Session = Depends(get_db),
):
    """Bulletin queries scoped to this sponsor (search jobs within it)."""
    company = db.get(models.Company, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")
    queries = bulletin.build_job_queries(
        role, location_mode=location_mode, company=company.name,
    )
    return [q.as_dict() for q in queries]
