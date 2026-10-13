"""SQLAlchemy ORM models for the Job Copilot.

Design notes:
- Job is separate from Application. You can discover a job today and apply later.
- Sponsorship is richer than yes/no: a status plus the evidence behind it.
- "Ageing" is never stored; it's computed from date_applied at read time.
- No plaintext job-portal credentials are ever stored.
"""
from __future__ import annotations

import enum
from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


# --- Enums -----------------------------------------------------------------

class ApplicationStatus(str, enum.Enum):
    SAVED = "Saved"
    READY_TO_APPLY = "Ready to Apply"
    APPLIED = "Applied"
    UNDER_REVIEW = "Under Review"
    RECRUITER_CONTACTED = "Recruiter Contacted"
    INTERVIEW = "Interview"
    TECHNICAL_INTERVIEW = "Technical Interview"
    FINAL_INTERVIEW = "Final Interview"
    OFFER = "Offer"
    REJECTED = "Rejected"
    WITHDRAWN = "Withdrawn"
    NO_RESPONSE = "No Response"
    CLOSED = "Closed"


class SponsorshipStatus(str, enum.Enum):
    CONFIRMED_YES = "Confirmed Yes"
    CONFIRMED_NO = "Confirmed No"
    REQUESTED = "Requested"
    UNKNOWN = "Unknown"
    PREVIOUSLY_SPONSORED = "Previously Sponsored"
    CURRENTLY_SPONSORING = "Currently Sponsoring"
    JOB_POSTING_SAYS_NO = "Job Posting Says No"


class SponsorshipEvidence(str, enum.Enum):
    DOL_LCA = "DOL LCA"
    COMPANY_CAREER_PAGE = "Company Career Page"
    JOB_DESCRIPTION = "Job Description"
    COMPANY_IMMIGRATION_POLICY = "Company Immigration Policy"
    RECRUITER_CONFIRMATION = "Recruiter Confirmation"
    USER_REPORT = "User Report"
    UNKNOWN = "Unknown"


class ContactType(str, enum.Enum):
    RECRUITER = "Recruiter"
    HIRING_MANAGER = "Hiring Manager"
    CYBERSECURITY_EMPLOYEE = "Cybersecurity Employee"
    ALUMNI = "Alumni"
    FORMER_COLLEAGUE = "Former Colleague"
    EMPLOYEE = "Employee"
    OTHER = "Other"


class FollowUpStatus(str, enum.Enum):
    PENDING = "Pending"
    DONE = "Done"
    SKIPPED = "Skipped"


# --- Models ----------------------------------------------------------------

class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    normalized_name: Mapped[str] = mapped_column(String(255), index=True)
    website: Mapped[str | None] = mapped_column(String(512), nullable=True)
    careers_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # H-1B/LCA history signals (populated in Phase 2 from DOL data).
    h1b_filings_total: Mapped[int] = mapped_column(Integer, default=0)
    h1b_filings_recent: Mapped[int] = mapped_column(Integer, default=0)
    h1b_certified: Mapped[int] = mapped_column(Integer, default=0)
    h1b_last_filing_year: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    # Semicolon-separated top titles / states seen in filings (display only).
    h1b_top_titles: Mapped[str | None] = mapped_column(Text, nullable=True)
    h1b_top_states: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # USCIS H-1B Employer Data Hub signals (actual petition decisions).
    uscis_initial_approvals: Mapped[int] = mapped_column(Integer, default=0)
    uscis_initial_denials: Mapped[int] = mapped_column(Integer, default=0)
    uscis_continuing_approvals: Mapped[int] = mapped_column(Integer, default=0)
    uscis_continuing_denials: Mapped[int] = mapped_column(Integer, default=0)
    uscis_last_fiscal_year: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )

    # 0-100 signal computed from filing volume + recency. NOT a guarantee.
    sponsorship_score: Mapped[int] = mapped_column(Integer, default=0)
    sponsorship_status: Mapped[SponsorshipStatus] = mapped_column(
        Enum(SponsorshipStatus), default=SponsorshipStatus.UNKNOWN
    )

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    jobs: Mapped[list["Job"]] = relationship(back_populates="company")
    contacts: Mapped[list["Contact"]] = relationship(back_populates="company")


