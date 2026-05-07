# AWS Summit Singapore 2026 — Session digest

Interactive recap of summit sessions: search, filters, embedded VoD (HLS), caption-based summaries, and the event infographic.

## Live site (GitHub Pages)

[https://rubikill.github.io/aws-summit-sing-2026/](https://rubikill.github.io/aws-summit-sing-2026/)

## Regenerate the report

Requires session data under `aws-summit-crawler/output/` (metadata + captions from the crawler).

```bash
python3 build_aws_summit_report.py
```

This writes `index.html` in the repository root. Deployment expects **`index.html`** and **`Infographic.jpg`** in the Pages root (typically the repo root branch).

## Contents

- **`index.html`** — Single-file report (inline CSS/JS, loads [hls.js](https://github.com/video-dev/hls.js/) from CDN for HLS playback in common browsers).
- **`Infographic.jpg`** — Shown at the top of the report when present next to `index.html`.
- **`build_aws_summit_report.py`** — Builder script.
- **`aws-summit-crawler/`** — Crawler for metadata and WebVTT captions; see [aws-summit-crawler/README.md](aws-summit-crawler/README.md).
