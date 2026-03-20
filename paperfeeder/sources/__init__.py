from .base import BaseSource

__all__ = [
    "BaseSource",
    "BlogSource",
    "JinaReaderSource",
    "ArxivSource",
    "HuggingFaceSource",
    "ManualSource",
    "SemanticScholarSource",
    "OpenReviewSource",
    "fetch_blog_posts",
]


def __getattr__(name):
    if name == "fetch_blog_posts":
        from .blog_sources import fetch_blog_posts

        return fetch_blog_posts
    if name in {"BlogSource", "JinaReaderSource"}:
        from .blog_sources import BlogSource, JinaReaderSource

        return {"BlogSource": BlogSource, "JinaReaderSource": JinaReaderSource}[name]
    if name in {"ArxivSource", "HuggingFaceSource", "ManualSource", "SemanticScholarSource", "OpenReviewSource"}:
        from .paper_sources import (
            ArxivSource,
            HuggingFaceSource,
            ManualSource,
            OpenReviewSource,
            SemanticScholarSource,
        )

        return {
            "ArxivSource": ArxivSource,
            "HuggingFaceSource": HuggingFaceSource,
            "ManualSource": ManualSource,
            "SemanticScholarSource": SemanticScholarSource,
            "OpenReviewSource": OpenReviewSource,
        }[name]
    raise AttributeError(name)