class Job(Base):
    """A discovered opportunity. May or may not have an application yet."""

    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int | None] = mapped_column(
        ForeignKey("companies.id"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(255), index=True)
    normalized_title: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    job_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    source: Mapped[str | None] = mapped_column(String(255), nullable=True)

    sponsorship_status: Mapped[SponsorshipStatus] = mapped_column(
        Enum(SponsorshipStatus), default=SponsorshipStatus.UNKNOWN
    )
    sponsorship_evidence: Mapped[SponsorshipEvidence] = mapped_column(
        Enum(SponsorshipEvidence), default=SponsorshipEvidence.UNKNOWN
    )

    match_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    date_discovered: Mapped[date] = mapped_column(Date, default=date.today)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    company: Mapped["Company | None"] = relationship(back_populates="jobs")
    application: Mapped["Application | None"] = relationship(
        back_populates="job", uselist=False
    )


class ResumeVersion(Base):
    __tablename__ = "resume_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    label: Mapped[str] = mapped_column(String(255), index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    applications: Mapped[list["Application"]] = relationship(
        back_populates="resume_version"
    )


class Application(Base):
    """A concrete application submitted (or being prepared) for a Job."""

    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), index=True)
    resume_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("resume_versions.id"), nullable=True
    )

    status: Mapped[ApplicationStatus] = mapped_column(
        Enum(ApplicationStatus), default=ApplicationStatus.SAVED, index=True
    )
    date_applied: Mapped[date | None] = mapped_column(Date, nullable=True)

    ats_match: Mapped[int | None] = mapped_column(Integer, nullable=True)
    missing_keywords: Mapped[str | None] = mapped_column(Text, nullable=True)

    application_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    # Reference only (e.g. "Company SSO", "Workday profile") -- never a password.
    credential_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)

    response: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_contact: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    job: Mapped["Job"] = relationship(back_populates="application")
    resume_version: Mapped["ResumeVersion | None"] = relationship(
        back_populates="applications"
    )
    follow_ups: Mapped[list["FollowUp"]] = relationship(
        back_populates="application", cascade="all, delete-orphan"
    )

    @property
    def ageing(self) -> int | None:
        """Days since applied. Computed, never stored."""
        if self.date_applied is None:
            return None
        return (date.today() - self.date_applied).days


class Contact(Base):
    __tablename__ = "contacts"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int | None] = mapped_column(
        ForeignKey("companies.id"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255), index=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    department: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email_verified: Mapped[bool] = mapped_column(default=False)
    linkedin_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    contact_type: Mapped[ContactType] = mapped_column(
        Enum(ContactType), default=ContactType.OTHER
    )
    source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    date_contacted: Mapped[date | None] = mapped_column(Date, nullable=True)
    response: Mapped[str | None] = mapped_column(String(255), nullable=True)
    next_follow_up: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    company: Mapped["Company | None"] = relationship(back_populates="contacts")


class FollowUp(Base):
    __tablename__ = "follow_ups"

    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(
        ForeignKey("applications.id"), index=True
    )
    due_date: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[FollowUpStatus] = mapped_column(
        Enum(FollowUpStatus), default=FollowUpStatus.PENDING, index=True
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    application: Mapped["Application"] = relationship(back_populates="follow_ups")


class DolIngest(Base):
    """Tracks a DOL LCA download/import run so the UI can show status."""

    __tablename__ = "dol_ingests"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    filename: Mapped[str | None] = mapped_column(String(512), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending")  # pending/downloading/importing/done/error
    rows_read: Mapped[int] = mapped_column(Integer, default=0)
    companies_upserted: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class JobFetchRun(Base):
    """Tracks a background live-job fetch run so the UI can poll progress."""

    __tablename__ = "job_fetch_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    status: Mapped[str] = mapped_column(String(32), default="pending")  # pending/running/done/error
    companies_queried: Mapped[int] = mapped_column(Integer, default=0)
    jobs_seen: Mapped[int] = mapped_column(Integer, default=0)
    cyber_matched: Mapped[int] = mapped_column(Integer, default=0)
    inserted: Mapped[int] = mapped_column(Integer, default=0)
    duplicates: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
