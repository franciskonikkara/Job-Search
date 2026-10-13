"""Small helpers for normalization and parsing shared across the app."""
from __future__ import annotations

import re
from datetime import date, datetime

from .models import ApplicationStatus, SponsorshipStatus

_WS = re.compile(r"\s+")
_COMPANY_SUFFIXES = re.compile(
    r"\b(inc|inc\.|llc|l\.l\.c\.|corp|corp\.|corporation|co|co\.|company|"
    r"ltd|ltd\.|limited|plc|group|holdings|usa)\b",
    re.IGNORECASE,
)


def normalize_name(value: str) -> str:
    """Lowercase, strip punctuation and common company suffixes for matching."""
    if not value:
        return ""
    v = value.strip().lower()
    v = _COMPANY_SUFFIXES.sub("", v)
    v = re.sub(r"[^a-z0-9 ]", " ", v)
    v = _WS.sub(" ", v).strip()
    return v


def normalize_title(value: str) -> str:
    if not value:
        return ""
    v = value.strip().lower()
    v = re.sub(r"[^a-z0-9 ]", " ", v)
    v = _WS.sub(" ", v).strip()
    return v


def parse_date(value) -> date | None:
    """Parse many date shapes (Excel serials, strings) into a date."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    s = str(value).strip()
    if not s:
        return None
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d", "%m-%d-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


# Map free-text status values (from an existing spreadsheet) to our enum.
_STATUS_ALIASES = {
    "applied": ApplicationStatus.APPLIED,
    "rejected": ApplicationStatus.REJECTED,
    "interview": ApplicationStatus.INTERVIEW,
    "interviewing": ApplicationStatus.INTERVIEW,
    "currently interviewing": ApplicationStatus.INTERVIEW,
    "offer": ApplicationStatus.OFFER,
    "saved": ApplicationStatus.SAVED,
    "ready to apply": ApplicationStatus.READY_TO_APPLY,
    "under review": ApplicationStatus.UNDER_REVIEW,
    "no response": ApplicationStatus.NO_RESPONSE,
    "withdrawn": ApplicationStatus.WITHDRAWN,
}


def parse_status(value) -> ApplicationStatus:
    if not value:
        return ApplicationStatus.SAVED
    key = str(value).strip().lower()
    return _STATUS_ALIASES.get(key, ApplicationStatus.APPLIED)


# Map free-text sponsorship values to our enum.
_SPONSOR_ALIASES = {
    "yes": SponsorshipStatus.CONFIRMED_YES,
    "no": SponsorshipStatus.CONFIRMED_NO,
    "requested": SponsorshipStatus.REQUESTED,
    "did not ask": SponsorshipStatus.UNKNOWN,
    "unknown": SponsorshipStatus.UNKNOWN,
    "previously sponsored": SponsorshipStatus.PREVIOUSLY_SPONSORED,
    "currently sponsoring": SponsorshipStatus.CURRENTLY_SPONSORING,
}


def parse_sponsorship(value) -> SponsorshipStatus:
    if not value:
        return SponsorshipStatus.UNKNOWN
    key = str(value).strip().lower()
    return _SPONSOR_ALIASES.get(key, SponsorshipStatus.UNKNOWN)
