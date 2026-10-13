"""Follow-up endpoints: list due follow-ups, create, update, delete."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db

router = APIRouter(prefix="/api/followups", tags=["followups"])


@router.get("", response_model=list[schemas.FollowUpOut])
def list_followups(
    db: Session = Depends(get_db),
    due_only: bool = Query(default=False),
    pending_only: bool = Query(default=True),
):
    stmt = select(models.FollowUp).order_by(models.FollowUp.due_date)
    if pending_only:
        stmt = stmt.where(models.FollowUp.status == models.FollowUpStatus.PENDING)
    if due_only:
        stmt = stmt.where(models.FollowUp.due_date <= date.today())
    return db.execute(stmt).scalars().all()


@router.post("", response_model=schemas.FollowUpOut, status_code=201)
def create_followup(data: schemas.FollowUpCreate, db: Session = Depends(get_db)):
    if db.get(models.Application, data.application_id) is None:
        raise HTTPException(status_code=404, detail="Application not found")
    fu = models.FollowUp(**data.model_dump())
    db.add(fu)
    db.commit()
    db.refresh(fu)
    return fu


@router.patch("/{fu_id}", response_model=schemas.FollowUpOut)
def update_followup(
    fu_id: int, data: schemas.FollowUpUpdate, db: Session = Depends(get_db)
):
    fu = db.get(models.FollowUp, fu_id)
    if fu is None:
        raise HTTPException(status_code=404, detail="Follow-up not found")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(fu, field, value)
    db.commit()
    db.refresh(fu)
    return fu


@router.delete("/{fu_id}", status_code=204)
def delete_followup(fu_id: int, db: Session = Depends(get_db)):
    fu = db.get(models.FollowUp, fu_id)
    if fu is None:
        raise HTTPException(status_code=404, detail="Follow-up not found")
    db.delete(fu)
    db.commit()
