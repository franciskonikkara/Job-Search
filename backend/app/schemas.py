"""Pydantic schemas for API request/response bodies."""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from .models import (
    ApplicationStatus,
    ContactType,
    FollowUpStatus,
    SponsorshipEvidence,
    SponsorshipStatus,
)


# --- Company ---------------------------------------------------------------

class CompanyBase(BaseModel):
    name: str
    website: str | None = None
    careers_url: str | None = None
    industry: str | None = None
    sponsorship_status: SponsorshipStatus = SponsorshipStatus.UNKNOWN


class CompanyOut(CompanyBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    normalized_name: str
    h1b_filings_total: int
    h1b_filings_recent: int


# --- Job -------------------------------------------------------------------

class JobBase(BaseModel):
    title: str
    description: str | None = None
    location: str | None = None
    job_url: str | None = None
    source: str | None = None
    sponsorship_status: SponsorshipStatus = SponsorshipStatus.UNKNOWN
    sponsorship_evidence: SponsorshipEvidence = SponsorshipEvidence.UNKNOWN
    match_score: int | None = None


class JobCreate(JobBase):
    company_name: str | None = None
    date_discovered: date | None = None


class JobOut(JobBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    company_id: int | None
    date_discovered: date
    company: CompanyOut | None = None


# --- Resume version --------------------------------------------------------

class ResumeVersionBase(BaseModel):
    label: str
    notes: str | None = None


class ResumeVersionOut(ResumeVersionBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime


# --- Follow-up -------------------------------------------------------------

class FollowUpBase(BaseModel):
    due_date: date
    status: FollowUpStatus = FollowUpStatus.PENDING
    note: str | None = None


class FollowUpCreate(FollowUpBase):
    application_id: int


class FollowUpUpdate(BaseModel):
    due_date: date | None = None
    status: FollowUpStatus | None = None
    note: str | None = None


class FollowUpOut(FollowUpBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    application_id: int


# --- Application -----------------------------------------------------------

class ApplicationBase(BaseModel):
    status: ApplicationStatus = ApplicationStatus.SAVED
    date_applied: date | None = None
    ats_match: int | None = None
    missing_keywords: str | None = None
    application_url: str | None = None
    credential_reference: str | None = None
    response: str | None = None
    last_contact: date | None = None
    notes: str | None = None
    resume_version_id: int | None = None


class ApplicationCreate(ApplicationBase):
    # Either link an existing job by id, or create one inline.
    job_id: int | None = None
    company_name: str | None = None
    position: str | None = None
    description: str | None = None
    link: str | None = None
    location: str | None = None
    sponsorship_status: SponsorshipStatus = SponsorshipStatus.UNKNOWN


class ApplicationUpdate(BaseModel):
    status: ApplicationStatus | None = None
    date_applied: date | None = None
    ats_match: int | None = None
    missing_keywords: str | None = None
    application_url: str | None = None
    credential_reference: str | None = None
    response: str | None = None
    last_contact: date | None = None
    notes: str | None = None
    resume_version_id: int | None = None


class ApplicationOut(ApplicationBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    job_id: int
    ageing: int | None = None
    job: JobOut
    resume_version: ResumeVersionOut | None = None
    follow_ups: list[FollowUpOut] = []


# --- Contact ---------------------------------------------------------------

class ContactBase(BaseModel):
    name: str
    title: str | None = None
    department: str | None = None
    email: str | None = None
    email_verified: bool = False
    linkedin_url: str | None = None
    contact_type: ContactType = ContactType.OTHER
    source: str | None = None
    date_contacted: date | None = None
    response: str | None = None
    next_follow_up: date | None = None
    notes: str | None = None


class ContactCreate(ContactBase):
    company_name: str | None = None


class ContactUpdate(BaseModel):
    name: str | None = None
    title: str | None = None
    department: str | None = None
    email: str | None = None
    email_verified: bool | None = None
    linkedin_url: str | None = None
    contact_type: ContactType | None = None
    source: str | None = None
    date_contacted: date | None = None
    response: str | None = None
    next_follow_up: date | None = None
    notes: str | None = None


class ContactOut(ContactBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    company_id: int | None
    company: CompanyOut | None = None


# --- Dashboard -------------------------------------------------------------

class StatusCount(BaseModel):
    status: str
    count: int


class DashboardStats(BaseModel):
    total_applications: int
    applied_this_week: int
    interviews: int
    offers: int
    rejections: int
    pending_response: int
    follow_ups_due: int
    jobs_saved_not_applied: int
    by_status: list[StatusCount]
    by_sponsorship: list[StatusCount]


# --- Sponsors (H-1B) -------------------------------------------------------

class SponsorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    h1b_filings_total: int
    h1b_filings_recent: int
    h1b_certified: int
    h1b_last_filing_year: int | None
    h1b_top_titles: str | None
    h1b_top_states: str | None
    uscis_initial_approvals: int
    uscis_continuing_approvals: int
    uscis_initial_denials: int
    uscis_continuing_denials: int
    uscis_last_fiscal_year: int | None
    sponsorship_score: int
    sponsorship_status: SponsorshipStatus
    careers_url: str | None


# --- DOL ingest ------------------------------------------------------------

class DolIngestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    source_url: str | None
    filename: str | None
    status: str
    rows_read: int
    companies_upserted: int
    message: str | None


class DolDownloadRequest(BaseModel):
    url: str | None = None


# --- Bulletin / discover ---------------------------------------------------

class QueryOut(BaseModel):
    label: str
    query: str
    url: str


class DiscoverRequest(BaseModel):
    role: str
    location_mode: str = "any"  # remote | onsite | any
    company: str | None = None
    exclusions: list[str] = []
    targets: list[str] = []


# --- Job fetching (Jobright) ----------------------------------------------

class JobFetchRequest(BaseModel):
    entry_only: bool = False
    remote_only: bool = False
    include_sponsors: bool = False  # also query top H-1B sponsors' ATS boards


class JobApplyRequest(BaseModel):
    status: ApplicationStatus = ApplicationStatus.APPLIED


class JobFetchRunOut(BaseModel):
    id: int
    status: str  # pending | running | done | error
    companies_queried: int
    jobs_seen: int
    cyber_matched: int
    inserted: int
    duplicates: int
    message: str | None = None


class JobFetchResult(BaseModel):
    companies_queried: int
    jobs_seen: int
    cyber_matched: int
    inserted: int
    duplicates: int
    errors: list[str] = []


# --- Resume / ATS matching -------------------------------------------------

class ResumeMatchRequest(BaseModel):
    resume: str
    job_description: str
    job_id: int | None = None  # optionally pull the JD from a stored job


class ResumeMatchResult(BaseModel):
    overall: int
    skills_match: int
    keyword_coverage: int
    matched_skills: list[str]
    missing_skills: list[str]
    jd_skills: list[str]
    suggested_bullets: list[str]
    notes: list[str]


class ResumeTailorRequest(BaseModel):
    resume: str
    job_description: str
    job_id: int | None = None


class ResumeTailorResult(BaseModel):
    tailored_resume: str
    matched_keywords: list[str]
    injected_keywords: list[str]
    gap_keywords: list[str]
    before_score: int
    after_score: int
    notes: list[str]


# --- Outreach drafting -----------------------------------------------------

class OutreachRequest(BaseModel):
    kind: str
    company: str = ""
    role: str = ""
    contact_name: str = ""
    your_name: str = ""
    your_background: str = ""
    highlight: str = ""
    shared_context: str = ""


class OutreachDraftOut(BaseModel):
    kind: str
    subject: str
    body: str


# --- Resume tailoring (iterative rewrite) ----------------------------------

class ResumeTailorRequest(BaseModel):
    resume: str
    job_description: str
    job_id: int | None = None


class ResumeTailorResult(BaseModel):
    tailored_resume: str
    matched_keywords: list[str]
    injected_keywords: list[str]
    gap_keywords: list[str]
    before_score: int
    after_score: int
    notes: list[str]
