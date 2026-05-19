import requests
import aiohttp
import asyncio
import base64
import logging
import os
import sys
import time
from typing import List, Dict, Any
from contextlib import asynccontextmanager

import fitz  # PyMuPDF
from langchain_core.documents import Document
from open_webui.env import GLOBAL_LOG_LEVEL

logging.basicConfig(stream=sys.stdout, level=GLOBAL_LOG_LEVEL)
log = logging.getLogger(__name__)

OCR_PROMPT = (
    "Extract and return all text content from this document image. "
    "Preserve the original structure and formatting as much as possible."
)


class OlmOCRLoader:
    """
    OlmOCR loader that uses an Ollama-hosted vision model to extract text from PDFs.

    Renders each PDF page to an image with PyMuPDF, then sends the base64-encoded
    image to the Ollama /api/chat endpoint for text extraction.

    Provides both sync and async support following the MistralLoader pattern.
    """

    def __init__(
        self,
        base_url: str,
        model: str,
        file_path: str,
        timeout: int = 120,
        max_retries: int = 3,
    ):
        if not base_url:
            raise ValueError("Ollama base URL cannot be empty.")
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found at {file_path}")

        self.base_url = base_url.rstrip("/")
        self.model = model or "richardyoung/olmocr2:7b-q8"
        self.file_path = file_path
        self.timeout = timeout
        self.max_retries = max_retries

        self.file_name = os.path.basename(file_path)
        self.file_size = os.path.getsize(file_path)

    # ------------------------------------------------------------------ #
    #  PDF rendering
    # ------------------------------------------------------------------ #

    def _render_pages_to_base64(self) -> List[str]:
        """Render each PDF page to a PNG image and return as base64 strings."""
        images: List[str] = []
        doc = fitz.open(self.file_path)
        try:
            for page in doc:
                # 300 DPI: matrix scale factor = 300/72 ~ 4.17
                mat = fitz.Matrix(300 / 72, 300 / 72)
                pix = page.get_pixmap(matrix=mat)
                png_bytes = pix.tobytes("png")
                images.append(base64.b64encode(png_bytes).decode("utf-8"))
        finally:
            doc.close()

        log.debug(f"Rendered {len(images)} pages from {self.file_name}")
        return images

    # ------------------------------------------------------------------ #
    #  Retry helpers
    # ------------------------------------------------------------------ #

    def _is_retryable_error(self, error: Exception) -> bool:
        if isinstance(error, (requests.exceptions.ConnectionError, requests.exceptions.Timeout)):
            return True
        if isinstance(error, requests.exceptions.HTTPError):
            if hasattr(error, "response") and error.response is not None:
                return error.response.status_code >= 500 or error.response.status_code == 429
            return False
        if isinstance(error, (aiohttp.ClientConnectionError, aiohttp.ServerTimeoutError)):
            return True
        if isinstance(error, aiohttp.ClientResponseError):
            return error.status >= 500 or error.status == 429
        return False

    def _retry_sync(self, fn, *args, **kwargs):
        for attempt in range(self.max_retries):
            try:
                return fn(*args, **kwargs)
            except Exception as e:
                if attempt == self.max_retries - 1 or not self._is_retryable_error(e):
                    raise
                wait = min((2 ** attempt) + 0.5, 30)
                log.warning(
                    f"Retryable error (attempt {attempt + 1}/{self.max_retries}): {e}. "
                    f"Retrying in {wait}s..."
                )
                time.sleep(wait)

    async def _retry_async(self, fn, *args, **kwargs):
        for attempt in range(self.max_retries):
            try:
                return await fn(*args, **kwargs)
            except Exception as e:
                if attempt == self.max_retries - 1 or not self._is_retryable_error(e):
                    raise
                wait = min((2 ** attempt) + 0.5, 30)
                log.warning(
                    f"Retryable error (attempt {attempt + 1}/{self.max_retries}): {e}. "
                    f"Retrying in {wait}s..."
                )
                await asyncio.sleep(wait)

    # ------------------------------------------------------------------ #
    #  Ollama API calls
    # ------------------------------------------------------------------ #

    def _ocr_page_sync(self, image_b64: str, page_index: int) -> str:
        """Send a single page image to Ollama for OCR (sync)."""
        url = f"{self.base_url}/api/chat"
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": OCR_PROMPT,
                    "images": [image_b64],
                }
            ],
            "stream": False,
        }

        def request_fn():
            response = requests.post(url, json=payload, timeout=self.timeout)
            response.raise_for_status()
            return response.json()

        result = self._retry_sync(request_fn)
        content = result.get("message", {}).get("content", "")
        log.debug(f"OCR completed for page {page_index + 1} of {self.file_name}")
        return content

    async def _ocr_page_async(
        self, session: aiohttp.ClientSession, image_b64: str, page_index: int
    ) -> str:
        """Send a single page image to Ollama for OCR (async)."""
        url = f"{self.base_url}/api/chat"
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": OCR_PROMPT,
                    "images": [image_b64],
                }
            ],
            "stream": False,
        }

        async def request_fn():
            async with session.post(
                url,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=self.timeout),
            ) as response:
                response.raise_for_status()
                data = await response.json()
                return data

        result = await self._retry_async(request_fn)
        content = result.get("message", {}).get("content", "")
        log.debug(f"OCR completed for page {page_index + 1} of {self.file_name}")
        return content

    # ------------------------------------------------------------------ #
    #  Result processing
    # ------------------------------------------------------------------ #

    def _build_documents(self, pages_text: List[str]) -> List[Document]:
        """Convert page text results into Document objects."""
        documents: List[Document] = []
        total_pages = len(pages_text)

        for idx, text in enumerate(pages_text):
            cleaned = text.strip() if isinstance(text, str) else str(text).strip()
            if not cleaned:
                log.debug(f"Skipping empty page {idx + 1}")
                continue

            documents.append(
                Document(
                    page_content=cleaned,
                    metadata={
                        "page": idx,
                        "page_label": idx + 1,
                        "total_pages": total_pages,
                        "file_name": self.file_name,
                        "file_size": self.file_size,
                        "processing_engine": "olm-ocr",
                        "model": self.model,
                        "content_length": len(cleaned),
                    },
                )
            )

        if not documents:
            log.warning("No text content extracted from any page.")
            return [
                Document(
                    page_content="No text content found",
                    metadata={
                        "error": "no_content",
                        "file_name": self.file_name,
                        "total_pages": total_pages,
                    },
                )
            ]

        return documents

    # ------------------------------------------------------------------ #
    #  Public interface
    # ------------------------------------------------------------------ #

    def load(self) -> List[Document]:
        """Synchronous OCR workflow: render pages, OCR each, return Documents."""
        start_time = time.time()
        try:
            images = self._render_pages_to_base64()
            pages_text: List[str] = []
            for idx, img_b64 in enumerate(images):
                text = self._ocr_page_sync(img_b64, idx)
                pages_text.append(text)

            documents = self._build_documents(pages_text)

            total_time = time.time() - start_time
            log.debug(
                f"OlmOCR sync workflow completed in {total_time:.2f}s, "
                f"produced {len(documents)} documents from {self.file_name}"
            )
            return documents

        except Exception as e:
            total_time = time.time() - start_time
            log.error(f"OlmOCR sync workflow failed after {total_time:.2f}s: {e}")
            return [
                Document(
                    page_content=f"Error during OCR processing: {e}",
                    metadata={
                        "error": "processing_failed",
                        "file_name": self.file_name,
                    },
                )
            ]

    async def load_async(self) -> List[Document]:
        """Asynchronous OCR workflow with connection pooling."""
        start_time = time.time()
        try:
            images = self._render_pages_to_base64()

            connector = aiohttp.TCPConnector(
                limit=5,
                limit_per_host=5,
                keepalive_timeout=60,
                enable_cleanup_closed=True,
            )
            timeout = aiohttp.ClientTimeout(total=self.timeout * len(images))

            async with aiohttp.ClientSession(
                connector=connector,
                timeout=timeout,
                raise_for_status=False,
            ) as session:
                pages_text: List[str] = []
                for idx, img_b64 in enumerate(images):
                    text = await self._ocr_page_async(session, img_b64, idx)
                    pages_text.append(text)

            documents = self._build_documents(pages_text)

            total_time = time.time() - start_time
            log.debug(
                f"OlmOCR async workflow completed in {total_time:.2f}s, "
                f"produced {len(documents)} documents from {self.file_name}"
            )
            return documents

        except Exception as e:
            total_time = time.time() - start_time
            log.error(f"OlmOCR async workflow failed after {total_time:.2f}s: {e}")
            return [
                Document(
                    page_content=f"Error during OCR processing: {e}",
                    metadata={
                        "error": "processing_failed",
                        "file_name": self.file_name,
                    },
                )
            ]
