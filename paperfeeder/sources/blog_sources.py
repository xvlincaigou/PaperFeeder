"""
Blog source fetcher via RSS/Atom feeds.
Fetches from AI research blogs, tech company blogs, and individual researchers.
All fetched blog posts go through the blog prefilter before synthesis.
"""

from __future__ import annotations

import asyncio
import aiohttp
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import re
from dataclasses import dataclass

try:
    import feedparser
except ImportError:
    feedparser = None
    print("⚠️  feedparser not installed. Run: pip install feedparser")

from paperfeeder.models import Author, Paper, PaperSource
from .base import BaseSource


# =============================================================================
# Pre-defined Blog Configurations
# =============================================================================

PRIORITY_BLOGS: Dict[str, Dict[str, Any]] = {
    # === 工业界三巨头 (最前沿动态) ===
    "openai": {
        "name": "OpenAI Blog",
        "feed_url": "https://openai.com/news/rss.xml",
        "website": "https://openai.com/news",
        "priority": True,
    },
    "anthropic": {
        "name": "Anthropic News & Research",
        # Anthropic 官方 RSS 路径较不稳定，建议检查其 /index.xml 或使用自定义爬虫
        "feed_url": "https://www.anthropic.com/index.xml", 
        "website": "https://www.anthropic.com/news",
        "priority": True,
    },
    "deepmind": {
        "name": "Google DeepMind",
        "feed_url": "https://deepmind.google/blog/rss.xml",
        "website": "https://deepmind.google/about/research/",
        "priority": True,
    },

    # === 开源与基座模型 (实战与生态) ===
    "huggingface": {
        "name": "Hugging Face Blog",
        "feed_url": "https://huggingface.co/blog/feed.xml",
        "website": "https://huggingface.co/blog",
        "priority": True,
    },
    "meta_research": {
        "name": "Meta Research",
        # 修复 Meta 404 问题，指向更硬核的 Research 频道而非 News
        "feed_url": "https://research.facebook.com/feed/", 
        "website": "https://ai.meta.com/research/",
        "priority": True,
    },

    # === 顶级个人博客 (深度洞察与方法论) ===
    "karpathy": {
        "name": "Andrej Karpathy",
        "feed_url": "https://karpathy.bearblog.dev/feed/",
        "website": "https://karpathy.bearblog.dev/",
        "priority": True,
    },
    "lilianweng": {
        "name": "Lil'Log (Lilian Weng)",
        "feed_url": "https://lilianweng.github.io/index.xml",
        "website": "https://lilianweng.github.io/",
        "priority": True,
    },
    "colah": {
        "name": "Christopher Olah (Circuits/Interpretability)",
        "feed_url": "https://colah.github.io/rss.xml",
        "website": "https://colah.github.io/",
        "priority": True,
    },

    # === 学术实验室 (长线研究) ===
    "bair": {
        "name": "Berkeley AI Research (BAIR)",
        "feed_url": "https://bair.berkeley.edu/blog/feed.xml",
        "website": "https://bair.berkeley.edu/blog/",
        "priority": True,
    },
    "nvidia_research": {
        "name": "NVIDIA Research",
        # 替代了商业化的 NVIDIA Blog，专注于 Graphics/System/AI 论文
        "feed_url": "https://developer.nvidia.com/blog/category/simulation-graphics/feed/",
        "website": "https://research.nvidia.com/",
        "priority": False,
    },

    # === 对齐与安全性 (硬核讨论) ===
    "alignment_forum": {
        "name": "AI Alignment Forum",
        "feed_url": "https://www.alignmentforum.org/feed.xml",
        "website": "https://www.alignmentforum.org/",
        "priority": False,
    },
    "lesswrong_ai": {
        "name": "LessWrong AI (Quality Tag)",
        "feed_url": "https://www.lesswrong.com/feed.xml?view=tagFeed&tagId=Qx37vhqLnzAR9PbEn",
        "website": "https://www.lesswrong.com/tag/ai",
        "priority": False,
    },
}


@dataclass
class BlogPost:
    """A blog post fetched from RSS/Atom feed."""
    title: str
    content: str  # Summary or full content
    url: str
    source_name: str
    published_date: Optional[datetime] = None
    author: Optional[str] = None
    priority: bool = False
    
    def to_paper(self) -> Paper:
        """Convert to Paper object for unified processing."""
        authors = [Author(name=self.author)] if self.author else []
        
        paper = Paper(
            title=f"[Blog] {self.title}",
            abstract=self.content[:2000] if self.content else "",  # Truncate if too long
            url=self.url,
            source=PaperSource.MANUAL,  # Use MANUAL as blog source
            authors=authors,
            published_date=self.published_date,
            notes=f"From: {self.source_name}",
        )
        
        paper.is_blog = True
        paper.blog_source = self.source_name
        
        return paper


