"""Download HLS as MP4 via ffmpeg and fetch caption files."""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

import requests

from config import REQUEST_TIMEOUT_SEC
from utils import sanitize_folder_name, with_retries

log = logging.getLogger(__name__)


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def download_hls_as_mp4(m3u8_url: str, output_path: Path, overwrite: bool = False) -> None:
    if not ffmpeg_available():
        raise RuntimeError(
            "ffmpeg is not installed or not on PATH. Install ffmpeg to download video."
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists() and not overwrite:
        log.info("Video already exists, skipping: %s", output_path)
        return

    # ffmpeg infers muxer from extension; avoid "*.mp4.part" (invalid)
    tmp_path = output_path.with_name(f"{output_path.stem}.partial{output_path.suffix}")
    if tmp_path.exists():
        tmp_path.unlink()

    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        m3u8_url,
        "-c",
        "copy",
        "-bsf:a",
        "aac_adtstoasc",
        str(tmp_path),
    ]
    log.info("Running ffmpeg for %s -> %s", m3u8_url, output_path)

    def run_ffmpeg() -> None:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip()
            raise RuntimeError(f"ffmpeg failed ({proc.returncode}): {err}")

    with_retries(run_ffmpeg, label="ffmpeg")
    tmp_path.replace(output_path)


def download_file(
    session: requests.Session, url: str, dest: Path, overwrite: bool = False
) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and not overwrite:
        return

    def fetch() -> None:
        r = session.get(url, stream=True, timeout=REQUEST_TIMEOUT_SEC)
        r.raise_for_status()
        tmp = dest.with_suffix(dest.suffix + ".part")
        if tmp.exists():
            tmp.unlink()
        try:
            with open(tmp, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 256):
                    if chunk:
                        f.write(chunk)
            tmp.replace(dest)
        except Exception:
            if tmp.exists():
                tmp.unlink()
            raise

    with_retries(fetch, label=f"download {url}")


def create_session_folder(
    base_path: Path, session_title: str, session_id: str
) -> Path:
    name = sanitize_folder_name(f"{session_title} [{session_id}]")
    folder = base_path / name
    folder.mkdir(parents=True, exist_ok=True)
    captions = folder / "captions"
    captions.mkdir(parents=True, exist_ok=True)
    return folder
