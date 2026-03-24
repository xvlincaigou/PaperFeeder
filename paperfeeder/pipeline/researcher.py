"""
Paper enrichment module using Tavily API for external research.
"""

from __future__ import annotations

import asyncio
from typing import List, Optional

import aiohttp

from paperfeeder.models import Paper


class PaperResearcher:
    TAVILY_API_URL = "https://api.tavily.com/search"

    def __init__(self, api_key: str, max_concurrent: int = 5, search_depth: str = "basic"):
        self.api_key = api_key
        self.max_concurrent = max_concurrent
        self.search_depth = search_depth

    async def research(self, papers: List[Paper]) -> List[Paper]:
        if not papers:
            return papers

        print(f"\nResearching {len(papers)} papers for external signals...")
        semaphore = asyncio.Semaphore(self.max_concurrent)

        async def research_one(paper: Paper, idx: int) -> Paper:
            async with semaphore:
                print(f"   [{idx+1}/{len(papers)}] Researching: {paper.title[:50]}...")
                paper.research_notes = await self._search_paper(paper)
                return paper

        tasks = [research_one(paper, i) for i, paper in enumerate(papers)]
        enriched_papers = await asyncio.gather(*tasks, return_exceptions=True)

        successful = []
        failed_count = 0
        for result in enriched_papers:
            if isinstance(result, Exception):
                print(f"   Research failed: {result}")
                failed_count += 1
            else:
                successful.append(result)

        if failed_count > 0:
            print(f"   {failed_count} papers failed to research")
        print(f"   Research complete: {len(successful)} papers enriched")
        return successful

    async def _search_paper(self, paper: Paper) -> str:
        query = self._build_search_query(paper)
        try:
            notes = await self._call_tavily(query)
            return notes or "No external signals found."
        except Exception as exc:
            print(f"      Search failed: {exc}")
            return f"Search failed: {str(exc)[:100]}"

    def _build_search_query(self, paper: Paper) -> str:
        return (
            f'"{paper.title}" '
            "(site:github.com OR site:reddit.com OR site:twitter.com OR site:huggingface.co) "
            "(review OR discussion OR implementation OR reproducibility)"
        )

    async def _call_tavily(self, query: str) -> Optional[str]:
        payload = {
            "api_key": self.api_key,
            "query": query,
            "search_depth": self.search_depth,
            "max_results": 5,
            "include_answer": True,
            "include_raw_content": False,
        }
        try:
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(self.TAVILY_API_URL, json=payload) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        print(f"      Tavily API error: {response.status} - {error_text[:100]}")
                        return None
                    data = await response.json()
                    if data.get("answer"):
                        return self._format_tavily_answer(data["answer"])
                    results = data.get("results", [])
                    if not results:
                        return None
                    return self._format_tavily_results(results)
        except asyncio.TimeoutError:
            print("      Tavily timeout")
            return None
        except Exception as exc:
            print(f"      Tavily error: {type(exc).__name__}: {exc}")
            return None

    def _format_tavily_answer(self, answer: str) -> str:
        sentences = answer.split(". ")
        summary = ". ".join(sentences[:3])
        if not summary.endswith("."):
            summary += "."
        return summary

    def _format_tavily_results(self, results: List[dict]) -> str:
        signals = []
        for result in results[:3]:
            title = result.get("title", "")
            url = result.get("url", "")
            content = result.get("content", "")
            if "github.com" in url and content:
                import re

                star_match = re.search(r"(\d+[\d,]*)\s*stars?", content, re.IGNORECASE)
                if star_match:
                    signals.append(f"GitHub repo with {star_match.group(1)} stars")
                else:
                    signals.append("GitHub implementation available")
            elif "reddit.com" in url or "twitter.com" in url:
                platform = "Reddit" if "reddit.com" in url else "Twitter"
                snippet = content[:100].strip()
                if snippet:
                    signals.append(f"{platform} discussion: {snippet}...")
            elif "huggingface.co" in url:
                signals.append(f"HuggingFace: {title[:60]}")

        if not signals:
            return "No significant external signals found."
        if len(signals) == 1:
            return signals[0] + "."
        if len(signals) == 2:
            return f"{signals[0]}. {signals[1]}."
        return f"{signals[0]}. {signals[1]}. {signals[2]}."


class MockPaperResearcher:
    async def research(self, papers: List[Paper]) -> List[Paper]:
        print(f"\nMock research for {len(papers)} papers...")
        for i, paper in enumerate(papers, 1):
            print(f"   [{i}/{len(papers)}] Mock researching: {paper.title[:50]}...")
            paper.research_notes = "Mock: GitHub repo with ~500 stars. Some discussion on Reddit about methodology."
            await asyncio.sleep(0.1)
        print("   Mock research complete")
        return papers