class BlogSource(BaseSource):
    """
    Fetch blog posts from RSS/Atom feeds.
    
    Usage:
        # Use default configured blogs
        source = BlogSource()
        posts = await source.fetch(days_back=7)
        
        # Add custom blogs
        source = BlogSource(custom_blogs={
            "my_blog": {
                "name": "My Favorite Blog",
                "feed_url": "https://example.com/feed.xml",
                "priority": True,
            }
        })
        
        # Only fetch specific blogs
        source = BlogSource(enabled_blogs=["openai", "anthropic", "karpathy"])
    """
    
    def __init__(
        self,
        enabled_blogs: Optional[List[str]] = None,
        custom_blogs: Optional[Dict[str, Dict[str, Any]]] = None,
        include_non_priority: bool = True,
    ):
        """
        Initialize BlogSource.
        
        Args:
            enabled_blogs: List of blog keys to enable. If None, use all configured blogs.
            custom_blogs: Additional custom blog configurations.
            include_non_priority: Whether to include non-priority blogs.
        """
        if feedparser is None:
            raise ImportError("feedparser is required. Install with: pip install feedparser")
        
        self.blogs: Dict[str, Dict[str, Any]] = {}
        
        # Add default blogs
        for key, config in PRIORITY_BLOGS.items():
            if enabled_blogs is None:
                if config.get("priority", False) or include_non_priority:
                    self.blogs[key] = config
            elif key in enabled_blogs:
                self.blogs[key] = config
        
        # Add custom blogs
        if custom_blogs:
            self.blogs.update(custom_blogs)
    
    async def fetch(
        self,
        days_back: int = 7,
        max_posts_per_blog: int = 5,
    ) -> List[Paper]:
        """
        Fetch recent blog posts from all enabled blogs.
        
        Args:
            days_back: Only include posts from the last N days.
            max_posts_per_blog: Maximum posts to fetch per blog.
        
        Returns:
            List of Paper objects (converted from BlogPost).
        """
        if not self.blogs:
            print("   ⚠️ No blogs configured")
            return []
        
        print(f"📝 Fetching from {len(self.blogs)} blogs...")
        
        cutoff_date = datetime.now() - timedelta(days=days_back)
        all_posts: List[BlogPost] = []
        
        # Fetch all blogs concurrently
        tasks = []
        for key, config in self.blogs.items():
            tasks.append(self._fetch_single_blog(key, config, cutoff_date, max_posts_per_blog))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for result in results:
            if isinstance(result, Exception):
                print(f"   ⚠️ Error: {result}")
            elif result:
                all_posts.extend(result)
        
        # Convert to Paper objects
        papers = [post.to_paper() for post in all_posts]
        
        print(f"   ✅ Found {len(papers)} blog posts")
        
        return papers
    
    async def _fetch_single_blog(
        self,
        key: str,
        config: Dict[str, Any],
        cutoff_date: datetime,
        max_posts: int,
    ) -> List[BlogPost]:
        """Fetch posts from a single blog."""
        name = config.get("name", key)
        feed_url = config.get("feed_url")
        priority = config.get("priority", False)
        
        if not feed_url:
            return []

        # Browser-like headers improve reliability for some sites/CDNs.
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            "Accept": "application/rss+xml, application/xml, text/xml;q=0.9, */*;q=0.8",
        }

        content = None
        max_retries = 2
        for attempt in range(max_retries):
            try:
                timeout = aiohttp.ClientTimeout(total=45, connect=15, sock_read=30)
                async with aiohttp.ClientSession(timeout=timeout, trust_env=True, headers=headers) as session:
                    async with session.get(feed_url) as response:
                        if response.status == 404:
                            print(f"   ⚠️ {name}: HTTP 404")
                            return []
                        if response.status >= 500:
                            if attempt < max_retries - 1:
                                await asyncio.sleep(1.5)
                                continue
                            print(f"   ⚠️ {name}: HTTP {response.status}")
                            return []
                        if response.status != 200:
                            print(f"   ⚠️ {name}: HTTP {response.status}")
                            return []
                        content = await response.text()
                        break
            except asyncio.TimeoutError:
                if attempt < max_retries - 1:
                    await asyncio.sleep(1.5)
                    continue
                print(f"   ⚠️ {name}: Timeout")
                return []
            except Exception as e:
                if attempt < max_retries - 1:
                    await asyncio.sleep(1.0)
                    continue
                print(f"   ⚠️ {name}: {type(e).__name__}: {str(e)[:50]}")
                return []

        if content is None:
            print(f"   ⚠️ {name}: Failed after retries")
            return []

        try:
            
            # Parse feed
            feed = feedparser.parse(content)
            
            if feed.bozo and not feed.entries:
                print(f"   ⚠️ {name}: Failed to parse feed")
                return []
            
            posts = []
            for entry in feed.entries[:max_posts]:
                # Parse publish date
                published = None
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    published = datetime(*entry.published_parsed[:6])
                elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
                    published = datetime(*entry.updated_parsed[:6])
                
                # Skip if too old
                if published and published < cutoff_date:
                    continue
                
                # Get content (prefer summary over full content to save tokens)
                content = ""
                if hasattr(entry, 'summary'):
                    content = entry.summary
                elif hasattr(entry, 'description'):
                    content = entry.description
                elif hasattr(entry, 'content') and entry.content:
                    # Only use full content if it's reasonably short (avoid token waste)
                    full_content = entry.content[0].get('value', '')
                    if len(full_content) <= 2000:  # Reasonable limit for blog posts
                        content = full_content
                    else:
                        # Truncate very long content and add note
                        content = full_content[:2000] + "... [Content truncated to save tokens]"

                # Clean HTML tags (basic)
                content = re.sub(r'<[^>]+>', ' ', content)
                content = re.sub(r'\s+', ' ', content).strip()

                # Further limit content length for token efficiency
                if len(content) > 1500:
                    content = content[:1500] + "... [Truncated for token efficiency]"
                
                # Get author
                author = None
                if hasattr(entry, 'author'):
                    author = entry.author
                elif hasattr(entry, 'authors') and entry.authors:
                    author = entry.authors[0].get('name', '')
                
                post = BlogPost(
                    title=entry.get('title', 'Untitled'),
                    content=content,
                    url=entry.get('link', ''),
                    source_name=name,
                    published_date=published,
                    author=author,
                    priority=priority,
                )
                posts.append(post)
            
            if posts:
                print(f"   ✓ {name}: {len(posts)} posts")
            
            return posts
            
        except Exception as e:
            print(f"   ⚠️ {name}: {type(e).__name__}: {str(e)[:50]}")
            return []


