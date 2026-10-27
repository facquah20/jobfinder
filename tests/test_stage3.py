from __future__ import annotations

import asyncio
import json
import sys
from types import ModuleType

import pytest

from job_finder.adapters import ashby, greenhouse, lever, workday
from job_finder.adapters.base import FeedRequest
from job_finder.config import CrawlConfig
from job_finder.crawler import engine as engine_module
from job_finder.crawler.engine import CrawlEngine
from job_finder.discovery.company_discovery import discover_career_pages
from job_finder.discovery.search_sources import SearchResult
from job_finder.models import FetchResult


@pytest.mark.parametrize(
    ("adapter", "url", "payload", "expected_title"),
    [
        (
            greenhouse.GreenhouseAdapter(),
            "https://boards-api.greenhouse.io/v1/boards/acme/jobs",
            {"jobs": [{"id": 12, "title": "Backend Engineer",
                       "absolute_url": "https://boards.greenhouse.io/acme/jobs/12",
                       "location": {"name": "Remote"}}]},
            "Backend Engineer",
        ),
        (
            lever.LeverAdapter(),
            "https://api.lever.co/v0/postings/acme?mode=json",
            [{"id": "abc", "text": "Data Analyst",
              "hostedUrl": "https://jobs.lever.co/acme/abc",
              "categories": {"location": "London", "commitment": "Full-time"}}],
            "Data Analyst",
        ),
        (
            ashby.AshbyAdapter(),
            "https://api.ashbyhq.com/posting-api/job-board/acme",
            {"jobs": [{"id": "a1", "title": "Product Designer",
                       "jobUrl": "https://jobs.ashbyhq.com/acme/a1",
                       "isRemote": True}]},
            "Product Designer",
        ),
        (
            workday.WorkdayAdapter(),
            "https://acme.wd5.myworkdayjobs.com/wday/cxs/acme/External/jobs",
            {"jobPostings": [{"jobReqId": "JR1", "title": "Platform Engineer",
                              "externalPath": "/job/US/JR1",
                              "locationsText": "New York"}]},
            "Platform Engineer",
        ),
    ],
)
def test_provider_adapters_parse_public_json(adapter, url, payload, expected_title):
    assert adapter.can_handle(url, json.dumps(payload), "application/json")
    jobs = adapter.extract(url, json.dumps(payload))
    assert len(jobs) == 1
    assert jobs[0].title == expected_title


@pytest.mark.parametrize(
    ("adapter", "url", "expected_method", "feed_host"),
    [
        (
            greenhouse.GreenhouseAdapter(),
            "https://boards.greenhouse.io/acme",
            "GET",
            "boards-api.greenhouse.io",
        ),
        (
            lever.LeverAdapter(),
            "https://jobs.lever.co/acme",
            "GET",
            "api.lever.co",
        ),
        (
            ashby.AshbyAdapter(),
            "https://jobs.ashbyhq.com/acme",
            "GET",
            "api.ashbyhq.com",
        ),
        (
            workday.WorkdayAdapter(),
            "https://acme.wd5.myworkdayjobs.com/en-US/External",
            "POST",
            "acme.wd5.myworkdayjobs.com",
        ),
    ],
)
def test_provider_adapters_discover_feeds(adapter, url, expected_method, feed_host):
    requests = adapter.feed_requests(url, "")
    assert len(requests) == 1
    assert isinstance(requests[0], FeedRequest)
    assert requests[0].method == expected_method
    assert feed_host in requests[0].url
    if expected_method == "POST":
        assert requests[0].json_body == {
            "appliedFacets": {},
            "limit": 20,
            "offset": 0,
            "searchText": "",
        }


class FakeSearchSource:
    async def search(self, query: str) -> list[SearchResult]:
        assert query == '"Acme Corp" careers jobs'
        return [
            SearchResult("Acme Corp homepage", "https://acme.example/"),
            SearchResult("Careers at Acme Corp", "https://acme.example/careers"),
            SearchResult("Jobs at Acme", "https://jobs.lever.co/acme"),
            SearchResult("Careers", "javascript:void(0)"),
        ]


