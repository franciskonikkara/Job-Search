"""Parse a DOL LCA disclosure file and build the sponsor company database.

DOL files are large (hundreds of MB, ~1M rows) with columns like:
  EMPLOYER_NAME, CASE_STATUS, DECISION_DATE / RECEIVED_DATE, JOB_TITLE,
  WORKSITE_STATE / EMPLOYER_STATE, VISA_CLASS
Column names vary slightly across fiscal years, so we resolve them fuzzily.

We aggregate per employer:
  - total filings, certified filings, recent filings (last 2 FYs),
  - last filing year, top job titles, top worksite states,
then compute a 0-100 sponsorship *signal* (volume + recency + certified rate).

This is framed as FILING HISTORY, never a guarantee of sponsorship.
"""
from __future__ import annotations

import os
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models
from .utils import normalize_name

# H-1B (and related) visa classes we count. We keep H-1B primarily.
_VISA_CLASSES = {"H-1B", "H-1B1 CHILE", "H-1B1 SINGAPORE", "E-3 AUSTRALIAN"}

# Candidate column names -> canonical key. Matched case-insensitively.
_COLS = {
    "employer": ["EMPLOYER_NAME", "employer_name", "EMPLOYER_BUSINESS_NAME"],
    "status": ["CASE_STATUS", "case_status", "STATUS"],
    "decision_date": ["DECISION_DATE", "decision_date"],
    "received_date": ["RECEIVED_DATE", "received_date", "CASE_SUBMITTED"],
    "title": ["JOB_TITLE", "job_title", "SOC_TITLE"],
    "state": ["WORKSITE_STATE", "worksite_state", "EMPLOYER_STATE",
              "WORKSITE_STATE_1", "STATE"],
    "visa": ["VISA_CLASS", "visa_class"],
}

_RECENT_YEARS = 2


@dataclass
class _Agg:
    total: int = 0
    certified: int = 0
    recent: int = 0
    last_year: int | None = None
    titles: Counter = field(default_factory=Counter)
    states: Counter = field(default_factory=Counter)
    display_name: str = ""


@dataclass
class ImportSummary:
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


def _resolve_columns(available: list[str]) -> dict[str, str]:
    lower = {c.lower(): c for c in available}
    resolved: dict[str, str] = {}
    for key, candidates in _COLS.items():
        for cand in candidates:
            if cand.lower() in lower:
                resolved[key] = lower[cand.lower()]
                break
    return resolved


def _year_of(value) -> int | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        ts = pd.to_datetime(value, errors="coerce")
        if pd.isna(ts):
            return None
        return int(ts.year)
    except Exception:
        return None


def _iter_frames(path: str, usecols: list[str] | None):
    """Yield dataframes in chunks for csv, or a single frame for xlsx."""
    ext = os.path.splitext(path)[1].lower()
    if ext in (".csv", ".txt"):
        yield from pd.read_csv(
            path, usecols=usecols, chunksize=100_000,
            dtype=str, on_bad_lines="skip", low_memory=False,
        )
    else:
        # openpyxl can't stream easily; read once. Only the needed columns.
        df = pd.read_excel(path, usecols=usecols, dtype=str)
        yield df


def _score(agg: _Agg, current_year: int) -> tuple[int, models.SponsorshipStatus]:
    """0-100 signal from volume + recency + certified rate."""
    # Volume component (log-ish, capped).
    if agg.total >= 100:
        vol = 45
    elif agg.total >= 25:
        vol = 35
    elif agg.total >= 5:
        vol = 25
    elif agg.total >= 1:
        vol = 15
    else:
        vol = 0

    # Recency component.
    years_ago = (current_year - agg.last_year) if agg.last_year else 99
    if years_ago <= 1:
        rec = 35
    elif years_ago <= 2:
        rec = 25
    elif years_ago <= 4:
        rec = 12
    else:
        rec = 0

    # Certified-rate component.
    cert_rate = (agg.certified / agg.total) if agg.total else 0
    cert = int(round(cert_rate * 20))

    score = min(100, vol + rec + cert)

    if agg.recent > 0 and score >= 55:
        status = models.SponsorshipStatus.CURRENTLY_SPONSORING
    elif agg.total > 0:
        status = models.SponsorshipStatus.PREVIOUSLY_SPONSORED
    else:
        status = models.SponsorshipStatus.UNKNOWN
    return score, status


def import_lca_file(db: Session, path: str) -> ImportSummary:
    summary = ImportSummary()
    current_year = date.today().year

    # First peek to resolve columns.
    ext = os.path.splitext(path)[1].lower()
    if ext in (".csv", ".txt"):
        head = pd.read_csv(path, nrows=1, dtype=str)
    else:
        head = pd.read_excel(path, nrows=1, dtype=str)
    resolved = _resolve_columns(list(head.columns))
    if "employer" not in resolved:
        summary.message = (
            "Could not find an EMPLOYER_NAME column. Is this a DOL LCA "
            "disclosure file?"
        )
        return summary

    usecols = list(resolved.values())
    aggs: dict[str, _Agg] = defaultdict(_Agg)

    for frame in _iter_frames(path, usecols):
        # Rename to canonical keys.
        rename = {v: k for k, v in resolved.items()}
        frame = frame.rename(columns=rename)
        for row in frame.itertuples(index=False):
            summary.rows_read += 1
            employer = getattr(row, "employer", None)
            if not employer or str(employer).strip() == "":
                continue
            # Optional visa filter (keep row if no visa column present).
            visa = getattr(row, "visa", None)
            if visa is not None and not (isinstance(visa, float) and pd.isna(visa)):
                if str(visa).strip().upper() not in _VISA_CLASSES:
                    continue

            norm = normalize_name(str(employer))
            if not norm:
                continue
            agg = aggs[norm]
            if not agg.display_name:
                agg.display_name = str(employer).strip().title()
            agg.total += 1

            status = getattr(row, "status", None)
            if status and "CERTIF" in str(status).upper():
                agg.certified += 1

            yr = _year_of(getattr(row, "decision_date", None)) or _year_of(
                getattr(row, "received_date", None)
            )
            if yr:
                agg.last_year = max(agg.last_year or 0, yr)
                if current_year - yr <= _RECENT_YEARS:
                    agg.recent += 1

            title = getattr(row, "title", None)
            if title and not (isinstance(title, float) and pd.isna(title)):
                agg.titles[str(title).strip().title()] += 1
            st = getattr(row, "state", None)
            if st and not (isinstance(st, float) and pd.isna(st)):
                agg.states[str(st).strip().upper()] += 1

    summary.employers_seen = len(aggs)

    # Upsert companies.
    for norm, agg in aggs.items():
        score, spons = _score(agg, current_year)
        company = db.execute(
            select(models.Company).where(models.Company.normalized_name == norm)
        ).scalar_one_or_none()
        top_titles = "; ".join(t for t, _ in agg.titles.most_common(5))
        top_states = "; ".join(s for s, _ in agg.states.most_common(5))
        if company is None:
            company = models.Company(
                name=agg.display_name or norm,
                normalized_name=norm,
            )
            db.add(company)
        company.h1b_filings_total = agg.total
        company.h1b_filings_recent = agg.recent
        company.h1b_certified = agg.certified
        company.h1b_last_filing_year = agg.last_year
        company.h1b_top_titles = top_titles or None
        company.h1b_top_states = top_states or None
        company.sponsorship_score = score
        company.sponsorship_status = spons
        summary.companies_upserted += 1

    db.commit()
    summary.message = (
        f"Imported {summary.rows_read} rows across {summary.employers_seen} "
        f"employers; updated {summary.companies_upserted} companies."
    )
    return summary
