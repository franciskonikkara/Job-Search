"""Discover endpoints: bulletin/dork job-search query generation."""
from __future__ import annotations

from fastapi import APIRouter

from .. import bulletin, schemas

router = APIRouter(prefix="/api/discover", tags=["discover"])


@router.get("/options")
def options():
    """Preset cybersecurity roles and available ATS targets."""
    return bulletin.list_roles_and_targets()


@router.post("/queries", response_model=list[schemas.QueryOut])
def build_queries(body: schemas.DiscoverRequest):
    queries = bulletin.build_job_queries(
        body.role,
        location_mode=body.location_mode,
        company=body.company,
        exclusions=body.exclusions,
        targets=body.targets or None,
    )
    return [q.as_dict() for q in queries]