@pytest.mark.asyncio
async def test_company_discovery_ranks_career_pages():
    pages = await discover_career_pages(["Acme Corp"], FakeSearchSource())
    assert pages == {
        "Acme Corp": [
            "https://acme.example/careers",
            "https://jobs.lever.co/acme",
        ]
    }


@pytest.mark.asyncio
async def test_crawler_fetches_discovered_provider_feed(monkeypatch):
    engine = CrawlEngine(CrawlConfig(max_concurrency=1, per_host_delay_seconds=0))
    monkeypatch.setattr(engine_module, "is_safe_url", lambda url: (True, ""))

    class Robots:
        async def allowed(self, url: str) -> bool:
            return True

    engine.robots = Robots()
    calls: list[tuple[str, str]] = []

    async def fake_fetch(url, method="GET", json_body=None):
        calls.append((url, method))
        if "boards-api.greenhouse.io" in url:
            return FetchResult(
                url=url,
                status=200,
                content=json.dumps({
                    "jobs": [{
                        "id": 3,
                        "title": "Backend Engineer",
                        "absolute_url": "https://boards.greenhouse.io/acme/jobs/3",
                    }]
                }).encode(),
                content_type="application/json",
            )
        return FetchResult(
            url=url,
            status=200,
            content=b"<html><body><a href='https://boards.greenhouse.io/acme'>Jobs</a></body></html>",
            content_type="text/html",
        )

    monkeypatch.setattr(engine, "_fetch_with_retry", fake_fetch)
    jobs = await engine._bounded_fetch(asyncio.Semaphore(1), "https://acme.example/careers")

    assert len(jobs) == 1
    assert jobs[0].title == "Backend Engineer"
    assert jobs[0].source == "greenhouse"
    assert jobs[0].career_page_url == "https://boards.greenhouse.io/acme"
    assert calls == [
        ("https://acme.example/careers", "GET"),
        ("https://boards-api.greenhouse.io/v1/boards/acme/jobs?content=true", "GET"),
    ]


@pytest.mark.asyncio
async def test_playwright_render_fallback_checks_requests(monkeypatch):
    package = ModuleType("playwright")
    package.__path__ = []
    api = ModuleType("playwright.async_api")
    api.Error = RuntimeError
    api.TimeoutError = TimeoutError
    monkeypatch.setitem(sys.modules, "playwright", package)
    monkeypatch.setitem(sys.modules, "playwright.async_api", api)
    monkeypatch.setattr(engine_module, "is_safe_url", lambda url: (True, ""))

    class Robots:
        async def allowed(self, url: str) -> bool:
            return True

    class Request:
        url = "https://acme.example/careers"
        resource_type = "document"

    class Route:
        request = Request()

        async def continue_(self):
            self.continued = True

        async def abort(self):
            self.aborted = True

    route = Route()

    class Page:
        url = "https://acme.example/careers"

        async def goto(self, url: str, **kwargs):
            await context.guard(route)

        async def wait_for_load_state(self, state: str, timeout: int):
            return None

        async def content(self) -> str:
            return "<html><body>Rendered jobs</body></html>"

        async def close(self):
            return None

    class Context:
        async def route(self, pattern: str, handler):
            self.guard = handler

        async def new_page(self):
            return Page()

        async def close(self):
            return None

    class Browser:
        async def new_context(self, **kwargs):
            return context

    context = Context()
    engine = CrawlEngine(CrawlConfig(playwright_fallback=True, per_host_delay_seconds=0))
    engine.browser = Browser()
    engine.robots = Robots()

    rendered = await engine._render_page("https://acme.example/careers")

    assert rendered == "<html><body>Rendered jobs</body></html>"
    assert route.continued
    assert engine.stats.pages_fetched == 1
