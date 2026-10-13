# H-1B Cyber Job Copilot

A job-search copilot for cybersecurity roles with H-1B sponsorship history in mind.
Built with a **human-approval** philosophy: the app does research and prepares
materials, but you approve every action. It does not auto-apply or automate
LinkedIn.

This repository currently contains **Phase 1 (MVP)**: a working application
tracker with a dashboard, jobs-vs-applications separation, automatic aging,
follow-up reminders, contacts, and Excel import/export.

## What's in Phase 1

- **Dashboard** with live metrics (total applications, interviews, offers,
  rejections, pending, follow-ups due, saved-not-applied).
- **Applications** table with status dropdowns, detailed visa-sponsorship
  fields, and **automatic aging** (computed from the applied date, never stored).
- **Jobs are separate from Applications** — you can discover a job today and
  apply later. Duplicate jobs (same company + title) are detected.
- **Follow-ups** — schedule a reminder on any application; the dashboard shows
  what's due.
- **Contacts** — recruiters/hiring managers with a verified-email flag.
- **Excel import** from your existing tracker (maps your columns, normalizes
  statuses and dates, skips duplicates). **The username/password column is
  ignored on purpose.**
- **Excel export** to a multi-sheet workbook (Applications, Contacts,
  Follow-ups, Analytics).

## Security note

This app **never stores job-portal usernames or passwords**. The importer
detects and ignores any credential column. If you pasted real passwords into
notes anywhere, change them. Applications have an optional
`credential_reference` field for a *label only* (e.g. "Workday profile"),
never a secret.

## Tech stack (all free for local use)

| Layer     | Choice                          |
|-----------|---------------------------------|
| Backend   | Python + FastAPI                |
| Database  | SQLite (zero setup)             |
| Frontend  | React via CDN (no build step)   |
| Excel     | openpyxl                        |

SQLite and the CDN-React frontend keep the MVP at **$0** and runnable with one
command. Both are designed to be swapped later (SQLite → Postgres/Supabase,
CDN React → Next.js) without changing the API.

## Running it

Requires Python 3.11+ (tested on 3.13).

```powershell
cd backend

# One-time setup
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# Optional: load the sample tracker rows
.\.venv\Scripts\python.exe seed.py

# Start the app (serves both API and dashboard)
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

Then open **http://127.0.0.1:8000/** for the dashboard.
API docs are at **http://127.0.0.1:8000/docs**.

## Project layout

```
backend/
  app/
    main.py          FastAPI app; serves API + frontend
    config.py        Settings (DB URL, CORS)
    database.py      Engine, session, Base, init_db
    models.py        Company, Job, Application, Contact, FollowUp, ResumeVersion
    schemas.py       Pydantic request/response models
    crud.py          Shared data-access helpers + dashboard aggregation
    utils.py         Normalization + status/date/sponsorship parsing
    excel_io.py      Excel import (your tracker) and export (4 sheets)
    routers/         applications, jobs, contacts, followups, dashboard, excel
  seed.py            Loads the sample tracker rows (no credentials)
  requirements.txt
frontend/
  index.html         Single-page dashboard (CDN React + Babel)
  app.js             Dashboard UI
  styles.css
