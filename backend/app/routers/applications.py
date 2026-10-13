"""Application endpoints: list, create, update, delete."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .. import crud, models, schemas
from ..database import get_db

router = APIRouter(prefix="/api/applications", tags=["applications"])


def _load(db: Session, app_id: int) -> models.Application:
    app = db.get(models.Application, app_id)
    if app is None:
        raise HTTPException(status_code=404, detail="Application not found")
    return app


@router.get("", response_model=list[schemas.ApplicationOut])
def list_applications(
    db: Session = Depends(get_db),
    status: models.ApplicationStatus | None = None,
    search: str | None = Query(default=None),
):
    stmt = (
        select(models.Application)
        .options(
            selectinload(models.Application.job).selectinload(models.Job.company),
            selectinload(models.Application.resume_version),
            selectinload(models.Application.follow_ups),
        )
        .join(models.Job, models.Application.job_id == models.Job.id)
        .order_by(models.Application.date_applied.desc().nullslast())
    )
    if status is not None:
        stmt = stmt.where(models.Application.status == status)
    if search:
        like = f"%{search.lower()}%"
        stmt = stmt.where(models.Job.title.ilike(like))
    return db.execute(stmt).scalars().all()


@router.post("", response_model=schemas.ApplicationOut, status_code=201)
def create_application(
    data: schemas.ApplicationCreate, db: Session = Depends(get_db)
):
    try:
        app = crud.create_application(db, data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    db.refresh(app)
    return app


@router.get("/{app_id}", response_model=schemas.ApplicationOut)
def get_application(app_id: int, db: Session = Depends(get_db)):
    return _load(db, app_id)


@router.patch("/{app_id}", response_model=schemas.ApplicationOut)
def update_application(
    app_id: int, data: schemas.ApplicationUpdate, db: Session = Depends(get_db)
):
    app = _load(db, app_id)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(app, field, value)
    db.commit()
    db.refresh(app)
    return app


@router.delete("/{app_id}", status_code=204)
def delete_application(app_id: int, db: Session = Depends(get_db)):
    app = _load(db, app_id)
    db.delete(app)
    db.commit()
