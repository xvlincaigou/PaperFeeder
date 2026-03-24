#!/usr/bin/env python3
"""Repository entrypoint for the PaperFeeder digest runner."""

from __future__ import annotations

from paperfeeder.pipeline.runner import (
    _extract_report_urls,
    _normalize_url_for_match,
    build_parser,
    main,
    run_pipeline,
    update_semantic_memory_from_report,
)

__all__ = [
    "_extract_report_urls",
    "_normalize_url_for_match",
    "build_parser",
    "main",
    "run_pipeline",
    "update_semantic_memory_from_report",
]


if __name__ == "__main__":
    main()