```

## Data model highlights

- **Job** ≠ **Application**. A `Job` is a discovered opportunity; an
  `Application` is a concrete submission linked to one job.
- **Sponsorship** is richer than yes/no: a *status*
  (Confirmed Yes/No, Requested, Previously Sponsored, Currently Sponsoring,
  Job Posting Says No, Unknown) plus the *evidence* behind it (DOL LCA,
  career page, job description, recruiter, etc.).
- **Aging** is computed on read from `date_applied`, so it's always current.

## Phase 2 — H-1B sponsor intelligence + job discovery (built)

New tabs and features:

- **Sponsors tab** — an H-1B sponsor database built from public **DOL LCA
  disclosure data**. Each company shows total filings, recent filings, last
  filing year, top titles/states, and a **0–100 sponsorship signal** (volume +
  recency + certified rate). This is *filing history*, not a guarantee.
- **DOL data loading** (Data tab):
  - **Auto-download & Import** — the app downloads the DOL file with a
    browser-like User-Agent and imports it in the background.
  - **Import DOL File** — a fallback for when DOL's CDN blocks automated
    downloads (it often does): download the file yourself and drop it in.
  - The source URL is configurable (`DOL_SOURCE_URL`) because DOL rotates the
    filename each fiscal quarter.
- **Discover tab** — the **bulletin / Google-dork method** (same idea as
  briansjobsearch.com). Pick a role, remote on/off, exclusions (e.g.
  `jobgether`), and it generates ready-to-click search links across ATS
  platforms:
  `"SOC Analyst" site:greenhouse.io remote -jobgether`, `site:lever.co`, Ashby,
  Workday, and more. You click, review real postings, apply, then add the role
  via **+ Add Application**.
- **Company-scoped search** — from a sponsor row, generate queries that search
  cybersecurity jobs *within that specific H-1B sponsor*, e.g.
  `"Cybersecurity" "Acme Security Inc" site:greenhouse.io`. This is the
  H-1B-list → jobs chaining.

### Two official H-1B data sources

The app uses the same two public primary sources that commercial sites (e.g.
h1bgrader.com) are built on. Those sites block scraping and resell curated
access, so we go straight to the government sources instead:

1. **DOL LCA disclosure data** — Labor Condition Application *filings*.
   Download `LCA_Disclosure_Data_FYxxxx_Qx.xlsx` from
   https://www.dol.gov/agencies/eta/foreign-labor/performance
2. **USCIS H-1B Employer Data Hub** — actual petition *approvals/denials* by
   employer and fiscal year. Download a fiscal-year CSV from
   https://www.uscis.gov/tools/reports-studies/h-1b-employer-data-hub-files

The USCIS approvals are a stronger "has this company sponsored H-1B" signal
than filings alone, so the app blends both into one 0–100 score.

### Loading the data

1. Go to the **Data** tab.
2. For each source, try **Auto-download & Import**. If the site blocks the
   automated download (DOL's CDN often does), download the file yourself and
   use **Import DOL File** / **Import USCIS File**.
3. Files are large (DOL ~1M rows); the importer parses in chunks and
   aggregates by employer.

### DOL config (optional)

In `.env` (see `.env.example`):

```
DOL_SOURCE_URL=https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2025_Q3.xlsx
```

## Schema changes note

Phase 2 added columns to the `companies` table. SQLite's `create_all` does not
alter existing tables, so if you built the DB under Phase 1 you'll need to
recreate it (delete `backend/data/jobcopilot.db` and run `seed.py`). A future
step would add Alembic migrations to avoid manual resets.

## Phase 3 — Rank sponsors from the USCIS Employer Data Hub (built)

The two `Employer Information*.xlsx` files in the repo root are **USCIS H-1B
Employer Data Hub** exports (FY2021–2023 and FY2024–2026). They're small on
disk but huge uncompressed (130 MB and 312 MB of XML, ~600k rows combined), so
pandas/openpyxl can't open them without hanging.

What was added:

- **`app/xlsx_stream.py`** — a memory-safe streaming xlsx reader (SAX-style
  `iterparse`) that yields one row at a time, so these giant files parse in
  seconds with bounded memory.
- **`app/uscis_import.py`** — rewritten to stream and to sum *all* USCIS
  decision categories (New Employment, Continuation, Change with Same Employer,
  New Concurrent, Change of Employer, Amended — approvals and denials),
  aggregate per employer, and compute the 0–100 sponsorship score.
- **`import_employer_files.py`** — one command to load both files and rank
  every employer by real H-1B approval history.

### Loading the provided files

```powershell
cd backend
.\.venv\Scripts\python.exe import_employer_files.py
```

This imports ~600k rows into ~163k companies in about 80 seconds. The
**Sponsors** tab then shows them ranked (Amazon, Google, Microsoft, Apple,
Meta, TCS, Deloitte, etc. at the top). From any sponsor, click **Links** to
find its careers page and generate a bulletin search for a chosen
cybersecurity role scoped to that company, e.g.
`"Cloud Security Engineer" "Amazon Com Services Llc" site:greenhouse.io remote`.

That completes the requested flow: **rank companies by sponsorship history →
open their careers → find cybersecurity jobs**, all with clickable links you
review and apply to yourself.

## Phase 4 — Live job feed, resume/ATS, outreach, de-duplication (built)

**Jobs tab — real H-1B postings (Jobright feed).** Pulls currently-open,
H-1B-sponsored tech jobs from Jobright.ai's openly published
`Daily-H1B-Jobs-In-Tech` GitHub feed (compliant and free — Jobright itself has
no public API and blocks scraping, so we use their public feed). Fetches ~1,400
jobs daily, filters to cybersecurity roles, links each to its sponsor company,
dedupes, and lets you open + mark applied into the tracker.

**Resume tab — tailoring & ATS match (rule-based, no API).** Paste your master
resume and a job description; it scores the match (overall / skills / keyword
coverage), lists matched skills and missing keywords, and surfaces your most
relevant bullets. It **never invents experience** — missing keywords are shown
as "add only if you truly have them."

**Outreach tab — draft generation (human-approved).** Templates for recruiter
email, referral request, follow-up, LinkedIn connection note / message, and
cover letter, filled with your real details. Nothing is sent automatically;
you review and copy. (LinkedIn stays manual by design.)

**Company de-duplication.** USCIS files employers under many spelling and
abbreviation variants. `dedupe_companies.py` conservatively merges only
variants of the *same* full name (e.g. "Tata Consultancy Services" +
"Tata Consultancy Svcs"), summing their stats, while keeping genuinely
different entities separate (Amazon Advertising ≠ Amazon Studios; Tata Elxsi ≠
Tatango).

```powershell
cd backend
.\.venv\Scripts\python.exe dedupe_companies.py          # dry run (preview)
.\.venv\Scripts\python.exe dedupe_companies.py --apply  # perform merge
```

On the provided data this merged 1,046 groups (~1,059 duplicate records).

## Roadmap (ideas)

- Optional LLM upgrade for resume/outreach quality (behind an API key).
- Contacts UI tab.
- Scheduled daily job refresh.

All phases follow the human-approval principle: no auto-applying, no automated
LinkedIn activity, no scraping of private/paywalled data.
