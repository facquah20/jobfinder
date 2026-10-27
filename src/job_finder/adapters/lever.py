"""Lever public postings API adapter."""

from __future__ import annotations

import json
from urllib.parse import quote, urlparse

from job_finder.adapters._provider_utils import first_text, json_items, provider_urls
from job_finder.adapters.base import FeedRequest, register
from job_finder.crawler.url_utils import resolve_relative
from job_finder.models import RawJob

_DOMAINS = ("lever.co",)


class LeverAdapter:
    name = "lever"
    priority = 21

    def can_handle(self, url: str, html: str, content_type: str) -> bool:
        parsed = urlparse(url)
        return (
            (parsed.hostname or "").lower() == "api.lever.co"
            and parsed.path.startswith("/v0/postings/")
            and "json" in content_type.lower()
        )

    def feed_requests(self, url: str, html: str) -> list[FeedRequest]:
        requests: list[FeedRequest] = []
        seen: set[str] = set()
        for board_url in provider_urls(url, html, _DOMAINS):
            parsed = urlparse(board_url)
            host = (parsed.hostname or "").lower()
            if host == "api.lever.co":
                continue
            parts = [part for part in parsed.path.split("/") if part]
            if not parts:
                continue
            site = quote(parts[0], safe="")
            feed = f"https://api.lever.co/v0/postings/{site}?mode=json"
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
        for item in json_items(data):
            title = first_text(item.get("text"), item.get("title"))
            target = first_text(item.get("hostedUrl"), item.get("applyUrl"), item.get("url"))
            if not title or not target:
                continue
            categories = item.get("categories")
            categories = categories if isinstance(categories, dict) else {}
            location = first_text(categories.get("location"), categories.get("allLocations"))
            employment = first_text(categories.get("commitment"))
            jobs.append(RawJob(
                title=title,
                url=resolve_relative(url, target),
                source=self.name,
                location=location,
                description_html=first_text(item.get("description"), item.get("descriptionPlain")),
                employment_type=employment,
                posting_date=first_text(item.get("createdAt")),
                identifier=first_text(item.get("id")),
                raw={"provider": self.name, "team": categories.get("team")},
            ))
        return jobs


register(LeverAdapter())
