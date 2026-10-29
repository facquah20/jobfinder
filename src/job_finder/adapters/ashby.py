"""Ashby public job-board feed adapter."""

from __future__ import annotations

import json
from urllib.parse import quote, urlparse

from job_finder.adapters._provider_utils import first_text, json_items, provider_urls
from job_finder.adapters.base import FeedRequest, register
from job_finder.crawler.url_utils import resolve_relative
from job_finder.models import RawJob

_DOMAINS = ("ashbyhq.com",)


class AshbyAdapter:
    name = "ashby"
    priority = 22

    def can_handle(self, url: str, html: str, content_type: str) -> bool:
        parsed = urlparse(url)
        return (
            (parsed.hostname or "").lower() == "api.ashbyhq.com"
            and "/posting-api/job-board/" in parsed.path
            and "json" in content_type.lower()
        )

    def feed_requests(self, url: str, html: str) -> list[FeedRequest]:
        requests: list[FeedRequest] = []
        seen: set[str] = set()
        for board_url in provider_urls(url, html, _DOMAINS):
            parsed = urlparse(board_url)
            host = (parsed.hostname or "").lower()
            if host == "api.ashbyhq.com":
                continue
            parts = [part for part in parsed.path.split("/") if part]
            if not parts:
                continue
            board = quote(parts[0], safe="")
            feed = f"https://api.ashbyhq.com/posting-api/job-board/{board}"
            if feed not in seen:
                seen.add(feed)
                requests.append(FeedRequest(feed, career_page_url=board_url))
        return requests

    def extract(self, url: str, html: str) -> list[RawJob]:
        try:
            data = json.loads(html)
        except json.JSONDecodeError:
            return []
        jobs: list[RawJob] = []
        for item in json_items(data, "jobs"):
            title = first_text(item.get("title"))
            target = first_text(item.get("jobUrl"), item.get("applyUrl"), item.get("url"))
            if not title or not target:
                continue
            location = first_text(item.get("location"))
            if item.get("isRemote") is True and not location:
                location = "Remote"
            jobs.append(RawJob(
                title=title,
                url=resolve_relative(url, target),
                source=self.name,
                location=location,
                description_html=first_text(item.get("descriptionHtml"), item.get("description")),
                employment_type=first_text(item.get("employmentType")),
                posting_date=first_text(item.get("publishedAt")),
                identifier=first_text(item.get("id")),
                raw={"provider": self.name, "department": item.get("department")},
            ))
        return jobs


register(AshbyAdapter())
