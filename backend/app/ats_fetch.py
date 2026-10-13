"""Live job fetching from public ATS (applicant tracking system) APIs.

These are official, publicly documented JSON endpoints that companies expose
to power their own job boards. They return ONLY currently-open postings, so
nothing is stale, and each posting has a real apply URL. No scraping, no
Google, no ToS violation.

Supported platforms:
  - Greenhouse: https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true
  - Lever:      https://api.lever.co/v0/postings/{slug}?mode=json
  - Ashby:      https://api.ashbyhq.com/posting-api/job-board/{slug}

Each company must be identified by (platform, slug). Not every company is on
every platform, so a wrong slug simply yields 0 jobs (handled gracefully).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import requests

_UA = {"User-Agent": "Mozilla/5.0 (compatible; JobCopilot/1.0)"}
_TIMEOUT = 25


@dataclass
class ATSJob:
    company: str
    title: str
    location: str | None
    url: str | None
    remote: bool
    platform: str
    posted: str | None = None


@dataclass
class ATSFetchResult:
    jobs: list[ATSJob] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _is_remote(text: str | None) -> bool:
    t = (text or "").lower()
    return "remote" in t or "anywhere" in t or "distributed" in t


def fetch_greenhouse(slug: str, company: str | None = None) -> ATSFetchResult:
    res = ATSFetchResult()
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=false"
    try:
        r = requests.get(url, headers=_UA, timeout=_TIMEOUT)
        if r.status_code != 200:
            res.errors.append(f"greenhouse:{slug} HTTP {r.status_code}")
            return res
        data = r.json()
        for j in data.get("jobs", []):
            loc = (j.get("location") or {}).get("name")
            res.jobs.append(ATSJob(
                company=company or slug,
                title=j.get("title", "").strip(),
                location=loc,
                url=j.get("absolute_url"),
                remote=_is_remote(loc),
                platform="greenhouse",
                posted=j.get("updated_at") or j.get("first_published"),
            ))
    except requests.RequestException as exc:
        res.errors.append(f"greenhouse:{slug} {exc}")
    return res


def fetch_lever(slug: str, company: str | None = None) -> ATSFetchResult:
    res = ATSFetchResult()
    url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
    try:
        r = requests.get(url, headers=_UA, timeout=_TIMEOUT)
        if r.status_code != 200:
            res.errors.append(f"lever:{slug} HTTP {r.status_code}")
            return res
        for j in r.json():
            cats = j.get("categories", {}) or {}
            loc = cats.get("location")
            wt = (cats.get("commitment") or "") + " " + (
                j.get("workplaceType") or ""
            )
            res.jobs.append(ATSJob(
                company=company or slug,
                title=(j.get("text") or "").strip(),
                location=loc,
                url=j.get("hostedUrl"),
                remote=_is_remote(loc) or _is_remote(wt)
                or (j.get("workplaceType") == "remote"),
                platform="lever",
                posted=str(j.get("createdAt")) if j.get("createdAt") else None,
            ))
    except requests.RequestException as exc:
        res.errors.append(f"lever:{slug} {exc}")
    return res


def fetch_ashby(slug: str, company: str | None = None) -> ATSFetchResult:
    res = ATSFetchResult()
    url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
    try:
        r = requests.get(url, headers=_UA, timeout=_TIMEOUT)
        if r.status_code != 200:
            res.errors.append(f"ashby:{slug} HTTP {r.status_code}")
            return res
        data = r.json()
        for j in data.get("jobs", []):
            loc = j.get("location")
            res.jobs.append(ATSJob(
                company=company or slug,
                title=(j.get("title") or "").strip(),
                location=loc,
                url=j.get("jobUrl") or j.get("applyUrl"),
                remote=bool(j.get("isRemote")) or _is_remote(loc),
                platform="ashby",
                posted=j.get("publishedDate"),
            ))
    except requests.RequestException as exc:
        res.errors.append(f"ashby:{slug} {exc}")
    return res


_FETCHERS = {
    "greenhouse": fetch_greenhouse,
    "lever": fetch_lever,
    "ashby": fetch_ashby,
}


def fetch_company(platform: str, slug: str, company: str | None = None) -> ATSFetchResult:
    fn = _FETCHERS.get(platform)
    if fn is None:
        r = ATSFetchResult()
        r.errors.append(f"unknown platform: {platform}")
        return r
    return fn(slug, company)
