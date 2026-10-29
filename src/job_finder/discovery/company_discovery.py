"""Find likely career pages through a configured search source."""

from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

from job_finder.discovery.search_sources import SearchResult, SearchSource

log = logging.getLogger(__name__)

_CAREER_HINTS = (
    "career", "careers", "jobs", "job-openings", "job openings",
    "open-positions", "open positions", "work-with-us", "work with us",
    "greenhouse", "lever.co", "ashbyhq", "myworkdayjobs",
)


def _candidate_score(company: str, result: SearchResult) -> int:
    parsed = urlparse(result.url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return 0
    haystack = " ".join((parsed.hostname, parsed.path, result.title, result.snippet)).lower()
    if not any(hint in haystack for hint in _CAREER_HINTS):
        return 0
    company_words = [
        word for word in re.findall(r"[a-z0-9]+", company.lower())
        if len(word) > 2
    ]
    score = 1
    if any(word in " ".join((parsed.hostname, parsed.path, result.title)).lower()
           for word in company_words):
        score += 2
    if any(hint in f"{parsed.hostname}{parsed.path}".lower()
           for hint in ("career", "jobs", "greenhouse", "lever.co", "ashbyhq", "myworkdayjobs")):
        score += 2
    return score


async def discover_career_pages(
    companies: list[str],
    search_source: SearchSource,
    *,
    results_per_company: int = 3,
) -> dict[str, list[str]]:
    """Search and rank likely career URLs for each company name."""
    discovered: dict[str, list[str]] = {}
    for company in companies:
        company = company.strip()
        if not company:
            continue
        results = await search_source.search(f'"{company}" careers jobs')
        ranked = sorted(
            (
                (_candidate_score(company, result), index, result)
                for index, result in enumerate(results)
            ),
            key=lambda item: (-item[0], item[1]),
        )
        urls: list[str] = []
        for score, _, result in ranked:
            if score <= 0 or result.url in urls:
                continue
            urls.append(result.url)
            if len(urls) >= results_per_company:
                break
        discovered[company] = urls
        if not urls:
            log.info("no likely careers page found for %s", company)
    return discovered
