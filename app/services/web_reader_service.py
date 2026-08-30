"""Free local webpage reader used by legacy scrape/watchlist flows."""
from __future__ import annotations

import logging
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup
from app.plugins.utils import validate_public_url

logger = logging.getLogger("J.A.R.V.I.S")


@dataclass
class WebReadResult:
    success: bool
    source: str = "direct_web"
    data: list | None = None
    text: str = ""
    healed: bool = False
    error: str | None = None


class WebReaderService:
    def scrape_with_self_healing(self, url: str) -> WebReadResult:
        """Compatibility method for existing flows; performs one transparent HTTP read."""
        try:
            validate_public_url(url)
            response = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0 EdithAssistant/1.0"}, allow_redirects=True)
            response.raise_for_status()
            validate_public_url(response.url)
            if len(response.content) > 5_000_000:
                raise ValueError("Page exceeds the 5 MB limit")
            soup = BeautifulSoup(response.text, "html.parser")
            for node in soup(["script", "style", "noscript", "svg"]): node.decompose()
            text = "\n".join(line for line in (part.strip() for part in soup.get_text("\n").splitlines()) if line)
            return WebReadResult(True, text=text[:100_000])
        except Exception as exc:
            logger.warning("[WEB READER] %s", exc)
            return WebReadResult(False, error=str(exc))


_service = WebReaderService()


def get_web_reader_service() -> WebReaderService:
    return _service
