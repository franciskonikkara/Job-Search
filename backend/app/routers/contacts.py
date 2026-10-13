"""Contact endpoints: list, create, update, delete."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .. import crud, models, schemas
from ..database import get_db

router = APIRouter(prefix="/api/contacts", tags=["contacts"])


@router.get("", response_model=list[schemas.ContactOut])
def list_contacts(db: Session = Depends(get_db)):
    stmt = (
        select(models.Contact)
        .options(selectinload(models.Contact.company))
        .order_by(models.Contact.name)
    )
    return db.execute(stmt).scalars().all()


@router.post("", response_model=schemas.ContactOut, status_code=201)
def create_contact(data: schemas.ContactCreate, db: Session = Depends(get_db)):
    company = crud.get_or_create_company(db, data.company_name)
    contact = models.Contact(
        company_id=company.id if company else None,
        **data.model_dump(exclude={"company_name"}),
    )
    db.add(contact)
    db.commit()
    db.refresh(contact)
    return contact


@router.patch("/{contact_id}", response_model=schemas.ContactOut)
def update_contact(
    contact_id: int, data: schemas.ContactUpdate, db: Session = Depends(get_db)
):
    contact = db.get(models.Contact, contact_id)
    if contact is None:
        raise HTTPException(status_code=404, detail="Contact not found")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(contact, field, value)
    db.commit()
    db.refresh(contact)
    return contact


@router.delete("/{contact_id}", status_code=204)
def delete_contact(contact_id: int, db: Session = Depends(get_db)):
    contact = db.get(models.Contact, contact_id)
    if contact is None:
        raise HTTPException(status_code=404, detail="Contact not found")
    db.delete(contact)
    db.commit()
