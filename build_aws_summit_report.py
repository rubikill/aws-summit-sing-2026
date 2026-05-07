#!/usr/bin/env python3
"""Build a single-page interactive AWS Summit Singapore 2026 report from crawler output."""

from __future__ import annotations

import html as html_lib
import json
import re
from collections import Counter
from pathlib import Path

OUTPUT_ROOT = Path(__file__).resolve().parent / "aws-summit-crawler" / "output"
REPO_ROOT = Path(__file__).resolve().parent
OUT_HTML = REPO_ROOT / "index.html"
INFOGRAPHIC_FILE = REPO_ROOT / "Infographic.jpg"
INFOGRAPHIC_SRC = "Infographic.jpg"

STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "if", "in", "on", "at", "to", "for", "of", "with",
    "by", "from", "as", "is", "was", "are", "were", "be", "been", "being", "it", "this", "that",
    "these", "those", "we", "you", "your", "our", "they", "them", "their", "there", "here", "also",
    "just", "so", "than", "then", "into", "about", "over", "such", "all", "any", "both", "each",
    "few", "more", "most", "other", "some", "such", "no", "not", "only", "own", "same", "too",
    "very", "can", "could", "should", "would", "may", "might", "will", "shall", "do", "does", "did",
    "done", "have", "has", "had", "having", "i", "me", "my", "he", "she", "his", "her", "its",
    "who", "whom", "what", "which", "when", "where", "why", "how", "yeah", "uh", "um", "okay",
}


def strip_bracket_suffix(title: str) -> str:
    """Folder names look like 'Title [sin-xxxx]'; keep display title from JSON only."""
    return title


def parse_vtt_paths(captions_dir: Path) -> str:
    if not captions_dir.is_dir():
        return ""
    parts: list[str] = []
    for vtt in sorted(captions_dir.glob("*.vtt")):
        parts.append(parse_vtt_file(vtt))
    text = " ".join(p for p in parts if p)
    return re.sub(r"\s+", " ", text).strip()


def parse_vtt_file(path: Path) -> str:
    lines_out: list[str] = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        s = raw.strip()
        if not s or s.startswith("WEBVTT") or s.startswith("NOTE") or s.startswith("X-TIMESTAMP"):
            continue
        if "-->" in s:
            continue
        if re.fullmatch(r"\d+", s):
            continue
        # Some engines emit standalone timing lines without arrow (rare)
        if re.match(r"^\d{2}:\d{2}:\d{2}\.\d{3}", s):
            continue
        lines_out.append(s)
    return " ".join(lines_out)


def tokenize_sentence(sentence: str) -> list[str]:
    return [
        w for w in re.findall(r"[A-Za-z][A-Za-z0-9']*", sentence.lower())
        if len(w) > 2 and w not in STOPWORDS
    ]


def split_sentences(text: str) -> list[str]:
    if not text:
        return []
    chunks = re.split(r"(?<=[.!?])\s+", text)
    return [c.strip() for c in chunks if len(c.strip()) > 35]


