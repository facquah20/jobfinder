"""Workday CXS public jobs API adapter."""

from __future__ import annotations

import json
from urllib.parse import quote, urlparse

from job_finder.adapters._provider_utils import first_text, json_items, provider_urls
from job_finder.adapters.base import FeedRequest, register
from job_finder.crawler.url_utils import resolve_relative
from job_finder.models import RawJob

_DOMAIN = "myworkdayjobs.com"


class WorkdayAdapter:
    name = "workday"
    priority = 23

    def can_handle(self, url: str, html: str, content_type: str) -> bool:
        parsed = urlparse(url)
        return (
            "/wday/cxs/" in parsed.path
            and parsed.path.endswith("/jobs")
            and "json" in content_type.lower()
        )

    def feed_requests(self, url: str, html: str) -> list[FeedRequest]:
        requests: list[FeedRequest] = []
        seen: set[str] = set()
        for careers_url in provider_urls(url, html, (_DOMAIN,)):
            parsed = urlparse(careers_url)
            host = (parsed.hostname or "").lower()
            if host == "api.workday.com" or "/wday/cxs/" in parsed.path:
                continue
            tenant = host.removesuffix(f".{_DOMAIN}").split(".")[0]
            if not tenant:
                continue
            parts = [part for part in parsed.path.split("/") if part]
            if not parts:
                continue
            site = parts[1] if parts[0].lower().startswith(("en-", "fr-", "de-", "es-")) and len(parts) > 1 else parts[0]
            endpoint = f"{parsed.scheme}://{parsed.netloc}/wday/cxs/{quote(tenant)}/{quote(site)}/jobs"
            if endpoint not in seen:
                seen.add(endpoint)
                requests.append(FeedRequest(
                    endpoint,
                    method="POST",
                    json_body={"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": ""},
                    career_page_url=careers_url,
                ))
        return requests

    def extract(self, url: str, html: str) -> list[RawJob]:
        try:
            data = json.loads(html)
        except json.JSONDecodeError:
            return []
        jobs: list[RawJob] = []
        for item in json_items(data, "jobPostings"):
            title = first_text(item.get("title"))
            path = first_text(item.get("externalPath"), item.get("url"))
            if not title or not path:
                continue
            jobs.append(RawJob(
                title=title,
                url=resolve_relative(url, path),
                source=self.name,
                location=first_text(item.get("locationsText"), item.get("location")),
                description_html=first_text(item.get("jobDescription"), item.get("description")),
                posting_date=first_text(item.get("postedOn"), item.get("postedDate")),
                identifier=first_text(item.get("jobReqId"), item.get("id")),
                raw={"provider": self.name, "bullet_fields": item.get("bulletFields")},
            ))
        return jobs


register(WorkdayAdapter())
