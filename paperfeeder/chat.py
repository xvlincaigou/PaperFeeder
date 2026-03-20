"""
OpenAI-compatible chat client (remote APIs, local endpoints, Anthropic, etc.).
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import List, Optional

import aiohttp
import httpx
from openai import AsyncOpenAI, OpenAI


class LLMClient:
    """
    Chat client using OpenAI-compatible HTTP APIs where applicable.
    """

    PDF_NATIVE_MODELS = ["claude", "gemini"]

    def __init__(
        self,
        api_key: str = None,
        base_url: str = "https://api.openai.com/v1",
        model: str = "gpt-4o-mini",
        timeout: int = 120,
        debug_save_pdfs: bool = False,
        debug_pdf_dir: str = "debug_pdfs",
        pdf_max_pages: int = 10,
    ):
        self.model = model
        self.base_url = base_url
        self.debug_save_pdfs = debug_save_pdfs
        self.debug_pdf_dir = debug_pdf_dir
        self.pdf_max_pages = pdf_max_pages
        self.is_anthropic = "anthropic.com" in base_url

        if self.is_anthropic:
            import anthropic

            self.client = anthropic.Anthropic(api_key=api_key)
            self.async_client = anthropic.AsyncAnthropic(api_key=api_key)
        else:
            self.client = OpenAI(
                api_key=api_key or "not-needed",
                base_url=base_url,
                timeout=httpx.Timeout(timeout),
            )
            self.async_client = AsyncOpenAI(
                api_key=api_key or "not-needed",
                base_url=base_url,
                timeout=httpx.Timeout(timeout),
            )

    def chat(self, messages: list[dict], max_tokens: int = 4000, temperature: float = 0.7) -> str:
        if self.is_anthropic:
            response = self.client.messages.create(model=self.model, max_tokens=max_tokens, messages=messages)
            return response.content[0].text
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return response.choices[0].message.content

    async def achat(self, messages: list[dict], max_tokens: int = 4000, temperature: float = 0.7) -> str:
        if self.is_anthropic:
            response = await self.async_client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                messages=messages,
            )
            return response.content[0].text
        response = await self.async_client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return response.choices[0].message.content

    async def achat_with_pdf(
        self,
        prompt: str,
        pdf_path: Optional[str] = None,
        pdf_url: Optional[str] = None,
        pdf_base64: Optional[str] = None,
        max_tokens: int = 4000,
    ) -> str:
        if pdf_base64:
            pdf_data = pdf_base64
        elif pdf_path:
            pdf_data = self._file_to_base64(pdf_path)
        elif pdf_url:
            pdf_data = await self._url_to_base64_async(
                pdf_url,
                save_debug=getattr(self, "debug_save_pdfs", False),
                debug_dir=getattr(self, "debug_pdf_dir", "debug_pdfs"),
                max_pages=getattr(self, "pdf_max_pages", 10),
            )
            if pdf_data is None:
                raise ValueError(f"Failed to download PDF from {pdf_url}")
        else:
            raise ValueError("Must provide pdf_path, pdf_url, or pdf_base64")

        if self.is_anthropic:
            messages = [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "document",
                            "source": {
                                "type": "base64",
                                "media_type": "application/pdf",
                                "data": pdf_data,
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ]
            response = await self.async_client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                messages=messages,
            )
            return response.content[0].text

        if self.supports_pdf_native():
            messages = [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "file",
                            "file": {
                                "filename": "paper.pdf",
                                "file_data": f"data:application/pdf;base64,{pdf_data}",
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ]
            return await self.achat(messages, max_tokens=max_tokens)

        text = self._extract_pdf_text_from_base64(pdf_data)
        messages = [{"role": "user", "content": f"{prompt}\n\n---\nPaper content:\n{text[:30000]}"}]
        return await self.achat(messages, max_tokens=max_tokens)

    async def achat_with_multiple_pdfs(
        self,
        prompt: str,
        pdf_urls: List[str],
        max_tokens: int = 4000,
    ) -> tuple[str, List[int]]:
        if not pdf_urls:
            raise ValueError("Must provide at least one PDF URL")

        pdf_data_list = []
        failed_indices = []
        for i, url in enumerate(pdf_urls):
            pdf_data = await self._url_to_base64_async(
                url,
                save_debug=getattr(self, "debug_save_pdfs", False),
                max_pages=getattr(self, "pdf_max_pages", 10),
            )
            if pdf_data is None:
                failed_indices.append(i)
                pdf_data_list.append(None)
            else:
                pdf_data_list.append(pdf_data)

        successful_pdfs = [data for data in pdf_data_list if data is not None]
        if not successful_pdfs:
            raise ValueError("All PDF downloads failed")

        if self.is_anthropic:
            content = []
            for pdf_data in pdf_data_list:
                if pdf_data is not None:
                    content.append(
                        {
                            "type": "document",
                            "source": {
                                "type": "base64",
                                "media_type": "application/pdf",
                                "data": pdf_data,
                            },
                        }
                    )
            if failed_indices:
                prompt = prompt + f"\n\n注意：有 {len(failed_indices)} 篇论文的PDF下载失败，将仅基于摘要进行分析。"
            content.append({"type": "text", "text": prompt})
            messages = [{"role": "user", "content": content}]
            response = await self.async_client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                messages=messages,
            )
            return response.content[0].text, failed_indices

        raise NotImplementedError("Multiple PDFs not yet supported for this model. Use achat_with_pdf for single PDFs.")

    def supports_pdf_native(self) -> bool:
        return any(prefix in self.model.lower() for prefix in self.PDF_NATIVE_MODELS)

    def chat_with_pdf(
        self,
        prompt: str,
        pdf_path: Optional[str] = None,
        pdf_url: Optional[str] = None,
        pdf_base64: Optional[str] = None,
        max_tokens: int = 4000,
    ) -> str:
        if pdf_base64:
            pdf_data = pdf_base64
        elif pdf_path:
            pdf_data = self._file_to_base64(pdf_path)
        elif pdf_url:
            pdf_data = self._url_to_base64(pdf_url)
        else:
            raise ValueError("Must provide pdf_path, pdf_url, or pdf_base64")

        if self.is_anthropic:
            messages = [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "document",
                            "source": {
                                "type": "base64",
                                "media_type": "application/pdf",
                                "data": pdf_data,
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ]
            response = self.client.messages.create(model=self.model, max_tokens=max_tokens, messages=messages)
            return response.content[0].text

        if self.supports_pdf_native():
            messages = [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "file",
                            "file": {
                                "filename": "paper.pdf",
                                "file_data": f"data:application/pdf;base64,{pdf_data}",
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ]
            return self.chat(messages, max_tokens=max_tokens)

        text = self._extract_pdf_text_from_base64(pdf_data)
        messages = [{"role": "user", "content": f"{prompt}\n\n---\nPaper content:\n{text[:30000]}"}]
        return self.chat(messages, max_tokens=max_tokens)

    def _file_to_base64(self, path: str) -> str:
        with open(path, "rb") as handle:
            return base64.standard_b64encode(handle.read()).decode("utf-8")

    def _url_to_base64(self, url: str) -> str:
        response = httpx.get(url, follow_redirects=True, timeout=60)
        response.raise_for_status()
        return base64.standard_b64encode(response.content).decode("utf-8")

    async def _url_to_base64_async(
        self,
        url: str,
        save_debug: bool = False,
        debug_dir: str = "debug_pdfs",
        max_pages: int = 10,
    ) -> Optional[str]:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=60)) as response:
                    if response.status != 200:
                        print(f"      PDF download failed: HTTP {response.status}")
                        return None
                    content = await response.read()
                    if not content.startswith(b"%PDF"):
                        print("      Downloaded content is not a valid PDF")
                        return None
                    if max_pages > 0:
                        try:
                            import fitz

                            doc = fitz.open(stream=content, filetype="pdf")
                            total_pages = len(doc)
                            if total_pages > max_pages:
                                new_doc = fitz.open()
                                new_doc.insert_pdf(doc, from_page=0, to_page=max_pages - 1)
                                content = new_doc.tobytes()
                                new_doc.close()
                                print(f"      Extracted first {max_pages} pages (total: {total_pages})")
                            else:
                                print(f"      PDF has {total_pages} pages (using all)")
                            doc.close()
                        except ImportError:
                            print("      PyMuPDF not available, using full PDF")
                        except Exception as exc:
                            print(f"      Failed to extract pages: {exc}, using full PDF")
                    if save_debug:
                        Path(debug_dir).mkdir(parents=True, exist_ok=True)
                        filename = url.split("/")[-1].split("?")[0] or "paper.pdf"
                        if not filename.endswith(".pdf"):
                            filename += ".pdf"
                        filepath = Path(debug_dir) / filename
                        with open(filepath, "wb") as handle:
                            handle.write(content)
                        print(f"      Debug PDF saved to {filepath} ({len(content)} bytes)")
                    pdf_base64 = base64.standard_b64encode(content).decode("utf-8")
                    print(f"      PDF processed: {len(content)} bytes -> base64 length: {len(pdf_base64)}")
                    return pdf_base64
        except Exception as exc:
            preview = str(url)[:50] if url is not None else "<none>"
            print(f"      PDF download failed for {preview}...: {exc}")
            return None

    def _extract_pdf_text_from_base64(self, pdf_base64: str) -> str:
        try:
            import fitz

            pdf_bytes = base64.b64decode(pdf_base64)
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            text = "\n".join(page.get_text() for page in doc)
            doc.close()
            return text
        except ImportError:
            return "[PDF text extraction unavailable - install pymupdf]"
        except Exception as exc:
            return f"[PDF extraction error: {exc}]"


def openai_client(api_key: str, model: str = "gpt-4o-mini") -> LLMClient:
    return LLMClient(api_key=api_key, base_url="https://api.openai.com/v1", model=model)


def claude_client(api_key: str, model: str = "claude-sonnet-4-20250514") -> LLMClient:
    return LLMClient(api_key=api_key, base_url="https://api.anthropic.com/v1", model=model)


def deepseek_client(api_key: str, model: str = "deepseek-chat") -> LLMClient:
    return LLMClient(api_key=api_key, base_url="https://api.deepseek.com/v1", model=model)


def gemini_client(api_key: str, model: str = "gemini-2.0-flash") -> LLMClient:
    return LLMClient(
        api_key=api_key,
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        model=model,
    )


def qwen_client(api_key: str, model: str = "qwen-turbo") -> LLMClient:
    return LLMClient(
        api_key=api_key,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        model=model,
    )


def local_client(base_url: str = "http://localhost:11434/v1", model: str = "llama3") -> LLMClient:
    return LLMClient(base_url=base_url, model=model)
