"""
Paper summarization using any LLM.
"""

from __future__ import annotations

from datetime import datetime

from paperfeeder.models import Paper
from paperfeeder.chat import LLMClient


class PaperSummarizer:
    """Generate paper summaries and insights using any LLM."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        model: str = "gpt-4o-mini",
        research_interests: str = "",
        prompt_addon: str = "",
        debug_save_pdfs: bool = False,
        debug_pdf_dir: str = "debug_pdfs",
        pdf_max_pages: int = 10,
    ):
        self.client = LLMClient(
            api_key=api_key,
            base_url=base_url,
            model=model,
            debug_save_pdfs=debug_save_pdfs,
            debug_pdf_dir=debug_pdf_dir,
            pdf_max_pages=pdf_max_pages,
        )
        self.research_interests = research_interests
        self.prompt_addon = prompt_addon.strip()

    def _build_prompt(
        self,
        papers: list[Paper],
        papers_with_pdf: list[Paper] = None,
        failed_pdf_papers: list[Paper] = None,
        blog_posts: list[Paper] = None,
    ) -> str:
        failed_pdf_set = set(failed_pdf_papers) if failed_pdf_papers else set()
        blog_posts = blog_posts or []

        papers_info = []
        for i, paper in enumerate(papers, 1):
            authors_str = ", ".join([author.name for author in paper.authors[:5]])
            if len(paper.authors) > 5:
                authors_str += " et al."

            has_pdf = papers_with_pdf and paper in papers_with_pdf
            is_failed = paper in failed_pdf_set
            if is_failed:
                pdf_note = " [PDF failed]"
            elif has_pdf:
                pdf_note = " [PDF]"
            else:
                pdf_note = ""

            community_signal = ""
            if hasattr(paper, "research_notes") and paper.research_notes:
                community_signal = f"\n   Community Signals: {paper.research_notes}"

            papers_info.append(
                f"{i}. {paper.title}{pdf_note}\n"
                f"   Authors: {authors_str}\n"
                f"   URL: {paper.url}"
                f"{community_signal}"
            )

        blog_info = []
        if blog_posts:
            for i, post in enumerate(blog_posts, 1):
                source = getattr(post, "blog_source", "Unknown")
                title = post.title[7:] if post.title.startswith("[Blog] ") else post.title
                content_preview = post.abstract[:500] if post.abstract else "No content preview"
                blog_info.append(
                    f"{i}. {title}\n"
                    f"   Source: {source}\n"
                    f"   URL: {post.url}\n"
                    f"   Content: {content_preview}..."
                )

        pdf_context = ""
        if papers_with_pdf:
            successful_count = len(papers_with_pdf) - len(failed_pdf_set)
            pdf_context = f"\n\n{successful_count} PDFs provided for deep analysis."
            if failed_pdf_set:
                pdf_context += f" ({len(failed_pdf_set)} failed, using abstract only)"

        system_prompt = """You are a Senior Principal Researcher at a top-tier AI lab (OpenAI/DeepMind/Anthropic caliber), screening papers AND blog posts for your research team.

## Your Philosophy
- You DESPISE incremental work. "Beat SOTA by 0.2%" makes you yawn.
- You hunt for Paradigm Shifts, Counter-intuitive Findings, and Mathematical Elegance.
- You value First Principles Thinking over empirical bag-of-tricks.
- You care about what scales and what actually matters.

## Your Evaluation Lens
For each paper AND blog post, you instinctively assess:
- Surprise: Does it challenge my priors? Is there an "aha" moment?
- Rigor: Is the content substantive, or is it just marketing fluff?
- Impact: Could this change how we build systems? Or is it a footnote?
- Relevance: Is it actually about AI/ML research, or off-topic?

## Your Communication Style
- 犀利、专业、不废话
- 中英文夹杂
- 直接给判断，不要模棱两可

