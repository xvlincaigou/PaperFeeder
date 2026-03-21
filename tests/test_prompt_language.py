from __future__ import annotations

import unittest

from paperfeeder.pipeline.prompt_templates import normalize_prompt_language
from paperfeeder.pipeline.summarizer import PaperSummarizer


class PromptLanguageTests(unittest.TestCase):
    def test_language_aliases_normalize(self) -> None:
        self.assertEqual(normalize_prompt_language("zh"), "zh-CN")
        self.assertEqual(normalize_prompt_language("en"), "en-US")
        self.assertEqual(normalize_prompt_language("en-us"), "en-US")
        self.assertEqual(normalize_prompt_language("unknown"), "zh-CN")

    def test_english_prompt_pack_used(self) -> None:
        summarizer = PaperSummarizer(api_key="test", prompt_language="en")
        prompts = summarizer._build_prompt([], blog_posts=[])
        self.assertIn("## My Research Interests", prompts["user"])
        self.assertIn("Write primarily in English.", prompts["user"])
        html = summarizer._wrap_html("<p>Test</p>", [], [])
        self.assertIn("Paper Digest", html)
        self.assertIn("0 papers reviewed", html)

    def test_chinese_prompt_pack_used(self) -> None:
        summarizer = PaperSummarizer(api_key="test", prompt_language="zh-CN")
        prompts = summarizer._build_prompt([], blog_posts=[])
        self.assertIn("## 我的研究兴趣", prompts["user"])
        self.assertIn("输出语言以简体中文为主", prompts["user"])
        html = summarizer._wrap_html("<p>测试</p>", [], [])
        self.assertIn("已审阅 0 篇论文", html)


if __name__ == "__main__":
    unittest.main()