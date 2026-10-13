"""Parse USCIS H-1B Employer Data Hub files and rank companies.

USCIS publishes per-fiscal-year data of actual H-1B petition decisions. This is
the second primary source (alongside DOL LCA) that sites like h1bgrader.com are
built on. Unlike DOL LCA (filings), this reflects real petition outcomes.

The full Employer Data Hub layout (as in the user's Excel files) has these
columns, with decisions split across categories:

  Line by line, Fiscal Year, Employer (Petitioner) Name, Tax ID,
  Industry (NAICS) Code, Petitioner City, Petitioner State, Petitioner Zip Code,
  New Employment Approval/Denial, Continuation Approval/Denial,
  Change with Same Employer Approval/Denial, New Concurrent Approval/Denial,
  Change of Employer Approval/Denial, Amended Approval/Denial

These files are huge uncompressed (100s of MB), so xlsx is read with the
streaming reader in xlsx_stream.py. CSV files (single-fiscal-year Data Hub
downloads) are read in chunks with pandas.

Everything is framed as sponsorship HISTORY, never a guarantee.
"""
from __future__ import annotations

import os
from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models
from .utils import normalize_name
from .xlsx_stream import iter_xlsx_rows

# Header label -> canonical key. Matched case-insensitively, trimmed.
# Approval/denial categories are grouped into "approvals" and "denials".
_HEADER_MAP = {
    "fiscal year": "fiscal_year",
    "employer (petitioner) name": "employer",
    "employer": "employer",
    "petitioner": "employer",
    "petitioner state": "state",
    "state": "state",
    "petitioner city": "city",
    "city": "city",
    "industry (naics) code": "industry",
    # Approval categories
    "new employment approval": "appr",
    "continuation approval": "appr",
    "change with same employer approval": "appr",
    "new concurrent approval": "appr",
    "change of employer approval": "appr",
    "amended approval": "appr",
    "initial approval": "appr",
    "continuing approval": "appr",
    # Denial categories
    "new employment denial": "den",
    "continuation denial": "den",
    "change with same employer denial": "den",
    "new concurrent denial": "den",
    "change of employer denial": "den",
    "amended denial": "den",
    "initial denial": "den",
    "continuing denial": "den",
}


@dataclass
class _Agg:
    approvals: int = 0
    denials: int = 0
    # Split for the model's initial/continuing display fields.
    init_appr: int = 0
    init_den: int = 0
    cont_appr: int = 0
    cont_den: int = 0
    last_fy: int | None = None
    display_name: str = ""
    industry: str = ""


@dataclass
class UscisSummary:
    rows_read: int = 0
    companies_upserted: int = 0
    employers_seen: int = 0
    message: str = ""

    def as_dict(self) -> dict:
        return {
            "rows_read": self.rows_read,
            "companies_upserted": self.companies_upserted,
            "employers_seen": self.employers_seen,
            "message": self.message,
        }


def _to_int(value) -> int:
    if value is None:
        return 0
    s = str(value).replace(",", "").strip()
    if not s or s.upper() in ("NA", "N/A", "-"):
        return 0
    try:
        return int(float(s))
    except ValueError:
        return 0


def _to_year(value) -> int | None:
    y = _to_int(value)
    return y if 1990 <= y <= 2100 else None


def _build_column_plan(header: list[str]) -> dict:
    """Map header positions to roles. Returns indices for each field.

    approval/denial columns are collected as lists of indices, and we track
    which specific ones are 'initial/new' vs 'continuing' for display fields.
    """
    plan = {
        "employer": None, "fiscal_year": None, "state": None,
        "city": None, "industry": None,
        "appr": [], "den": [],
        "init_appr": [], "init_den": [], "cont_appr": [], "cont_den": [],
    }
    for i, raw in enumerate(header):
        key = str(raw or "").strip().lower()
        role = _HEADER_MAP.get(key)
        if role is None:
            continue
        if role in ("appr", "den"):
            plan[role].append(i)
            if key.startswith("new employment") or key.startswith("initial"):
                plan["init_" + role].append(i)
            elif key.startswith("continu"):
                plan["cont_" + role].append(i)
        elif plan[role] is None:
            plan[role] = i
    return plan


def _iter_rows(path: str):
    """Yield rows as lists of strings for xlsx (streamed) or csv."""
    ext = os.path.splitext(path)[1].lower()
    if ext in (".xlsx", ".xlsm"):
        yield from iter_xlsx_rows(path)
    else:
        # CSV/TXT: stream line by line via the csv module (memory-safe).
        import csv

        with open(path, newline="", encoding="utf-8-sig", errors="replace") as fh:
            for row in csv.reader(fh):
                yield row