## CRITICAL: Blog Post Filtering
- NOT all blog posts are worth reading!
- Filter OUT: marketing content, product announcements, off-topic posts
- Keep ONLY: technical deep dives, year-in-review posts, research insights, methodology discussions
- A blog post from a famous source can still be SKIP-worthy if it's not about AI research"""

        if self.prompt_addon:
            system_prompt += f"\n\n## Additional User Guidance\n{self.prompt_addon}"

        papers_section = ""
        if papers:
            papers_section = f"""
## Today's Paper Pool ({len(papers)} papers)
{chr(10).join(papers_info)}{pdf_context}
"""

        blogs_section = ""
        if blog_posts:
            blogs_section = f"""
## Blog Posts from Priority Sources ({len(blog_posts)} posts)
These need filtering too.

{chr(10).join(blog_info)}
"""

        user_prompt = f"""## My Research Interests
{self.research_interests}
{blogs_section}{papers_section}
---

## Your Task

请以 Senior Principal Researcher 的视角审阅这批内容，输出 clean HTML（不要 html/head/body 标签）。

Critical requirements:
1. 博客也要筛选，不是所有博客都值得读。
2. 宁缺毋滥。
3. 具体、可执行。
4. 深度分析要有干货。
5. **视觉：必须浅色清爽** — 正文区块背景只用 #ffffff 或 #f8fafc；文字用深色 #1e293b / #334155。**禁止**黑底/深灰底配浅色字、禁止整段「深色卡片」风格；链接用蓝色即可。
6. 每个条目请保留可点击的论文/博客 **原始 URL**（与上方列表中的 URL 一致），用 `<a href="...">` 输出，便于反馈按钮匹配。
7. **版式宽度**：不要在外层再包 `<div style="max-width:...">`、居中窄栏或多层大 `padding`/`margin`；宿主页面已有 `.content` 与整页宽度约束。请用 `<h2>`、`<p>`、`<section>` 等**平铺**，避免「大边距套小边距」把正文挤成细条。
"""

        return {"system": system_prompt, "user": user_prompt}

    async def generate_report(
        self,
        papers: list[Paper],
        use_pdf_multimodal: bool = True,
        blog_posts: list[Paper] = None,
    ) -> str:
        if not papers and not blog_posts:
            return self._wrap_html("<p>No papers or blog posts to review today.</p>", [], blog_posts)

        actual_papers = []
        actual_blogs = list(blog_posts) if blog_posts else []
        for paper in papers:
            if getattr(paper, "is_blog", False):
                actual_blogs.append(paper)
            else:
                actual_papers.append(paper)

        seen_urls = set()
        unique_blogs = []
        for blog in actual_blogs:
            if blog.url not in seen_urls:
                seen_urls.add(blog.url)
                unique_blogs.append(blog)
        actual_blogs = unique_blogs

        papers_with_pdf = []
        failed_pdf_papers = []
        if use_pdf_multimodal and actual_papers:
            print(f"   Processing {len(actual_papers)} PDFs individually...")
            for i, paper in enumerate(actual_papers, 1):
                print(f"      [{i}/{len(actual_papers)}] {paper.title[:40]}...")
                if not getattr(paper, "pdf_url", None):
                    failed_pdf_papers.append(paper)
                    paper._pdf_base64 = None
                    print("      No pdf_url, fallback to abstract-only")
                    continue
                pdf_content = await self.client._url_to_base64_async(
                    paper.pdf_url,
                    save_debug=getattr(self.client, "debug_save_pdfs", False),
                    debug_dir=getattr(self.client, "debug_pdf_dir", "debug_pdfs"),
                    max_pages=getattr(self.client, "pdf_max_pages", 10),
                )
                if pdf_content:
                    paper._pdf_base64 = pdf_content
                    papers_with_pdf.append(paper)
                else:
                    failed_pdf_papers.append(paper)
                    paper._pdf_base64 = None

        prompts = self._build_prompt(actual_papers, papers_with_pdf, failed_pdf_papers, blog_posts=actual_blogs)
        messages = [{"role": "system", "content": prompts["system"]}]

        user_content = []
        for paper in papers_with_pdf:
            if paper not in failed_pdf_papers and hasattr(paper, "_pdf_base64") and paper._pdf_base64:
                user_content.append(
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": paper._pdf_base64,
                        },
                        "cache_control": {"type": "ephemeral"},
                    }
                )
        user_content.append({"type": "text", "text": prompts["user"]})
        messages.append({"role": "user", "content": user_content})

        try:
            content = await self.client.achat(messages, max_tokens=8000)
            all_items = actual_papers + actual_blogs
            return self._wrap_html(content, all_items, actual_blogs)
        except Exception as exc:
            error_msg = f"<p class='error'>Error generating report: {str(exc)}</p>"
            return self._wrap_html(error_msg, actual_papers, actual_blogs)

    def _wrap_html(self, content: str, papers: list[Paper], blog_posts: list[Paper] = None) -> str:
        today = datetime.now()
        today_cn = today.strftime("%Y年%m月%d日")
        weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        weekday = weekdays[today.weekday()]
        paper_count = len([paper for paper in papers if not getattr(paper, "is_blog", False)])
        blog_count = len(blog_posts) if blog_posts else 0

        if blog_count > 0 and paper_count > 0:
            meta_str = f"{paper_count} papers + {blog_count} blogs reviewed"
        elif blog_count > 0:
            meta_str = f"{blog_count} blogs reviewed"
        else:
            meta_str = f"{paper_count} papers reviewed"

        return f"""<!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Paper Digest - {today.strftime("%Y-%m-%d")}</title>
        <script src="https://polyfill.io/v3/polyfill.min.js?features=es6"></script>
        <script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
        <style>
            :root {{ color-scheme: light; }}
            * {{ box-sizing: border-box; margin: 0; padding: 0; }}
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif;
                line-height: 1.55;
                color: #0f172a;
                background: linear-gradient(180deg, #e8f2fc 0%, #f1f5f9 45%, #e2e8f0 100%);
                /* One outer gutter only; inner padding lives in .header / .content to avoid triple side margins */
                padding: max(0px, env(safe-area-inset-top)) max(0px, env(safe-area-inset-right)) max(0px, env(safe-area-inset-bottom)) max(0px, env(safe-area-inset-left));
                font-size: clamp(15px, 2.8vw, 16px);
            }}
            .container {{
                max-width: min(52rem, 100%);
                margin: 0 auto;
                background: #fff;
                border-radius: 14px;
                box-shadow: 0 4px 24px rgba(15, 23, 42, 0.08);
                border: 1px solid rgba(148, 163, 184, 0.35);
                overflow: hidden;
            }}
            .header {{
                background: linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 50%, #dbeafe 100%);
                color: #0c4a6e;
                padding: 6px 8px;
                text-align: center;
                border-bottom: 1px solid rgba(125, 211, 252, 0.5);
            }}
            .header h1 {{ font-size: 1.35rem; font-weight: 700; letter-spacing: -0.02em; color: #0369a1; }}
            .header .meta {{ margin-top: 6px; font-size: 0.9rem; color: #0e7490; }}
            .header .persona {{ margin-top: 4px; font-size: 0.8rem; color: #64748b; }}
            .content {{
                padding: 6px 8px 8px;
                color: #1e293b;
            }}
            .content h2, .content h3 {{ color: #0f172a; margin-top: 1em; }}
            .content a {{ color: #2563eb; }}
            .footer {{ text-align: center; padding: 6px 8px; font-size: 0.72rem; color: #64748b; border-top: 1px solid #e2e8f0; background: #f8fafc; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>Paper Digest</h1>
                <div class="meta">{today_cn} {weekday} · {meta_str}</div>
                <div class="persona">Curated by PaperFeeder · No fluff, no hype</div>
            </div>
            <div class="content">
                {content}
            </div>
            <div class="footer">
                PaperFeeder · {self._get_unique_keywords(papers)}
            </div>
        </div>
    </body>
    </html>"""

    def _get_unique_keywords(self, papers: list[Paper]) -> str:
        keywords = set()
        for paper in papers:
            if hasattr(paper, "matched_keywords"):
                keywords.update(paper.matched_keywords)
        return ", ".join(sorted(keywords)[:8]) if keywords else "AI Research"


ClaudeSummarizer = PaperSummarizer
