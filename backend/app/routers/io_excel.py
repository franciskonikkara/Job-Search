"""Excel import/export endpoints."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from .. import excel_io
from ..database import get_db

router = APIRouter(prefix="/api/excel", tags=["excel"])

_XLSX_MIME = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)


@router.post("/import")
async def import_excel(
    file: UploadFile = File(...), db: Session = Depends(get_db)
):
    if not file.filename or not file.filename.lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(
            status_code=400, detail="Please upload an .xlsx file."
        )
    content = await file.read()
    try:
        result = excel_io.import_workbook(db, content)
    except Exception as exc:  # noqa: BLE001 - surface a friendly message
        raise HTTPException(
            status_code=400, detail=f"Could not read spreadsheet: {exc}"
        ) from exc
    return result.as_dict()


@router.get("/export")
def export_excel(db: Session = Depends(get_db)):
    data = excel_io.export_workbook(db)
    filename = f"Job_Applications_{date.today().isoformat()}.xlsx"
    return StreamingResponse(
        iter([data]),
        media_type=_XLSX_MIME,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
