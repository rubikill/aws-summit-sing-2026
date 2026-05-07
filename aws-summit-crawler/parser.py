"""Fetch event lists, session JSON, and discover caption URLs from HLS manifests."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urljoin

import m3u8
import requests

from config import EVENTS_URL, SESSION_FRONTEND_TEMPLATE, SINGAPORE_SESSION_PREFIX
from utils import get_json, get_text

log = logging.getLogger(__name__)


def fetch_events_list(session: requests.Session) -> list[dict[str, Any]]:
    data = get_json(session, EVENTS_URL)
    if not isinstance(data, dict):
        raise ValueError("events.json root must be an object")
    out: list[dict[str, Any]] = []
    for key in ("upcoming", "onDemand"):
        chunk = data.get(key)
        if isinstance(chunk, list):
            for item in chunk:
                if isinstance(item, dict):
                    out.append(item)
    return out


def filter_singapore_sessions(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for e in events:
        sid = str(e.get("sessionEventId") or e.get("crvmEventId") or "")
        if sid.startswith(SINGAPORE_SESSION_PREFIX):
            result.append(e)
    return result


def fetch_session_details(session: requests.Session, session_id: str) -> dict[str, Any]:
    url = SESSION_FRONTEND_TEMPLATE.format(session_id=session_id)
    data = get_json(session, url)
    if not isinstance(data, dict):
        raise ValueError(f"frontend.json for {session_id} must be an object")
    return data


def extract_vod_url(session_data: dict[str, Any]) -> str | None:
    """Return HLS master URL for on-demand video, if present."""
    videos = session_data.get("videos")
    if not isinstance(videos, list):
        return None
    default_id = session_data.get("defaultVideo") or "VOD"

    by_id: dict[str, dict[str, Any]] = {}
    for v in videos:
        if isinstance(v, dict) and "id" in v:
            by_id[str(v["id"])] = v

    def pick_vid(vid: str) -> dict[str, Any] | None:
        v = by_id.get(vid)
        return v if isinstance(v, dict) else None

    # Prefer explicit defaultVideo, then VOD, then first non-empty videoUrl
    chosen = pick_vid(str(default_id)) or pick_vid("VOD")
    if chosen is None:
        for v in videos:
            if not isinstance(v, dict):
                continue
            url = (v.get("videoUrl") or "").strip()
            if url and v.get("id") not in ("pre-show", "post-show", "contingency", "brb", "secondary", "ASL"):
                chosen = v
                break

    if chosen is None:
        return None
    url = str(chosen.get("videoUrl") or "").strip()
    return url or None


def _extract_subtitle_playlist_uri(master_text: str, master_url: str) -> str | None:
    playlist = m3u8.loads(master_text, uri=master_url)

    for media in playlist.media:
        if (
            media.type == "SUBTITLES"
            and getattr(media, "uri", None)
            and (media.uri or "").strip()
        ):
            return urljoin(master_url, media.uri)

    # Fallback: parse raw lines for TYPE=SUBTITLES
    for line in master_text.splitlines():
        line = line.strip()
        if line.startswith("#EXT-X-MEDIA:") and "TYPE=SUBTITLES" in line:
            if "URI=" in line:
                part = line.split("URI=", 1)[1].strip().strip('"')
                if part:
                    return urljoin(master_url, part)
    return None


def discover_caption_vtt_urls(
    session_http: requests.Session, master_m3u8_url: str
) -> list[str]:
    """
    Parse the HLS master playlist, find the WebVTT media playlist,
    and return absolute URLs for each .vtt segment.
    """
    master_text = get_text(session_http, master_m3u8_url)
    sub_playlist_uri = _extract_subtitle_playlist_uri(master_text, master_m3u8_url)
    if not sub_playlist_uri:
        log.info("No SUBTITLES media found in master playlist: %s", master_m3u8_url)
        return []

    cap_text = get_text(session_http, sub_playlist_uri)
    cap_list = m3u8.loads(cap_text, uri=sub_playlist_uri)
    urls: list[str] = []
    for seg in cap_list.segments:
        if seg.uri and seg.uri.strip().lower().endswith(".vtt"):
            urls.append(urljoin(sub_playlist_uri, seg.uri))
    return urls


def build_session_summary(
    event_row: dict[str, Any], session_data: dict[str, Any]
) -> dict[str, Any]:
    """Flatten useful fields for metadata.json."""
    home = session_data.get("homePage") or {}
    panel = session_data.get("eventPanel") or {}
    speakers_section = panel.get("speakersSection") or {}
    speakers = speakers_section.get("speakers") or []

    meta_tags = session_data.get("metaTags") or {}

    return {
        "sessionEventId": event_row.get("sessionEventId") or event_row.get("crvmEventId"),
        "eventtitle": event_row.get("eventtitle") or meta_tags.get("title"),
        "description": event_row.get("description") or meta_tags.get("description"),
        "customCategory": event_row.get("customCategory") or meta_tags.get("customCategory"),
        "eventdate": event_row.get("eventdate"),
        "eventtime": event_row.get("eventtime"),
        "eventStart": event_row.get("eventStart"),
        "eventEnd": event_row.get("eventEnd"),
        "filterTags": event_row.get("filterTags") or meta_tags.get("filterTags"),
        "image": event_row.get("image"),
        "speakers": speakers,
    }
