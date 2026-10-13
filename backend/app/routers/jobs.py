"""Job endpoints: list jobs, live ATS fetch (background), apply, delete."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .. import crud, models, schemas
from ..ats_ingest import ingest_ats
from ..database import SessionLocal, get_db

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

# Statuses that mean "you actually submitted an application" (set date_applied).
_APPLIED_LIKE = {
    models.ApplicationStatus.APPLIED,
    models.ApplicationStatus.UNDER_REVIEW,
    models.ApplicationStatus.RECRUITER_CONTACTED,
    models.ApplicationStatus.INTERVIEW,
    models.ApplicationStatus.TECHNICAL_INTERVIEW,
    models.ApplicationStatus.FINAL_INTERVIEW,
    models.ApplicationStatus.OFFER,
}


@router.get("", response_model=list[schemas.JobOut])
def list_jobs(
    db: Session = Depends(get_db),
    only_unapplied: bool = Query(default=False),
    search: str | None = None,
):
    stmt = (
        select(models.Job)
        .options(selectinload(models.Job.company))
        .order_by(models.Job.date_discovered.desc())
    )
    if only_unapplied:
        stmt = stmt.where(~models.Job.application.has())
    if search:
        stmt = stmt.where(models.Job.title.ilike(f"%{search.lower()}%"))
    return db.execute(stmt).scalars().all()


@router.post("", response_model=schemas.JobOut, status_code=201)
def create_job(data: schemas.JobCreate, db: Session = Depends(get_db)):
    job = crud.create_job(db, data)
    db.commit()
    db.refresh(job)
    return job


def _run_fetch(run_id: int, entry_only: bool, remote_only: bool,
               include_sponsors: bool) -> None:
    """Background worker: query ATS boards and record progress on the run."""
    db = SessionLocal()
    try:
        run = db.get(models.JobFetchRun, run_id)
        if run is None:
            return
        run.status = "running"
        db.commit()

        def progress(res) -> None:
            run.companies_queried = res.companies_queried
            run.jobs_seen = res.jobs_seen
            run.cyber_matched = res.cyber_matched
            run.inserted = res.inserted
            run.duplicates = res.duplicates
            db.commit()

        result = ingest_ats(
            db, entry_only=entry_only, remote_only=remote_only,
            include_sponsors=include_sponsors, progress=progress,
        )
        run.status = "done"
        run.companies_queried = result.companies_queried
        run.jobs_seen = result.jobs_seen
        run.cyber_matched = result.cyber_matched
        run.inserted = result.inserted
        run.duplicates = result.duplicates
        run.message = f"Added {result.inserted} new cyber jobs."
        db.commit()
    except Exception as exc:  # noqa: BLE001
        run = db.get(models.JobFetchRun, run_id)
        if run is not None:
            run.status = "error"
            run.message = str(exc)
            db.commit()
    finally:
        db.close()


@router.post("/fetch", response_model=schemas.JobFetchRunOut, status_code=202)
def fetch_jobs(
    body: schemas.JobFetchRequest,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Start a background fetch of live cybersecurity jobs from ATS boards.

    Returns immediately with a run id; poll GET /api/jobs/fetch/{id} for
    progress. Only currently-open postings are returned by the ATS APIs.
    """
    run = models.JobFetchRun(status="pending")
    db.add(run)
    db.commit()
    db.refresh(run)
    background.add_task(
        _run_fetch, run.id, body.entry_only, body.remote_only,
        body.include_sponsors,
    )
    return _run_out(run)


@router.get("/fetch/{run_id}", response_model=schemas.JobFetchRunOut)
def fetch_status(run_id: int, db: Session = Depends(get_db)):
    run = db.get(models.JobFetchRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return _run_out(run)


def _run_out(run: models.JobFetchRun) -> dict:
    return {
        "id": run.id,
        "status": run.status,
        "companies_queried": run.companies_queried,
        "jobs_seen": run.jobs_seen,
        "cyber_matched": run.cyber_matched,
        "inserted": run.inserted,
        "duplicates": run.duplicates,
        "message": run.message,
    }


@router.post("/{job_id}/apply", response_model=schemas.ApplicationOut, status_code=201)
def mark_applied(
    job_id: int,
    body: schemas.JobApplyRequest | None = None,
    db: Session = Depends(get_db),
):
    """Create an Application for a job with a chosen status.

    Status may be Applied, Saved, Closed, Rejected, Interview, etc. date_applied
    is set only for applied-like statuses.
    """
    job = db.get(models.Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.application is not None:
        raise HTTPException(status_code=400, detail="Job already has an application")
    status = (body.status if body else None) or models.ApplicationStatus.APPLIED
    app = models.Application(
        job_id=job.id,
        status=status,
        date_applied=date.today() if status in _APPLIED_LIKE else None,
        application_url=job.job_url,
    )
    db.add(app)
    db.commit()
    db.refresh(app)
    return app


@router.delete("/{job_id}", status_code=204)
def delete_job(job_id: int, db: Session = Depends(get_db)):
    job = db.get(models.Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    db.delete(job)
    db.commit()
