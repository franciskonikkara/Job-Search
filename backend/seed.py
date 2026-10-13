"""Seed the database with the user's sample tracker rows.

Credentials from the original spreadsheet are intentionally excluded.
Run once:  python seed.py
"""
from __future__ import annotations

from datetime import date

from app.database import SessionLocal, init_db
from app import crud, schemas
from app.models import Application

SAMPLE = [
    {
        "company_name": "Hilton",
        "position": "2026 Corporate Summer Internship - Technology (Cyber, Engineering, Product Management)",
        "status": "Rejected",
        "sponsorship_status": "Unknown",  # "did not ask"
        "link": "https://hilton.taleo.net/careersection/hil_corp_ext/mysubmissions.ftl",
        "date_applied": date(2025, 9, 15),
    },
    {
        "company_name": "Navy Federal Careers",
        "position": "Intern - Year Round (Security/Cyber Governance & Risk Management) - 26574",
        "status": "Rejected",
        "sponsorship_status": "Unknown",
        "date_applied": date(2025, 9, 15),
        "notes": "Contact: careers@hr.navyfederal.org",
    },
    {
        "company_name": "Riley Sentinel",
        "position": "RileySENTINEL Security Analyst Internship Program",
        "status": "Applied",
        "sponsorship_status": "Unknown",
        "date_applied": date(2025, 9, 15),
    },
    {
        "company_name": "MITRE",
        "position": "Internships in Computer Science or Software Engineering (R115479)",
        "status": "Applied",
        "sponsorship_status": "Requested",
        "date_applied": date(2025, 9, 15),
    },
    {
        "company_name": "BDO USA",
        "position": "Advisory Intern, Data Forensics - Summer 2026",
        "status": "Rejected",
        "sponsorship_status": "Requested",
        "link": "https://ebqb.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/BDOEntryLevelCareers/my-profile",
        "date_applied": date(2025, 9, 15),
    },
]


def main() -> None:
    init_db()
    db = SessionLocal()
    try:
        if db.query(Application).count() > 0:
            print("Database already has applications; skipping seed.")
            return
        for row in SAMPLE:
            crud.create_application(db, schemas.ApplicationCreate(**row))
        db.commit()
        print(f"Seeded {len(SAMPLE)} applications.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
