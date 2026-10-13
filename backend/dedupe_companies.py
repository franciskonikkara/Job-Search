"""Consolidate duplicate companies (spelling/abbreviation variants).

Usage:
    python dedupe_companies.py            # dry run (shows what would merge)
    python dedupe_companies.py --apply    # actually merge

Only merges companies whose fully-expanded canonical name is identical, so it
combines things like "Tata Consultancy Services" / "Tata Consultancy Svcs" but
never merges distinct entities that merely share a prefix (Amazon Advertising
vs Amazon Studios) or unrelated look-alikes (Tata Elxsi vs Tatango).
"""
from __future__ import annotations

import sys

from app.database import SessionLocal, init_db
from app.dedupe import deduplicate


def main() -> None:
    apply = "--apply" in sys.argv
    init_db()
    lines: list[str] = []

    def out(msg: str = "") -> None:
        print(msg)
        lines.append(msg)

    db = SessionLocal()
    try:
        result = deduplicate(db, dry_run=not apply)
        out(f"dry_run={result.dry_run}")
        out(f"groups that {'were' if apply else 'would be'} merged: "
            f"{result.groups_merged}")
        out(f"companies {'removed' if apply else 'that would be removed'}: "
            f"{result.companies_removed}")
        out("\nExamples:")
        for ex in result.examples:
            out("  " + ex)
        if not apply:
            out("\n(Dry run — re-run with --apply to perform the merge.)")
    finally:
        db.close()

    with open("dedupe_result.log", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
