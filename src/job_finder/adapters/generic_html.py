"""Heuristic fallback for pages with no structured data.

Deliberately conservative: only emits a job when the page's title/headline
and URL suggest a vacancy. Marked source='generic_html' so downstream can
treat these as lower confidence.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from job_finder.adapters.base import FeedRequest, register
from job_finder.crawler.url_utils import resolve_relative
from job_finder.models import RawJob

_JOB_URL_HINTS = re.compile(
    r"/(job|jobs|careers?/[^/]+|positions?|openings?|vacanc(?:y|ies))/", re.I
)
_JOB_TITLE_HINTS = re.compile(
    r"\b(engineer|developer|analyst|manager|designer|scientist|"
    r"assistant|associate|specialist|coordinator|technician|"
    r"consultant|director|lead|intern)\b",
    re.I,
)


class GenericHtmlAdapter:
    name = "generic_html"
    priority = 90

    def can_handle(self, url: str, html: str, content_type: str) -> bool:
        return "html" in content_type.lower()

    def feed_requests(self, url: str, html: str) -> list[FeedRequest]:
        return []

    def extract(self, url: str, html: str) -> list[RawJob]:
        soup = BeautifulSoup(html, "lxml")
        headline = soup.find("h1")
        title = headline.get_text(" ", strip=True) if headline else ""
        if not title:
            title_tag = soup.find("title")
            title = title_tag.get_text(" ", strip=True) if title_tag else ""
        if not title:
            return []
        # Require URL OR title to signal a job page.
        if not (_JOB_URL_HINTS.search(url) or _JOB_TITLE_HINTS.search(title)):
            return []
        # Require the page to contain a plausible "apply" affordance.
        page_text = soup.get_text(" ", strip=True).lower()
        if "apply" not in page_text and "job description" not in page_text:
            return []
        description = ""
        main = soup.find("main") or soup.find("article") or soup.body
        if main:
            description = main.get_text(" ", strip=True)[:20_000]
        company = None
        og = soup.find("meta", property="og:site_name")
        if og and og.get("content"):
            company = str(og["content"])
        return [RawJob(
            title=title,
            url=resolve_relative(url, url),
            source=self.name,
            company=company,
            description_html=description,
            raw={"heuristic": True},
        )]


register(GenericHtmlAdapter())