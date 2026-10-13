"""H-1B / DOL LCA endpoints: download, import, and ingest status."""
from __future__ import annotations

import os

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..config import get_settings
from ..database import SessionLocal, get_db
from ..dol_download import DolDownloadError, download_dol_file
from ..dol_import import import_lca_file
from ..uscis_import import import_uscis_file

router = APIRouter(prefix="/api/h1b", tags=["h1b"])
settings = get_settings()


def _set(ingest_id: int, **fields) -> None:
    """Update an ingest row in its own short-lived session."""
    db = SessionLocal()
    try:
        ing = db.get(models.DolIngest, ingest_id)
        if ing is None:
            return
        for k, v in fields.items():
            setattr(ing, k, v)
        db.commit()
    finally:
        db.close()


def _run_download_and_import(ingest_id: int, url: str) -> None:
    """Background job: download the DOL file then import it."""
    try:
        _set(ingest_id, status="downloading")
        result = download_dol_file(url)
        _set(ingest_id, status="importing", filename=os.path.basename(result.path))
        db = SessionLocal()
        try:
            summary = import_lca_file(db, result.path)
        finally:
            db.close()
        _set(
            ingest_id, status="done", rows_read=summary.rows_read,
            companies_upserted=summary.companies_upserted, message=summary.message,
        )
    except DolDownloadError as exc:
        _set(ingest_id, status="error", message=str(exc))
    except Exception as exc:  # noqa: BLE001
        _set(ingest_id, status="error", message=f"Import failed: {exc}")


@router.post("/download", response_model=schemas.DolIngestOut, status_code=202)
def start_download(
    body: schemas.DolDownloadRequest,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Kick off an auto-download + import of the DOL LCA file (in background)."""
    url = body.url or settings.dol_source_url
    ingest = models.DolIngest(source_url=url, status="pending")
    db.add(ingest)
    db.commit()
    db.refresh(ingest)
    background.add_task(_run_download_and_import, ingest.id, url)
    return ingest


@router.post("/import-file", response_model=schemas.DolIngestOut)
async def import_local_file(
    file: UploadFile = File(...), db: Session = Depends(get_db)
):
    """Fallback: import a DOL file the user downloaded manually."""
    if not file.filename or not file.filename.lower().endswith(
        (".xlsx", ".csv", ".txt")
    ):
        raise HTTPException(
            status_code=400, detail="Upload a DOL .xlsx or .csv disclosure file."
        )
    os.makedirs(settings.dol_download_dir, exist_ok=True)
    dest = os.path.join(settings.dol_download_dir, file.filename)
    with open(dest, "wb") as fh:
        fh.write(await file.read())

    ingest = models.DolIngest(
        source_url="(local file)", filename=file.filename, status="importing"
    )
    db.add(ingest)
    db.commit()
    db.refresh(ingest)
    try:
        summary = import_lca_file(db, dest)
    except Exception as exc:  # noqa: BLE001
        ingest.status = "error"
        ingest.message = f"Import failed: {exc}"
        db.commit()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    ingest.status = "done"
    ingest.rows_read = summary.rows_read
    ingest.companies_upserted = summary.companies_upserted
    ingest.message = summary.message
    db.commit()
    db.refresh(ingest)
    return ingest


@router.post("/uscis/import-file", response_model=schemas.DolIngestOut)
async def import_uscis_local_file(
    file: UploadFile = File(...), db: Session = Depends(get_db)
):
    """Import a USCIS H-1B Employer Data Hub CSV the user downloaded."""
    if not file.filename or not file.filename.lower().endswith(
        (".csv", ".txt", ".xlsx")
    ):
        raise HTTPException(
            status_code=400,
            detail="Upload a USCIS H-1B Employer Data Hub .csv file.",
        )
    os.makedirs(settings.dol_download_dir, exist_ok=True)
    dest = os.path.join(settings.dol_download_dir, file.filename)
    with open(dest, "wb") as fh:
        fh.write(await file.read())

    ingest = models.DolIngest(
        source_url="(USCIS local file)", filename=file.filename,
        status="importing",
    )
    db.add(ingest)
    db.commit()
    db.refresh(ingest)
    try:
        summary = import_uscis_file(db, dest)
    except Exception as exc:  # noqa: BLE001
        ingest.status = "error"
        ingest.message = f"Import failed: {exc}"
        db.commit()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    ingest.status = "done"
    ingest.rows_read = summary.rows_read
    ingest.companies_upserted = summary.companies_upserted
    ingest.message = summary.message
    db.commit()
    db.refresh(ingest)
    return ingest


@router.post("/uscis/download", response_model=schemas.DolIngestOut, status_code=202)
def start_uscis_download(
    body: schemas.DolDownloadRequest,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Auto-download + import a USCIS Employer Data Hub CSV (background)."""
    url = body.url or settings.uscis_source_url
    if not url:
        raise HTTPException(
            status_code=400,
            detail=(
                "No USCIS URL configured. Provide a url, or download the CSV "
                "from the USCIS Employer Data Hub Files page and use "
                "'Import USCIS File'."
            ),
        )
    ingest = models.DolIngest(source_url=url, status="pending")
    db.add(ingest)
    db.commit()
    db.refresh(ingest)
    background.add_task(_run_uscis_download_and_import, ingest.id, url)
    return ingest


def _run_uscis_download_and_import(ingest_id: int, url: str) -> None:
    try:
        _set(ingest_id, status="downloading")
        result = download_dol_file(url)  # generic downloader (browser UA)
        _set(ingest_id, status="importing", filename=os.path.basename(result.path))
        db = SessionLocal()
        try:
            summary = import_uscis_file(db, result.path)
        finally:
            db.close()
        _set(
            ingest_id, status="done", rows_read=summary.rows_read,
            companies_upserted=summary.companies_upserted, message=summary.message,
        )
    except DolDownloadError as exc:
        _set(ingest_id, status="error", message=str(exc))
    except Exception as exc:  # noqa: BLE001
        _set(ingest_id, status="error", message=f"Import failed: {exc}")


@router.get("/ingests", response_model=list[schemas.DolIngestOut])
def list_ingests(db: Session = Depends(get_db)):
    return db.execute(
        select(models.DolIngest).order_by(models.DolIngest.id.desc()).limit(20)
    ).scalars().all()


@router.get("/ingests/{ingest_id}", response_model=schemas.DolIngestOut)
def get_ingest(ingest_id: int, db: Session = Depends(get_db)):
    ing = db.get(models.DolIngest, ingest_id)
    if ing is None:
        raise HTTPException(status_code=404, detail="Ingest not found")
    return ing
