"""Import the USCIS Employer Data Hub Excel files from the workspace root.

Usage:
    python import_employer_files.py

Imports both provided files (older first, then newer so recency wins) and
ranks companies by their H-1B approval history. Progress is written to
import_employer.log so you can watch it on these very large files.
"""
from __future__ import annotations

import os
import time

from app.database import SessionLocal, init_db
from app.uscis_import import import_uscis_file

# Older file first, newer second: the newer fiscal years then set the
# "last fiscal year" and recency-driven status/score.
WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
FILES = [
    os.path.join(WORKSPACE_ROOT, "Employer Information21-23.xlsx"),
    os.path.join(WORKSPACE_ROOT, "Employer Information_24-26.xlsx"),
]

LOG = "import_employer.log"


def log(msg: str) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    print(line)


def main() -> None:
    open(LOG, "w").close()
    init_db()
    for path in FILES:
        if not os.path.exists(path):
            log(f"MISSING: {path}")
            continue
        log(f"Importing {os.path.basename(path)} ...")
        t0 = time.time()
        db = SessionLocal()
        try:
            summary = import_uscis_file(db, path)
            dt = time.time() - t0
            log(
                f"  done in {dt:.1f}s -> rows={summary.rows_read} "
                f"employers={summary.employers_seen} "
                f"upserted={summary.companies_upserted}"
            )
            log(f"  message: {summary.message}")
        except Exception as exc:  # noqa: BLE001
            log(f"  ERROR: {exc}")
            import traceback

            log(traceback.format_exc())
        finally:
            db.close()
    log("ALL DONE")


if __name__ == "__main__":
    main()