def extractive_summary(transcript: str, num_sentences: int = 8) -> tuple[str, list[str]]:
    """Return two-paragraph text and high-signal transcript sentences (for takeaways)."""
    sentences = split_sentences(transcript)
    if not sentences:
        t = re.sub(r"\s+", " ", transcript).strip()
        t = t[:1200]
        return (t if t else "No caption transcript available for this session.", [])

    cw: Counter[str] = Counter()
    for s in sentences:
        for w in tokenize_sentence(s):
            cw[w] += 1

    scored: list[tuple[int, int, str]] = []
    for i, s in enumerate(sentences):
        score = sum(cw[w] for w in tokenize_sentence(s))
        scored.append((score, i, s))

    scored.sort(key=lambda x: (-x[0], x[1]))
    top_by_score = scored[: max(num_sentences, 6)]
    top_by_score.sort(key=lambda x: x[1])
    selected = [s for _, _, s in top_by_score[:num_sentences]]

    mid = max(min(4, len(selected)), len(selected) // 2)
    p1 = " ".join(selected[:mid])
    p2 = " ".join(selected[mid:]) if mid < len(selected) else ""
    body = (p1 + "\n\n" + p2).strip()

    takeaway_snips = [s for _, _, s in scored[:12]]
    return body, takeaway_snips


def takeaways(description: str, transcript_snippets: list[str]) -> list[str]:
    bullets: list[str] = []

    desc = (description or "").strip()
    if desc:
        ds = split_sentences(desc)
        # Prefer description sentences for official framing
        for s in ds:
            if len(s) > 40 and len(s) < 500:
                bullets.append(s.rstrip("."))
                if len(bullets) >= 3:
                    break

    if len(bullets) < 3 and desc:
        # fallback: clauses
        for part in re.split(r"[;\n]+", desc):
            p = part.strip()
            if 40 <= len(p) <= 420:
                bullets.append(p.rstrip("."))
                if len(bullets) >= 4:
                    break

    for s in transcript_snippets:
        if len(bullets) >= 6:
            break
        cand = re.sub(r"\s+", " ", s).strip()
        if cand and cand not in bullets and len(cand) > 50:
            bullets.append(cand.rstrip("."))

    # Dedupe loosely
    seen = set()
    out: list[str] = []
    for b in bullets:
        low = b.lower()[:140]
        if low in seen:
            continue
        seen.add(low)
        out.append(b)
    return out[:5]


def slugify(title: str) -> str:
    s = re.sub(r"[^\w\s-]", "", title, flags=re.ASCII)
    s = re.sub(r"[-\s]+", "-", s).strip("-")
    return s.lower()[:80] or "session"


def load_sessions(root: Path) -> list[dict]:
    sessions: list[dict] = []
    for meta_path in sorted(root.glob("**/metadata.json")):
        payload = json.loads(meta_path.read_text(encoding="utf-8"))
        session_dir = meta_path.parent
        captions_dir = session_dir / "captions"
        transcript = parse_vtt_paths(captions_dir)
        title = strip_bracket_suffix(payload.get("eventtitle") or session_dir.name)
        description = payload.get("description") or ""

        summary_text, snippets = extractive_summary(transcript, num_sentences=8)
        kta = takeaways(description, snippets)

        speakers_raw = payload.get("speakers") or []
        speaker_lines = []
        speaker_names: list[str] = []
        for sp in speakers_raw:
            name = (sp.get("name") or "").strip()
            tit = (sp.get("title") or "").strip()
            speaker_names.append(name)
            if name and tit:
                speaker_lines.append(f"{name} — {tit}")
            elif name:
                speaker_lines.append(name)

        category = (payload.get("customCategory") or "AWS Summit Singapore").strip()
        sess_id = payload.get("sessionEventId") or ""
        video_url = (payload.get("video_url") or payload.get("vod_m3u8_url") or "").strip()
        evt_date = payload.get("eventdate") or ""
        evt_time = payload.get("eventtime") or ""

        search_blob = " ".join(
            [title, summary_text, description, category, " ".join(speaker_names)]
        ).lower()

        sessions.append(
            {
                "id": sess_id or slugify(title),
                "title": title,
                "speakers_html": speaker_lines,
                "speaker_names": speaker_names,
                "category": category,
                "description": description,
                "key_takeaways": kta,
                "summary_text": summary_text,
                "search_blob": search_blob,
                "eventdate": evt_date,
                "eventtime": evt_time,
                "video_url": video_url,
            }
        )

    sessions.sort(key=lambda x: x["title"].lower())
    return sessions


CSS = """
:root {
  color-scheme: light dark;
  --bg: #0f1419;
  --surface: #1a2230;
  --border: rgba(255,255,255,0.08);
  --text: #e8eef8;
  --muted: #9fb1c9;
  --accent: #ff9900;
  --accent-soft: rgba(255,153,0,0.14);
}
* { box-sizing: border-box; }
body {
  margin: 0;
  font-family: "Segoe UI", system-ui, -apple-system, Roboto, Ubuntu, Cantarell, sans-serif;
  background: radial-gradient(1200px 800px at 10% -10%, #1f2d44 0%, var(--bg) 55%);
  color: var(--text);
  line-height: 1.55;
}
a { color: #ffb84d; }
header.app {
  position: sticky;
  top: 0;
  z-index: 20;
  backdrop-filter: blur(10px);
  background: rgba(15,20,25,0.85);
  border-bottom: 1px solid var(--border);
}
.inner {
  max-width: 1200px;
  margin: 0 auto;
  padding: 1.25rem 1.25rem 1rem;
}
h1 {
  margin: 0 0 0.35rem;
  font-size: 1.6rem;
  letter-spacing: 0.02em;
}
.sub {
  margin: 0;
  color: var(--muted);
  font-size: 0.95rem;
}
.filters {
  margin-top: 1rem;
  display: grid;
  gap: 0.75rem;
  grid-template-columns: 1fr;
}
@media (min-width: 720px) {
  .filters { grid-template-columns: 1.35fr repeat(3, auto); align-items: end; }
}
label {
  font-size: 0.82rem;
  color: var(--muted);
}
input[type="search"], select, button {
  width: 100%;
  padding: 0.55rem 0.65rem;
  border-radius: 10px;
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--text);
}
button {
  cursor: pointer;
  font-weight: 600;
}
button.secondary { background: #243044; border-color: #31405a; }
button:hover { filter: brightness(1.08); }
main.inner { padding-bottom: 3rem; }
.report-infographic {
  margin: 0 0 1.25rem;
}
.report-infographic figcaption {
  margin: 0.5rem 0 0;
  font-size: 0.85rem;
  color: var(--muted);
}
.report-infographic img {
  display: block;
  width: 100%;
  height: auto;
  border-radius: 12px;
  border: 1px solid var(--border);
  background: var(--surface);
}
.stats {
  margin: 0.85rem 0 0.25rem;
  color: var(--muted);
  font-size: 0.92rem;
}
.card-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 1rem;
  margin-top: 1rem;
}
.session-card {
  background: linear-gradient(180deg, rgba(26,34,48,0.95), rgba(20,26,36,0.98));
  border: 1px solid var(--border);
  border-radius: 14px;
  overflow: clip;
}
.session-card.hidden { display: none; }
.card-top {
  padding: 1rem 1rem 0;
}
.badge {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.2rem 0.55rem;
  border-radius: 999px;
  font-size: 0.75rem;
  color: var(--text);
  background: var(--accent-soft);
  border: 1px solid rgba(255,153,0,0.35);
}
h2.card-title {
  margin: 0.55rem 0 0;
  font-size: 1.12rem;
  line-height: 1.35;
}
.meta-row {
  margin-top: 0.6rem;
  color: var(--muted);
  font-size: 0.88rem;
}
.speaker-list {
  margin: 0.5rem 0 0;
  padding-left: 1rem;
}
.speaker-list li { margin-bottom: 0.25rem; }
.card-video {
  margin: 0.85rem -1rem 0;
  padding: 0 1rem;
}
@media (max-width: 899px) {
  .card-video { margin-left: 0; margin-right: 0; padding: 0; }
}
.card-video video {
  display: block;
  width: 100%;
  max-height: min(40vh, 280px);
  border-radius: 10px;
  background: #000;
  border: 1px solid var(--border);
}
.card-video .video-fallback {
  margin: 0.35rem 0 0;
  font-size: 0.82rem;
  color: var(--muted);
}
details.more {
  border-top: 1px solid var(--border);
  margin-top: 0.85rem;
  background: rgba(0,0,0,0.12);
}
details.more summary {
  cursor: pointer;
  list-style: none;
  padding: 0.75rem 1rem;
  font-weight: 650;
  color: #ffd9a8;
}
details.more summary::-webkit-details-marker { display: none; }
details.more[open] summary { border-bottom: 1px solid var(--border); }
.section {
  padding: 0 1rem 1rem;
}
.section h3 {
  margin: 0.95rem 0 0.4rem;
  font-size: 0.92rem;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 0.08em;
}
.section ul { margin: 0; padding-left: 1rem; }
.section li { margin-bottom: 0.35rem; }
.summary p {
  margin: 0.55rem 0 0;
  color: var(--text);
}
footer {
  max-width: 1200px;
  margin: 0 auto;
  padding: 0 1.25rem 2rem;
  color: var(--muted);
  font-size: 0.85rem;
}
"""


JS = """
(function () {
  const cards = Array.from(document.querySelectorAll(".session-card"));
  const search = document.getElementById("search");
  const categoryFilter = document.getElementById("categoryFilter");
  const speakerFilter = document.getElementById("speakerFilter");
  const resetBtn = document.getElementById("resetFilters");
  const stats = document.getElementById("stats");

  function apply() {
    const q = search.value.trim().toLowerCase();
    const cat = categoryFilter.value;
    const spk = speakerFilter.value;
    let shown = 0;
    cards.forEach((card) => {
      const blob = card.getAttribute("data-search") || "";
      const cats = card.getAttribute("data-category") || "";
      const speaks = card.getAttribute("data-speakers") || "";
      const catOk = !cat || cats === cat;
      const speakerOk = !spk || speaks.includes("|" + spk + "|");
      const matchOk =
        !q ||
        blob.includes(q) ||
        card.innerText.toLowerCase().includes(q);
      const ok = catOk && speakerOk && matchOk;
      card.classList.toggle("hidden", !ok);
      if (ok) shown += 1;
    });
    stats.textContent = `${shown} of ${cards.length} sessions shown`;
  }

  categoryFilter.addEventListener("change", apply);
  speakerFilter.addEventListener("change", apply);
  search.addEventListener("input", apply);

  resetBtn.addEventListener("click", () => {
    search.value = "";
    categoryFilter.value = "";
    speakerFilter.value = "";
    apply();
  });

  apply();

  function attachHlsPlayers() {
    document.querySelectorAll("video.hls-player").forEach((video) => {
      const src = video.getAttribute("data-video-url");
      if (!src) return;
      if (window.Hls && window.Hls.isSupported()) {
        const hls = new window.Hls({ enableWorker: true });
        hls.loadSource(src);
        hls.attachMedia(video);
      } else if (video.canPlayType("application/vnd.apple.mpegurl")) {
        video.src = src;
      } else {
        var fb = video.parentElement && video.parentElement.querySelector(".video-fallback");
        if (fb) fb.hidden = false;
      }
    });
  }
  if (window.Hls) {
    attachHlsPlayers();
  } else {
    var s = document.createElement("script");
    s.src = "https://cdn.jsdelivr.net/npm/hls.js@1.5.7/dist/hls.min.js";
    s.async = true;
    s.onload = attachHlsPlayers;
    document.head.appendChild(s);
  }
})();
"""


def escape_attr(s: str) -> str:
    return html_lib.escape(s, quote=True)


def infographic_block() -> str:
    """Embeds Infographic.jpg when present next to index.html / build script."""
    if not INFOGRAPHIC_FILE.is_file():
        return ""
    return f"""
    <figure class="report-infographic">
      <img src="{escape_attr(INFOGRAPHIC_SRC)}" alt="AWS Summit Singapore 2026 infographic" loading="lazy" decoding="async" />
      <figcaption>Event infographic</figcaption>
    </figure>
""".strip()


def build_html_doc(sessions: list[dict]) -> str:
    categories = sorted({s["category"] for s in sessions})
    speakers = sorted(
        {nm for s in sessions for nm in s["speaker_names"] if nm},
        key=str.lower,
    )

    filters_html = f"""
<div class="filters">
  <div>
    <label for="search">Search</label>
    <input id="search" type="search" placeholder="Titles, summaries, speakers…" autocomplete="off" />
  </div>
  <div>
    <label for="categoryFilter">Category</label>
    <select id="categoryFilter">
      <option value="">All categories</option>
      {"".join(f'<option value="{escape_attr(c)}">{html_lib.escape(c)}</option>' for c in categories)}
    </select>
  </div>
  <div>
    <label for="speakerFilter">Speaker</label>
    <select id="speakerFilter">
      <option value="">All speakers</option>
      {"".join(f'<option value="{escape_attr(s)}">{html_lib.escape(s)}</option>' for s in speakers)}
    </select>
  </div>
  <div>
    <label>&nbsp;</label>
    <button type="button" class="secondary" id="resetFilters">Reset filters</button>
  </div>
</div>
"""

    blocks: list[str] = []
    for s in sessions:
        sp_names_join = "|" + "|".join(s["speaker_names"]) + "|" if s["speaker_names"] else "|"
        speaker_li = "".join(f"<li>{html_lib.escape(x)}</li>" for x in s["speakers_html"])
        if not speaker_li:
            speaker_li = "<li>(See session VoD metadata)</li>"

        take_li = "".join(f"<li>{html_lib.escape(t)}</li>" for t in s["key_takeaways"])

        paras = []
        for para in (s["summary_text"] or "").split("\n\n"):
            para = para.strip()
            if para:
                paras.append(f"<p>{html_lib.escape(para)}</p>")
        if not paras:
            paras.append("<p>No transcript summary available.</p>")

        video_block = ""
        if s["video_url"]:
            escaped = escape_attr(s["video_url"])
            title_esc = escape_attr(s["title"])
            video_block = f"""
    <div class="card-video">
      <video class="hls-player" controls playsinline preload="metadata" data-video-url="{escaped}" aria-label="Recording: {title_esc}">
        <source src="{escaped}" type="application/x-mpegURL" />
      </video>
      <p class="video-fallback" hidden>HLS playback may require Safari or a browser with MSE. <a href="{escaped}" rel="noopener noreferrer" target="_blank">Open stream</a></p>
    </div>""".strip()

        vod_link = ""
        if s["video_url"]:
            vod_link = f'<p style="margin:0.55rem 0 0;"><a href="{escape_attr(s["video_url"])}" rel="noopener noreferrer" target="_blank">Open stream in new tab</a></p>'

        when_parts = [html_lib.escape(s["eventdate"]), html_lib.escape(s["eventtime"])]
        when = " · ".join(p for p in when_parts if p)

        blocks.append(
            f"""
<article class="session-card" data-category="{escape_attr(s['category'])}" data-speakers="{escape_attr(sp_names_join)}" data-search="{escape_attr(s['search_blob'])}">
  <div class="card-top">
    <span class="badge">{html_lib.escape(s['category'])}</span>
    <h2 class="card-title">{html_lib.escape(s['title'])}</h2>
    <div class="meta-row">{when}</div>
    <div class="meta-row"><strong>Speaker(s)</strong></div>
    <ul class="speaker-list">{speaker_li}</ul>
    {video_block}
  </div>
  <details class="more">
    <summary>Key takeaways &amp; caption-based summary</summary>
    <div class="section">
      <h3>Key takeaways</h3>
      <ul>{take_li}</ul>
      <h3>Summary (from captions)</h3>
      <div class="summary">{''.join(paras)}</div>
      {vod_link}
    </div>
  </details>
</article>
""".strip()
        )

    sources = html_lib.escape("aws-summit-crawler/output")

    doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>AWS Summit Singapore 2026 — Session digest</title>
  <meta name="description" content="Interactive recap of AWS Summit Singapore 2026 sessions with search, filters, and caption-based summaries." />
  <style>
{CSS}
  </style>
</head>
<body>
  <header class="app">
    <div class="inner">
      <h1>AWS Summit Singapore 2026</h1>
      <p class="sub">Interactive report from <code>{sources}</code> metadata &amp; WebVTT captions ({len(sessions)} sessions).</p>
      {filters_html}
    </div>
  </header>
  <main class="inner">
    {infographic_block()}
    <p id="stats" class="stats"></p>
    <div class="card-grid">
{"\n".join(blocks)}
    </div>
  </main>
  <footer>
    <p>GitHub Pages: commit <code>index.html</code> and <code>Infographic.jpg</code> at the site root, or run <code>python build_aws_summit_report.py</code> after updating crawler output.</p>
  </footer>
  <script>
{JS}
  </script>
</body>
</html>
"""

    return doc


def main() -> None:
    if not OUTPUT_ROOT.is_dir():
        raise SystemExit(f"Missing output folder: {OUTPUT_ROOT}")

    sessions = load_sessions(OUTPUT_ROOT)

    html_doc = build_html_doc(sessions)
    OUT_HTML.write_text(html_doc, encoding="utf-8")
    print(f"Wrote {OUT_HTML} ({len(sessions)} sessions)")


if __name__ == "__main__":
    main()
