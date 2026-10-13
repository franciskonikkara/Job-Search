"""Application configuration.

Loads settings from environment variables (and an optional .env file).
Keeps sensible zero-setup defaults so the app runs out of the box with SQLite.
"""
from __future__ import annotations

import os
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Local SQLite by default. Swap for a Postgres/Supabase URL later.
    database_url: str = "sqlite:///./data/jobcopilot.db"

    # Comma-separated list of allowed CORS origins for the frontend.
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # --- DOL H-1B / LCA disclosure data --------------------------------
    # The Office of Foreign Labor Certification publishes quarterly LCA
    # disclosure files. The exact filename rotates each fiscal quarter and
    # the CDN blocks non-browser clients, so this is overridable and the
    # downloader sends a browser User-Agent. Update this value (or pass a
    # url to the API) whenever DOL rotates the file.
    dol_source_url: str = (
        "https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/"
        "LCA_Disclosure_Data_FY2025_Q3.xlsx"
    )
    # Directory where downloaded/dropped-in DOL files live.
    data_dir: str = "./data"
    dol_download_dir: str = "./data/dol"
    # Browser-like UA to get past the DOL CDN bot filtering.
    dol_user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
    # USCIS H-1B Employer Data Hub CSV (per fiscal year). Like DOL, the exact
    # file rotates, so this is overridable. Download from:
    # https://www.uscis.gov/tools/reports-studies/h-1b-employer-data-hub-files
    uscis_source_url: str = ""

    # Default search engine base for generated bulletin/dork queries.
    search_engine_base: str = "https://www.google.com/search?q="

    # --- Jobright Daily H-1B jobs feed ---------------------------------
    # Jobright.ai publishes a daily-updated, openly consumable list of H-1B
    # tech jobs on GitHub (company, title, level, location, sponsorship tier,
    # apply link). We fetch the raw README and parse its markdown tables.
    # This repo focuses on SWE/PM/Marketing/Design; cyber roles appear within
    # the SWE category. Additional repos can be added for other categories.
    jobright_sources: str = ",".join([
        # H-1B-sponsored tech jobs (tiered 🏅/🥈).
        "https://raw.githubusercontent.com/jobright-ai/"
        "Daily-H1B-Jobs-In-Tech/master/README.md",
        # Entry-level / new-grad software engineering (includes cyber roles).
        "https://raw.githubusercontent.com/jobright-ai/"
        "2026-Software-Engineer-New-Grad/master/README.md",
        # Software engineering internships.
        "https://raw.githubusercontent.com/jobright-ai/"
        "2026-Software-Engineering-Internship/master/README.md",
    ])

    @property
    def jobright_sources_list(self) -> list[str]:
        return [u.strip() for u in self.jobright_sources.split(",") if u.strip()]

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    # Ensure the SQLite directory exists.
    if settings.database_url.startswith("sqlite:///"):
        db_path = settings.database_url.replace("sqlite:///", "", 1)
        db_dir = os.path.dirname(db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
    os.makedirs(settings.dol_download_dir, exist_ok=True)
    return settings
