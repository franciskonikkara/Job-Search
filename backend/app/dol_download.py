"""Download the DOL LCA disclosure file.

The DOL CDN blocks non-browser clients and rotates filenames each fiscal
quarter, so we:
  - send a browser-like User-Agent,
  - stream the (large) file to disk in chunks,
  - retry a few times with backoff,
  - and fail with a clear, actionable message so the user can fall back to
    dropping the file in manually.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass

import requests

from .config import get_settings

settings = get_settings()

_CHUNK = 1024 * 256  # 256 KB


class DolDownloadError(RuntimeError):
    """Raised when the automatic download fails (blocked, 404, network)."""


@dataclass
class DownloadResult:
    path: str
    bytes_written: int
    source_url: str


def _filename_from_url(url: str) -> str:
    name = url.split("?")[0].rstrip("/").split("/")[-1]
    return name or "dol_lca_disclosure.xlsx"


def download_dol_file(
    url: str | None = None,
    *,
    dest_dir: str | None = None,
    retries: int = 3,
    timeout: int = 60,
) -> DownloadResult:
    """Download the DOL LCA file to disk. Returns the local path.

    Raises DolDownloadError with a friendly message on failure.
    """
    url = url or settings.dol_source_url
    dest_dir = dest_dir or settings.dol_download_dir
    os.makedirs(dest_dir, exist_ok=True)
    dest_path = os.path.join(dest_dir, _filename_from_url(url))

    headers = {
        "User-Agent": settings.dol_user_agent,
        "Accept": (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,"
            "application/octet-stream,*/*"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }

    last_err: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            with requests.get(
                url, headers=headers, stream=True, timeout=timeout
            ) as resp:
                if resp.status_code == 403:
                    raise DolDownloadError(
                        "DOL blocked the automated download (HTTP 403). This is "
                        "common — the DOL CDN filters bots. Download the LCA "
                        "disclosure file manually from "
                        "https://www.dol.gov/agencies/eta/foreign-labor/performance "
                        "and import it with the local-file option."
                    )
                if resp.status_code == 404:
                    raise DolDownloadError(
                        f"File not found at {url} (HTTP 404). DOL rotates the "
                        "filename each fiscal quarter — update the source URL to "
                        "the current LCA_Disclosure_Data_FYxxxx_Qx.xlsx."
                    )
                resp.raise_for_status()

                written = 0
                with open(dest_path, "wb") as fh:
                    for chunk in resp.iter_content(chunk_size=_CHUNK):
                        if chunk:
                            fh.write(chunk)
                            written += len(chunk)

            if written == 0:
                raise DolDownloadError("Downloaded 0 bytes; the file was empty.")
            return DownloadResult(dest_path, written, url)

        except DolDownloadError:
            raise  # already friendly; don't retry a definitive block/404
        except requests.RequestException as exc:
            last_err = exc
            if attempt < retries:
                time.sleep(2 * attempt)  # linear backoff
                continue

    raise DolDownloadError(
        "Could not download the DOL file after several attempts "
        f"({last_err}). The DOL CDN may be blocking automated access. "
        "Please download it manually and use the local-file import option."
    )
