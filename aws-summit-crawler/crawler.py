#!/usr/bin/env python3
"""Crawl AWS Summit Singapore 2026 on-demand hub: metadata, captions, and VOD URL (HLS)."""

from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from config import DEFAULT_DELAY_BETWEEN_SESSIONS_SEC, DEFAULT_OUTPUT_DIR
from downloader import (
    create_session_folder,
    download_file,
    download_hls_as_mp4,
    ffmpeg_available,
)
from parser import (
    build_session_summary,
    discover_caption_vtt_urls,
    extract_vod_url,
    fetch_events_list,
    fetch_session_details,
    filter_singapore_sessions,
)
from utils import make_session, setup_logging

log = logging.getLogger(__name__)


def save_metadata(
    summary: dict[str, Any],
    vod_url: str | None,
    caption_urls: list[str],
    dest: Path,
) -> None:
    payload = {
        **summary,
        "vod_m3u8_url": vod_url,
        "caption_urls": caption_urls,
    }
    path = dest / "metadata.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def session_done(session_folder: Path) -> bool:
    meta = session_folder / "metadata.json"
    return meta.is_file() and meta.stat().st_size > 0


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--output",
        type=Path,
        default=Path(DEFAULT_OUTPUT_DIR),
        help="Output directory for downloads",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="Re-download even if session folder looks complete",
    )
    p.add_argument(
        "--session",
        action="append",
        dest="sessions",
        metavar="SESSION_ID",
        help="Only process specific session id(s), e.g. sin-dat204 (repeatable)",
    )
    p.add_argument(
        "--delay",
        type=float,
        default=DEFAULT_DELAY_BETWEEN_SESSIONS_SEC,
        help="Seconds to sleep between sessions",
    )
    p.add_argument(
        "--download-mp4",
        action="store_true",
        help="Also remux VOD HLS to video.mp4 via ffmpeg (large downloads)",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    out_dir: Path = args.output.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    setup_logging(out_dir / "crawler_log.txt")

    if args.download_mp4 and not ffmpeg_available():
        log.error("--download-mp4 requires ffmpeg on PATH.")
        return 2

    http = make_session()
    events = fetch_events_list(http)
    sessions = filter_singapore_sessions(events)

    if args.sessions:
        want = {s.lower() for s in args.sessions}
        sessions = [
            s
            for s in sessions
            if str(s.get("sessionEventId") or s.get("crvmEventId") or "").lower()
            in want
        ]

    log.info("Singapore sessions to process: %s", len(sessions))

    for i, row in enumerate(sessions, start=1):
        sid = str(row.get("sessionEventId") or row.get("crvmEventId") or "")
        title = str(row.get("eventtitle") or row.get("crvmEventName") or sid)
        log.info("[%s/%s] %s (%s)", i, len(sessions), title, sid)

        try:
            detail = fetch_session_details(http, sid)
        except Exception as e:  # noqa: BLE001
            log.exception("Failed to fetch frontend.json for %s: %s", sid, e)
            continue

        vod = extract_vod_url(detail)
        if not vod:
            log.warning("No VOD URL for %s — saving metadata only", sid)
            summary = build_session_summary(row, detail)
            folder = create_session_folder(out_dir, title, sid)
            save_metadata(summary, None, [], folder)
            if args.delay:
                time.sleep(args.delay)
            continue

        summary = build_session_summary(row, detail)

        caption_urls: list[str] = []
        try:
            caption_urls = discover_caption_vtt_urls(http, vod)
        except Exception as e:  # noqa: BLE001
            log.warning("Could not discover captions for %s: %s", sid, e)

        folder = create_session_folder(out_dir, title, sid)

        if not args.force and session_done(folder):
            log.info("Skipping complete session folder: %s", folder.name)
            if args.delay:
                time.sleep(args.delay)
            continue

        save_metadata(summary, vod, caption_urls, folder)

        caps_dir = folder / "captions"
        for cu in caption_urls:
            fname = urlparse(cu).path.rsplit("/", 1)[-1] or "caption.vtt"
            try:
                download_file(http, cu, caps_dir / fname, overwrite=args.force)
            except Exception as e:  # noqa: BLE001
                log.warning("Caption download failed %s: %s", cu, e)

        if args.download_mp4:
            video_path = folder / "video.mp4"
            try:
                download_hls_as_mp4(vod, video_path, overwrite=args.force)
            except Exception as e:  # noqa: BLE001
                log.exception("Video download failed for %s: %s", sid, e)

        if args.delay:
            time.sleep(args.delay)

    log.info("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
