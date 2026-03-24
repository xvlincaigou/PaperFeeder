"""
Lightweight debug path: one (or few) papers from JSON, no fetch / coarse LLM / Tavily / fine LLM.

Use for testing feedback links, D1 publish, email HTML, Worker viewer without full crawl.
"""

from __future__ import annotations

import html
import json
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional

from paperfeeder.models import Paper

DEFAULT_DEBUG_SAMPLE_PATH = "tests/debug_sample.json"
FALLBACK_DEBUG_SAMPLE_PATH = "tests/debug_sample.example.json"


def resolve_debug_sample_path(path: Optional[str] = None) -> Path:
    """Prefer explicit path, then tests/debug_sample.json, then bundled example."""
    if path:
        p = Path(path)
        if not p.is_file():
            raise FileNotFoundError(f"Debug sample path not found: {p}")
        return p.resolve()
    primary = Path(DEFAULT_DEBUG_SAMPLE_PATH)
    if primary.is_file():
        return primary.resolve()
    alt = Path(FALLBACK_DEBUG_SAMPLE_PATH)
    if alt.is_file():
        print(f"   Debug sample: {primary} not found, using {alt} (copy to {primary} to customize)")
        return alt.resolve()
    raise FileNotFoundError(
        f"Debug sample file not found. Copy {FALLBACK_DEBUG_SAMPLE_PATH} to "
        f"{DEFAULT_DEBUG_SAMPLE_PATH} or pass --debug-sample-path."
    )


def load_debug_sample_papers(path: Optional[str] = None) -> List[Paper]:
    sample_path = resolve_debug_sample_path(path)
    raw = json.loads(sample_path.read_text(encoding="utf-8"))
    items: List[Any]
    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, dict):
        if "papers" in raw:
            items = raw["papers"]
        elif "title" in raw and "url" in raw:
            items = [raw]
        else:
            raise ValueError("debug sample JSON must be a list, or {papers: [...]}, or a single paper object")
    else:
        raise ValueError("debug sample JSON must be a list or object")

    papers = []
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"debug sample item {i} must be an object")
        papers.append(Paper.from_dict(item))
    if not papers:
        raise ValueError("debug sample contains no papers")
    print(f"   Debug sample: loaded {len(papers)} paper(s) from {sample_path}")
    return papers


# Keep in sync with summarizer light theme (no external scripts = faster load).
_MINIMAL_DIGEST_STYLES = """
        <style>
            :root { color-scheme: light; }
            * { box-sizing: border-box; margin: 0; padding: 0; }
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif;
                line-height: 1.55;
                color: #0f172a;
                background: linear-gradient(180deg, #e8f2fc 0%, #f1f5f9 45%, #e2e8f0 100%);
                padding: max(0px, env(safe-area-inset-top)) max(0px, env(safe-area-inset-right)) max(0px, env(safe-area-inset-bottom)) max(0px, env(safe-area-inset-left));
                font-size: clamp(15px, 2.8vw, 16px);
            }
            .container {
                max-width: min(52rem, 100%);
                margin: 0 auto;
                background: #fff;
                border-radius: 14px;
                box-shadow: 0 4px 24px rgba(15, 23, 42, 0.08);
                border: 1px solid rgba(148, 163, 184, 0.35);
                overflow: hidden;
            }
            .header {
                background: linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 50%, #dbeafe 100%);
                color: #0c4a6e;
                padding: 6px 8px;
                text-align: center;
                border-bottom: 1px solid rgba(125, 211, 252, 0.5);
            }
            .header h1 { font-size: 1.35rem; font-weight: 700; color: #0369a1; }
            .header .meta { margin-top: 6px; font-size: 0.9rem; color: #0e7490; }
            .content { padding: 6px 8px 8px; color: #1e293b; }
            .content h2 { color: #0f172a; margin: 1.1em 0 0.4em; font-size: 1.1rem; }
            .content p { margin: 0.5em 0; }
            .content a { color: #2563eb; }
            .badge {
                display: inline-block;
                font-size: 0.75rem;
                padding: 2px 8px;
                border-radius: 999px;
                background: #fef3c7;
                color: #92400e;
                margin-bottom: 8px;
            }
            .footer {
                text-align: center;
                padding: 6px 8px;
                font-size: 0.72rem;
                color: #64748b;
                border-top: 1px solid #e2e8f0;
                background: #f8fafc;
            }
        </style>
"""


def build_minimal_digest_html(papers: List[Paper], *, label: str = "DEBUG SAMPLE") -> str:
    """Full HTML document with one section per paper and a visible link for manifest matching."""
    today = datetime.now().strftime("%Y-%m-%d")
    parts: List[str] = []
    for i, p in enumerate(papers, 1):
        title_esc = html.escape(p.title)
        abs_esc = html.escape((p.abstract or "")[:1200] or "(no abstract)")
        url_esc = html.escape(p.url, quote=True)
        parts.append(f'<h2>{i}. {title_esc}</h2>')
        parts.append(f'<p><span class="badge">{html.escape(label)}</span></p>')
        parts.append(f'<p><a href="{p.url}">{title_esc}</a></p>')
        parts.append(f"<p>{abs_esc}</p>")
        if p.semantic_paper_id:
            parts.append(f"<p><small>semantic_paper_id: {html.escape(str(p.semantic_paper_id))}</small></p>")

    inner = "\n".join(parts)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Paper Digest (debug) - {today}</title>
{_MINIMAL_DIGEST_STYLES}
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Paper Digest</h1>
            <div class="meta">{today} · {len(papers)} paper(s) · minimal HTML (no LLM)</div>
        </div>
        <div class="content">
            {inner}
        </div>
        <div class="footer">PaperFeeder debug sample — feedback links still work if manifest + Worker are configured.</div>
    </div>
</body>
</html>"""