class JinaReaderSource(BaseSource):
    """
    Fallback for blogs without RSS - use Jina Reader API.
    Free tier: https://r.jina.ai/{url}
    """
    
    JINA_API = "https://r.jina.ai"
    
    def __init__(self, urls: List[str]):
        """
        Args:
            urls: List of blog URLs to fetch (not RSS, actual blog pages).
        """
        self.urls = urls
    
    async def fetch(self) -> List[Paper]:
        """Fetch blog content via Jina Reader API."""
        papers = []
        
        for url in self.urls:
            try:
                jina_url = f"{self.JINA_API}/{url}"
                
                timeout = aiohttp.ClientTimeout(total=60)
                async with aiohttp.ClientSession(timeout=timeout, trust_env=True) as session:
                    async with session.get(jina_url) as response:
                        if response.status != 200:
                            print(f"   ⚠️ Jina Reader failed for {url}: HTTP {response.status}")
                            continue
                        
                        content = await response.text()
                
                # Extract title from first line (Jina format)
                lines = content.strip().split('\n')
                title = lines[0] if lines else "Blog Post"
                body = '\n'.join(lines[1:]) if len(lines) > 1 else ""
                
                paper = Paper(
                    title=f"[Blog] {title[:100]}",
                    abstract=body[:2000],
                    url=url,
                    source=PaperSource.MANUAL,
                )
                paper.is_blog = True
                papers.append(paper)
                
            except Exception as e:
                print(f"   ⚠️ Error fetching {url}: {e}")
        
        return papers


# =============================================================================
# Helper function for main.py integration
# =============================================================================

async def fetch_blog_posts(
    config,  # Config object
    days_back: int = 7,
) -> tuple[List[Paper], List[Paper]]:
    """
    Fetch blog posts and return them in a single prefilterable pool.
    
    Returns:
        ([], all_posts)
        - first list kept empty for backward compatibility
        - second list contains all fetched blog posts to be prefiltered upstream
    """
    # Get enabled blogs from config
    enabled_blogs = getattr(config, 'enabled_blogs', None)
    custom_blogs = getattr(config, 'custom_blogs', None)
    
    source = BlogSource(
        enabled_blogs=enabled_blogs,
        custom_blogs=custom_blogs,
        include_non_priority=True,
    )
    
    all_posts = await source.fetch(days_back=days_back)
    
    return [], all_posts


# =============================================================================
# Example usage
# =============================================================================

if __name__ == "__main__":
    async def main():
        print("=" * 60)
        print("Blog Source Test")
        print("=" * 60)
        
        # Test with selected blogs
        source = BlogSource(
            enabled_blogs=["openai", "anthropic", "karpathy", "lilianweng"],
        )
        
        papers = await source.fetch(days_back=30, max_posts_per_blog=3)
        
        print(f"\n📊 Results:")
        for paper in papers[:10]:
            print(f"  {paper.title[:60]}...")
            print(f"      URL: {paper.url}")
            print(f"      From: {getattr(paper, 'blog_source', 'Unknown')}")
            print()
    
    asyncio.run(main())

