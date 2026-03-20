"""Filters for selecting relevant papers - upgraded for two-stage filtering."""

from __future__ import annotations

import asyncio
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from paperfeeder.models import Paper
from paperfeeder.chat import LLMClient


class KeywordFilter:
    """Simple keyword filter matching title and abstract."""

    def __init__(self, keywords: Optional[List[str]] = None, exclude_keywords: Optional[List[str]] = None):
        self.keywords = [keyword.lower() for keyword in (keywords or [])]
        self.exclude_keywords = [keyword.lower() for keyword in (exclude_keywords or [])]

    def filter(self, papers: List[Paper]) -> List[Paper]:
        if not self.keywords and not self.exclude_keywords:
            return papers

        matched = []
        for paper in papers:
            text = " ".join(filter(None, [getattr(paper, "title", ""), getattr(paper, "abstract", "")])).lower()
            if self.exclude_keywords and any(excluded in text for excluded in self.exclude_keywords):
                continue
            if self.keywords:
                matched_keywords = [keyword for keyword in self.keywords if keyword in text]
                if matched_keywords:
                    paper.matched_keywords = matched_keywords
                    matched.append(paper)
            else:
                matched.append(paper)
        return matched


class LLMFilter:
    """
    LLM-based paper filter supporting two-stage filtering.
    """

    def __init__(
        self,
        api_key: str,
        research_interests: str,
        prompt_addon: str = "",
        base_url: str = "https://api.openai.com/v1",
        model: str = "gpt-4o-mini",
        batch_size: int = 10,
    ):
        self.api_key = api_key
        self.research_interests = research_interests
        self.prompt_addon = prompt_addon.strip()
        self.base_url = base_url
        self.model = model
        self.batch_size = batch_size
        self.debug_dir = Path(os.getenv("LLM_FILTER_DEBUG_DIR", "llm_filter_debug"))

    async def filter(
        self,
        papers: List[Paper],
        max_papers: int = 20,
        include_community_signals: bool = False,
        **kwargs,
    ) -> List[Paper]:
        if not papers:
            return []

        client = LLMClient(api_key=self.api_key, base_url=self.base_url, model=self.model)
        all_scored_papers: List[Paper] = []
        total_batches = (len(papers) + self.batch_size - 1) // self.batch_size

        stage_name = "Fine (with community signals)" if include_community_signals else "Coarse (title+abstract)"
        print(f"   LLM Filter [{stage_name}]: Processing {len(papers)} papers in {total_batches} batches")

        for batch_idx, batch_start in enumerate(range(0, len(papers), self.batch_size)):
            batch_papers = papers[batch_start : batch_start + self.batch_size]
            print(f"   Batch {batch_idx + 1}/{total_batches} ({len(batch_papers)} papers)...")
            batch_results = await self._filter_batch(
                client,
                batch_papers,
                batch_start,
                include_community_signals=include_community_signals,
            )
            all_scored_papers.extend(batch_results)
            if batch_idx < total_batches - 1:
                await asyncio.sleep(0.5)

        print(f"   Scored {len(all_scored_papers)} papers, sorting by relevance...")
        all_scored_papers.sort(key=lambda paper: getattr(paper, "relevance_score", 0), reverse=True)
        return all_scored_papers[:max_papers]

    async def _filter_batch(
        self,
        client,
        papers: List[Paper],
        offset: int = 0,
        include_community_signals: bool = False,
    ) -> List[Paper]:
        papers_text = ""
        for index, paper in enumerate(papers):
            authors_str = ", ".join(
                [
                    f"{author.name}" + (f" ({author.affiliation})" if getattr(author, "affiliation", None) else "")
                    for author in getattr(paper, "authors", [])[:5]
                ]
            )
            if len(getattr(paper, "authors", [])) > 5:
                authors_str += " et al."
            categories = ", ".join(getattr(paper, "categories", [])[:3]) if getattr(paper, "categories", None) else "N/A"
            paper_block = f"""
Paper {index+1}:
Title: {paper.title}
Authors: {authors_str}
Abstract: {paper.abstract[:600]}...
Categories: {categories}"""
            if include_community_signals and hasattr(paper, "research_notes") and paper.research_notes:
                paper_block += f"\nCommunity Signals: {paper.research_notes}"
            papers_text += paper_block + "\n---\n"

        prompt = (
            self._build_fine_filter_prompt(papers_text, len(papers))
            if include_community_signals
            else self._build_coarse_filter_prompt(papers_text, len(papers))
        )

        result_text: Optional[str] = None
        try:
            messages = [{"role": "user", "content": prompt}]
            result_text = await client.achat(messages, max_tokens=2000)
            result_text = (result_text or "").strip()
            if result_text.startswith("```"):
                result_text = re.sub(r"^```(?:json)?\s*\n", "", result_text)
                result_text = re.sub(r"\n```$", "", result_text)

            json_match = re.search(r"\[.*\]", result_text, re.DOTALL)
            if not json_match:
                print(f"   LLM filter: Could not parse response (batch offset {offset})")
                self._log_parse_failure("no_json_array_match", offset, include_community_signals, prompt, result_text)
                return self._fallback_scoring(papers)

            scores = json.loads(json_match.group())
            if not isinstance(scores, list):
                print(f"   LLM filter: Invalid response format (batch offset {offset})")
                self._log_parse_failure("json_not_list", offset, include_community_signals, prompt, result_text)
                return self._fallback_scoring(papers)

            scored_papers: List[Paper] = []
            for item in scores:
                if not isinstance(item, dict) or "paper_num" not in item or "score" not in item:
                    continue
                paper_idx = int(item["paper_num"]) - 1
                if 0 <= paper_idx < len(papers):
                    paper = papers[paper_idx]
                    try:
                        score_val = float(item["score"]) / 10.0
                    except Exception:
                        score_val = 0.0
                    paper.relevance_score = score_val
                    paper.filter_reason = item.get("reason", "")
                    scored_papers.append(paper)
            return scored_papers
        except json.JSONDecodeError as exc:
            print(f"   LLM filter JSON error (batch offset {offset}): {exc}")
            self._log_parse_failure(f"json_decode_error:{exc}", offset, include_community_signals, prompt, result_text)
            return self._fallback_scoring(papers)
        except Exception as exc:
            print(f"   LLM filter error (batch offset {offset}): {type(exc).__name__}: {exc}")
            self._log_parse_failure(
                f"runtime_error:{type(exc).__name__}:{exc}",
                offset,
                include_community_signals,
                prompt,
                result_text,
            )
            return self._fallback_scoring(papers)

    def _log_parse_failure(
        self,
        reason: str,
        offset: int,
        include_community_signals: bool,
        prompt: str,
        response_text: Optional[str],
    ) -> None:
        stage = "fine" if include_community_signals else "coarse"
        response_text = response_text or ""
        ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        self.debug_dir.mkdir(parents=True, exist_ok=True)
        debug_path = self.debug_dir / f"{stage}_offset{offset}_{ts}.log"
        debug_payload = (
            f"reason={reason}\n"
            f"model={self.model}\n"
            f"base_url={self.base_url}\n"
            f"stage={stage}\n"
            f"batch_offset={offset}\n"
            f"prompt_chars={len(prompt)}\n"
            f"response_chars={len(response_text)}\n"
            "\n=== PROMPT BEGIN ===\n"
            f"{prompt}\n"
            "=== PROMPT END ===\n"
            "\n=== RESPONSE BEGIN ===\n"
            f"{response_text}\n"
            "=== RESPONSE END ===\n"
        )
        debug_path.write_text(debug_payload)
        print(f"   LLM filter debug saved: {debug_path} | reason={reason} | model={self.model}")
        print("   Full raw response follows:")
        print("   ----- RESPONSE BEGIN -----")
        print(response_text)
        print("   ----- RESPONSE END -----")

    def _build_coarse_filter_prompt(self, papers_text: str, num_papers: int) -> str:
        addon_block = f"\nAdditional guidance:\n{self.prompt_addon}\n" if self.prompt_addon else ""
        return f"""You are a research paper screening assistant doing COARSE filtering (Stage 1/2).

Your task: Quickly score papers based ONLY on title and abstract relevance.

My research interests:
{self.research_interests}
{addon_block}

Papers to evaluate:
{papers_text}

Scoring criteria (0-10):
- Relevance: How well does the title/abstract match my research interests?
- Novelty: Does it propose something new or just incremental improvements?
- Clarity: Is the contribution clear from the abstract?

Return a JSON array with paper number, score, and brief reason:
[{{"paper_num": 1, "score": 8, "reason": "brief reason"}}, ...]

Requirements:
- Only return papers with score >= 6 (be generous at this stage)
- Sort by score from high to low
- You must evaluate ALL {num_papers} papers in this batch
- This is COARSE filtering - focus on potential, not perfection

Return only the JSON array, no other text."""

    def _build_fine_filter_prompt(self, papers_text: str, num_papers: int) -> str:
        addon_block = f"\nAdditional guidance:\n{self.prompt_addon}\n" if self.prompt_addon else ""
        return f"""You are a Senior Principal Researcher doing FINE filtering (Stage 2/2).

Your task: Select the TOP papers based on content + external signals.

My research interests:
{self.research_interests}
{addon_block}

Papers to evaluate (with community signals):
{papers_text}

Scoring criteria (0-10):
1. Relevance: How well does the title/abstract match my research interests?
2. Surprise: Does it challenge conventional wisdom? Is there an "aha" moment?
3. Significance: Top-tier venue? Well-known authors? Novel methodology?
4. External Signal:
   - BOOST: High GitHub stars, active discussions, reproducible code
   - PENALTY: Negative reviews, reproducibility issues, overhyped claims

Return a JSON array with paper number, score, and detailed reason:
[{{"paper_num": 1, "score": 9, "reason": "Paradigm-shifting approach to X. 1k GitHub stars. Hot discussion on Reddit about implications for Y."}}, ...]

Requirements:
- Only return papers with score >= 6
- Sort by score from high to low
- Reason MUST explain: (1) why it's surprising/important AND (2) what community signals say
- Prioritize papers with both strong content AND positive external validation
- A paper needs at least one dimension >= 8 to be "Editor's Choice".

Return only the JSON array, no other text."""

    def _fallback_scoring(self, papers: List[Paper]) -> List[Paper]:
        return sorted(papers, key=lambda paper: getattr(paper, "relevance_score", 0), reverse=True)
