"""Fetch and parse Jobright.ai's Daily-H1B-Jobs-In-Tech feed.

Jobright publishes an openly consumable, daily-updated list of H-1B-sponsored
tech jobs on GitHub as a Markdown README. Each job is a pipe-delimited table
row inside <details> sections (Software Engineer, Product Manager, etc.):

  | **[Company](url)** | Job Title | Level | Location | 🏅/🥈 | [apply](url) | Date |

Rules we handle:
  - The company cell is `**[Name](company_url)**`, OR `↳` meaning "same company
    as the previous row" (Jobright groups multiple roles under one employer).
  - H-1B tier: 🏅 = sponsorship explicitly in the JD; 🥈 = company sponsored
    this category in the past ~3 years.
  - Some rows have an extra location cell (a second location); we tolerate a
    variable number of columns and locate the emoji / apply / date positions.

This is a compliant, free source (meant to be consumed) rather than scraping a
protected site.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime

import requests

from .config import get_settings

settings = get_settings()

_LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]*)\)")
_BOLD_LINK_RE = re.compile(r"\*\*\[([^\]]+)\]\(([^)]*)\)\*\*")
_TIER_GOLD = "🏅"
_TIER_SILVER = "🥈"


@dataclass
class JobrightJob:
    company: str
    company_url: str | None
    title: str
    level: str | None
    location: str | None
    h1b_tier: str  # "explicit" | "history" | "unknown"
    apply_url: str | None
    date_posted: date | None
    category: str | None = None


@dataclass
class FetchResult:
    jobs: list[JobrightJob] = field(default_factory=list)
    source_url: str = ""
    error: str | None = None


def _parse_date(text: str) -> date | None:
    text = (text or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%b %d, %Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    # New-grad feed uses "Sep 18" (no year). Assume the current year, but if
    # that lands in the future (e.g. parsing in January), roll back a year.
    for fmt in ("%b %d", "%B %d"):
        try:
            d = datetime.strptime(text, fmt).date()
            today = date.today()
            d = d.replace(year=today.year)
            if (d - today).days > 30:
                d = d.replace(year=today.year - 1)
            return d
        except ValueError:
            continue
    return None


# Work-model values that appear as their own column in the new-grad feed.
_WORK_MODELS = {"remote", "on site", "onsite", "hybrid", "in person"}


def _split_row(line: str) -> list[str]:
    """Split a markdown table row into trimmed cells."""
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [c.strip() for c in line.split("|")]


def _is_separator(cells: list[str]) -> bool:
    return all(set(c) <= {"-", ":", " "} and c for c in cells if c != "")


def parse_markdown(md: str) -> list[JobrightJob]:
    jobs: list[JobrightJob] = []
    current_category: str | None = None
    last_company: str | None = None
    last_company_url: str | None = None

    for raw in md.splitlines():
        line = raw.strip()

        # Track the <summary>Category</summary> section headings.
        m = re.search(r"<summary>(.*?)</summary>", line, re.IGNORECASE)
        if m:
            current_category = re.sub(r"<[^>]+>", "", m.group(1)).strip()
            continue

        if not line.startswith("|"):
            continue
        cells = _split_row(line)
        if len(cells) < 5:
            continue
        # Skip header + separator rows.
        joined = " ".join(cells).lower()
        if "job title" in joined and "company" in joined:
            continue
        if _is_separator(cells):
            continue

        company_cell = cells[0]

        # Company: bold-link, plain link, '↳' continuation, or empty.
        if company_cell in ("↳", "⤷", "") or company_cell.startswith("↳"):
            company = last_company
            company_url = last_company_url
            title_idx = 1
        else:
            bm = _BOLD_LINK_RE.search(company_cell)
            lm = _LINK_RE.search(company_cell)
            if bm:
                company, company_url = bm.group(1).strip(), bm.group(2).strip()
            elif lm:
                company, company_url = lm.group(1).strip(), lm.group(2).strip()
            else:
                company = re.sub(r"[*\[\]]", "", company_cell).strip() or None
                company_url = None
            last_company, last_company_url = company, company_url
            title_idx = 1

        if not company:
            continue

        title_cell = cells[title_idx] if len(cells) > title_idx else ""
        # In the new-grad/internship layout the TITLE is a bold-link that also
        # carries the apply URL. Extract both the text and the URL here.
        apply_url = None
        tm = _BOLD_LINK_RE.search(title_cell) or _LINK_RE.search(title_cell)
        if tm:
            title = tm.group(1).strip()
            url_in_title = tm.group(2).strip()
            if "jobright" in url_in_title or "/jobs/" in url_in_title:
                apply_url = url_in_title
        else:
            title = re.sub(r"\*+", "", title_cell).strip()
        if not title:
            continue

        # Locate remaining special cells by content rather than fixed index,
        # since the two feed layouts differ in column count/order.
        tier = "unknown"
        date_posted = None
        level = None
        work_model = None
        location_parts: list[str] = []

        for c in cells[title_idx + 1 :]:
            if _TIER_GOLD in c:
                tier = "explicit"
                continue
            if _TIER_SILVER in c:
                tier = "history"
                continue
            am = _LINK_RE.search(c)
            if am and ("apply" in c.lower() or "jobright" in am.group(2)):
                apply_url = am.group(2).strip()
                continue
            d = _parse_date(c)
            if d is not None:
                date_posted = d
                continue
            if c.strip().lower() in _WORK_MODELS:
                work_model = c.strip()
                continue
            # Heuristic: level cells contain seniority words.
            if re.search(
                r"intern|junior|mid|senior|staff|principal|lead|director|"
                r"vp|c-level|entry|associate|manager",
                c, re.IGNORECASE,
            ) and len(c) < 60 and level is None:
                level = c
                continue
            if c:
                location_parts.append(c)

        location = ", ".join(p for p in location_parts if p) or None
        # Fold the work model into the location display when present.
        if work_model:
            location = f"{location} ({work_model})" if location else work_model

        jobs.append(JobrightJob(
            company=company, company_url=company_url, title=title,
            level=level, location=location, h1b_tier=tier,
            apply_url=apply_url, date_posted=date_posted,
            category=current_category,
        ))

    return jobs


def fetch_jobright(url: str | None = None, timeout: int = 30) -> FetchResult:
    url = url or settings.jobright_sources_list[0]
    result = FetchResult(source_url=url)
    headers = {"User-Agent": settings.dol_user_agent}
    try:
        resp = requests.get(url, headers=headers, timeout=timeout)
        resp.raise_for_status()
        result.jobs = parse_markdown(resp.text)
    except requests.RequestException as exc:
        result.error = f"Could not fetch Jobright feed: {exc}"
    return result


def fetch_all(urls: list[str] | None = None, timeout: int = 30) -> FetchResult:
    """Fetch and combine jobs from every configured Jobright source.

    A failure on one source is recorded but does not abort the others.
    """
    urls = urls or settings.jobright_sources_list
    combined = FetchResult(source_url="; ".join(urls))
    errors: list[str] = []
    for u in urls:
        r = fetch_jobright(u, timeout=timeout)
        if r.error:
            errors.append(r.error)
        else:
            combined.jobs.extend(r.jobs)
    if errors and not combined.jobs:
        combined.error = " | ".join(errors)
    return combined
