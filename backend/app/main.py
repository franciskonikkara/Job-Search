"""FastAPI application entry point for the H-1B Cyber Job Copilot."""
from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .database import init_db
from .routers import (
    applications,
    contacts,
    dashboard,
    discover,
    followups,
    h1b,
    io_excel,
    jobs,
    outreach,
    resume,
    sponsors,
)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="H-1B Cyber Job Copilot",
    version="0.1.0",
    description="Job-search copilot with human approval. Phase 1 MVP.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(dashboard.router)
app.include_router(applications.router)
app.include_router(jobs.router)
app.include_router(contacts.router)
app.include_router(followups.router)
app.include_router(io_excel.router)
app.include_router(h1b.router)
app.include_router(sponsors.router)
app.include_router(discover.router)
app.include_router(resume.router)
app.include_router(outreach.router)


@app.get("/api/health", tags=["health"])
def health():
    return {"status": "ok"}


# Serve the bundled single-page frontend (zero-build, CDN React).
# Mounted last so it doesn't shadow the /api routes above.
_FRONTEND_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "frontend"
)
if os.path.isdir(_FRONTEND_DIR):
    app.mount(
        "/", StaticFiles(directory=_FRONTEND_DIR, html=True), name="frontend"
    )
