"""Outreach drafting endpoints (template-based, human-approved)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .. import outreach, schemas

router = APIRouter(prefix="/api/outreach", tags=["outreach"])


@router.get("/kinds")
def kinds():
    return {"kinds": outreach.KINDS}


@router.post("/draft", response_model=schemas.OutreachDraftOut)
def draft(body: schemas.OutreachRequest):
    try:
        inp = outreach.OutreachInput(**body.model_dump())
        result = outreach.generate(inp)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result.as_dict()
