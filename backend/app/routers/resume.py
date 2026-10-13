"""Resume tailoring / ATS match endpoints (rule-based)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import models, resume_match, schemas
from ..database import get_db

router = APIRouter(prefix="/api/resume", tags=["resume"])


@router.post("/match", response_model=schemas.ResumeMatchResult)
def match(body: schemas.ResumeMatchRequest, db: Session = Depends(get_db)):
    jd = body.job_description or ""
    # If a job_id is given and no JD text, use the stored job's description.
    if body.job_id and not jd.strip():
        job = db.get(models.Job, body.job_id)
        if job is not None:
            jd = (job.description or "") + " " + (job.title or "")
    result = resume_match.analyze(body.resume, jd)
    return result.as_dict()


@router.post("/tailor", response_model=schemas.ResumeTailorResult)
def tailor(body: schemas.ResumeTailorRequest, db: Session = Depends(get_db)):
    jd = body.job_description or ""
    if body.job_id and not jd.strip():
        job = db.get(models.Job, body.job_id)
        if job is not None:
            jd = (job.description or "") + " " + (job.title or "")
    result = resume_match.tailor(body.resume, jd)
    return result.as_dict()
