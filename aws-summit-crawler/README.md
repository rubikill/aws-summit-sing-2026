# AWS Summit Singapore 2026 — On-demand crawler

Fetches session **metadata** (including `vod_m3u8_url` for on-demand HLS), and **WebVTT captions** (discovered from the HLS manifest), from the public Corrivium CMS JSON + CloudFront endpoints used by [summitapj.awslivestream.com](https://summitapj.awslivestream.com/).

**By default this does not download MP4 files**; the master playlist URL is stored in each `metadata.json` as `vod_m3u8_url`. Use `--download-mp4` only if you want a local remux via ffmpeg.

## Prerequisites

- **Python 3.9+**
- **ffmpeg** on PATH — only if you pass `--download-mp4`

## Setup

```bash
cd aws-summit-crawler
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Usage

All `sin-*` sessions from `events.json` (Singapore):

```bash
python crawler.py --output ./output
```

One session:

```bash
python crawler.py --output ./output --session sin-dat204
```

Re-fetch metadata and captions:

```bash
python crawler.py --output ./output --force
```

Optional: also save `video.mp4` per session (large):

```bash
python crawler.py --output ./output --download-mp4
```

## Output layout

```
output/
├── <Session Title> [sin-xxxxxx]/
│   ├── metadata.json      # includes vod_m3u8_url, caption_urls, session fields
│   └── captions/
│       └── *.vtt
└── crawler_log.txt
```

With `--download-mp4`, each folder may also contain `video.mp4`.

## Notes

- APIs (`site-assets.corrivium.live`) and media URLs used here are **unauthenticated**; hub sign-in is not required for these assets.
- Respect AWS/CDN terms of use; this tool is for personal use as allowed by the event.
