__all__ = [
    "KeywordFilter",
    "LLMFilter",
    "MockPaperResearcher",
    "PaperResearcher",
    "PaperSummarizer",
    "_extract_report_urls",
    "_normalize_url_for_match",
    "build_parser",
    "main",
    "run_pipeline",
    "update_semantic_memory_from_report",
]


def __getattr__(name):
    if name in {
        "_extract_report_urls",
        "_normalize_url_for_match",
        "build_parser",
        "main",
        "run_pipeline",
        "update_semantic_memory_from_report",
    }:
        from .runner import (
            _extract_report_urls,
            _normalize_url_for_match,
            build_parser,
            main,
            run_pipeline,
            update_semantic_memory_from_report,
        )

        return {
            "_extract_report_urls": _extract_report_urls,
            "_normalize_url_for_match": _normalize_url_for_match,
            "build_parser": build_parser,
            "main": main,
            "run_pipeline": run_pipeline,
            "update_semantic_memory_from_report": update_semantic_memory_from_report,
        }[name]
    if name in {"KeywordFilter", "LLMFilter"}:
        from .filters import KeywordFilter, LLMFilter

        return {"KeywordFilter": KeywordFilter, "LLMFilter": LLMFilter}[name]
    if name in {"MockPaperResearcher", "PaperResearcher"}:
        from .researcher import MockPaperResearcher, PaperResearcher

        return {"MockPaperResearcher": MockPaperResearcher, "PaperResearcher": PaperResearcher}[name]
    if name == "PaperSummarizer":
        from .summarizer import PaperSummarizer

        return PaperSummarizer
    raise AttributeError(name)
