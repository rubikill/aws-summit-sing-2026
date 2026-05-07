"""Helpers: folder names, HTTP session with retries, logging."""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import Callable, TypeVar

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import MAX_RETRIES, REQUEST_TIMEOUT_SEC, RETRY_BACKOFF_SEC, USER_AGENT

T = TypeVar("T")


def setup_logging(log_file: Path | None = None) -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=handlers,
        force=True,
    )


def sanitize_folder_name(title: str, max_len: int = 120) -> str:
    """Turn a session title into a safe directory name."""
    s = title.strip()
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", s)
    s = re.sub(r"\s+", " ", s)
    s = s.strip(" .")
    if not s:
        s = "untitled_session"
    if len(s) > max_len:
        s = s[:max_len].rstrip()
    return s


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    retry = Retry(
        total=MAX_RETRIES,
        backoff_factor=RETRY_BACKOFF_SEC,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET", "HEAD"),
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def get_json(session: requests.Session, url: str) -> dict | list:
    r = session.get(url, timeout=REQUEST_TIMEOUT_SEC)
    r.raise_for_status()
    return r.json()


def get_text(session: requests.Session, url: str) -> str:
    r = session.get(url, timeout=REQUEST_TIMEOUT_SEC)
    r.raise_for_status()
    return r.text


def with_retries(
    fn: Callable[[], T],
    retries: int = MAX_RETRIES,
    backoff: float = RETRY_BACKOFF_SEC,
    label: str = "operation",
) -> T:
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001
            last_exc = e
            if attempt == retries:
                raise
            wait = backoff * (2**attempt)
            logging.warning(
                "%s failed (%s), retrying in %.1fs (attempt %s/%s)",
                label,
                e,
                wait,
                attempt + 1,
                retries,
            )
            time.sleep(wait)
    assert last_exc is not None
    raise last_exc