def import_uscis_file(db: Session, path: str) -> UscisSummary:
    summary = UscisSummary()
    rows = _iter_rows(path)

    header = next(rows, None)
    if header is None:
        summary.message = "File is empty."
        return summary
    plan = _build_column_plan(header)
    if plan["employer"] is None:
        summary.message = (
            "Could not find an 'Employer (Petitioner) Name' column. Is this a "
            "USCIS H-1B Employer Data Hub file?"
        )
        return summary

    emp_i = plan["employer"]
    aggs: dict[str, _Agg] = defaultdict(_Agg)

    def cell(row, idx):
        return row[idx] if idx is not None and idx < len(row) else ""

    def sum_cells(row, idxs):
        return sum(_to_int(row[i]) for i in idxs if i < len(row))

    for row in rows:
        summary.rows_read += 1
        if emp_i >= len(row):
            continue
        employer = row[emp_i]
        if not employer or str(employer).strip() == "":
            continue
        norm = normalize_name(str(employer))
        if not norm:
            continue
        agg = aggs[norm]
        if not agg.display_name:
            agg.display_name = str(employer).strip().title()
            ind = cell(row, plan["industry"])
            if ind:
                agg.industry = str(ind).strip()[:255]

        agg.approvals += sum_cells(row, plan["appr"])
        agg.denials += sum_cells(row, plan["den"])
        agg.init_appr += sum_cells(row, plan["init_appr"])
        agg.init_den += sum_cells(row, plan["init_den"])
        agg.cont_appr += sum_cells(row, plan["cont_appr"])
        agg.cont_den += sum_cells(row, plan["cont_den"])

        fy = _to_year(cell(row, plan["fiscal_year"]))
        if fy:
            agg.last_fy = max(agg.last_fy or 0, fy)

    summary.employers_seen = len(aggs)
    _upsert(db, aggs, summary)
    db.commit()
    summary.message = (
        f"Imported {summary.rows_read} USCIS rows across "
        f"{summary.employers_seen} employers; updated "
        f"{summary.companies_upserted} companies."
    )
    return summary


def _upsert(db: Session, aggs: dict[str, _Agg], summary: UscisSummary) -> None:
    # Batch existing lookups to avoid a query per employer.
    norms = list(aggs.keys())
    existing: dict[str, models.Company] = {}
    CHUNK = 500
    for i in range(0, len(norms), CHUNK):
        batch = norms[i : i + CHUNK]
        found = db.execute(
            select(models.Company).where(
                models.Company.normalized_name.in_(batch)
            )
        ).scalars().all()
        for c in found:
            existing[c.normalized_name] = c

    for norm, agg in aggs.items():
        company = existing.get(norm)
        if company is None:
            company = models.Company(
                name=agg.display_name or norm, normalized_name=norm
            )
            db.add(company)
        company.uscis_initial_approvals = agg.init_appr
        company.uscis_initial_denials = agg.init_den
        company.uscis_continuing_approvals = agg.cont_appr
        company.uscis_continuing_denials = agg.cont_den
        company.uscis_last_fiscal_year = agg.last_fy
        if agg.industry and not company.industry:
            company.industry = agg.industry
        if agg.approvals > (company.h1b_filings_total or 0):
            company.h1b_filings_total = agg.approvals
        score, status = _score(agg)
        # Keep the stronger signal if DOL already set one higher.
        company.sponsorship_score = max(company.sponsorship_score or 0, score)
        if agg.approvals > 0:
            company.sponsorship_status = status
        summary.companies_upserted += 1


def _score(agg: _Agg) -> tuple[int, models.SponsorshipStatus]:
    """0-100 signal from approval volume + recency + approval rate."""
    total_dec = agg.approvals + agg.denials
    appr_rate = (agg.approvals / total_dec) if total_dec else 0

    if agg.approvals >= 500:
        vol = 55
    elif agg.approvals >= 100:
        vol = 48
    elif agg.approvals >= 25:
        vol = 38
    elif agg.approvals >= 5:
        vol = 26
    elif agg.approvals >= 1:
        vol = 14
    else:
        vol = 0

    # Recency: recent fiscal year is a strong "currently sponsoring" signal.
    from datetime import date

    cy = date.today().year
    years_ago = (cy - agg.last_fy) if agg.last_fy else 99
    if years_ago <= 1:
        rec = 25
    elif years_ago <= 2:
        rec = 18
    elif years_ago <= 4:
        rec = 8
    else:
        rec = 0

    quality = int(round(appr_rate * 20))
    score = min(100, vol + rec + quality)

    if agg.approvals > 0 and years_ago <= 2 and score >= 45:
        status = models.SponsorshipStatus.CURRENTLY_SPONSORING
    elif agg.approvals > 0:
        status = models.SponsorshipStatus.PREVIOUSLY_SPONSORED
    else:
        status = models.SponsorshipStatus.UNKNOWN
    return score, status
