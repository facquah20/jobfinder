"""End-to-end crawl test against a local aiohttp server."""

from __future__ import annotations

import pytest
from aiohttp import web

from job_finder.config import CrawlConfig
from job_finder.crawler.engine import CrawlEngine

FIXTURE = None


def _read_fixture() -> str:
    from pathlib import Path
    global FIXTURE
    if FIXTURE is None:
        FIXTURE = (Path(__file__).parent / "fixtures" / "schema_org_job.html").read_text()
    return FIXTURE


async def _start_server():
    async def careers(request):
        return web.Response(text=_read_fixture(), content_type="text/html")

    async def robots(request):
        return web.Response(text="User-agent: *\nAllow: /\n", content_type="text/plain")

    app = web.Application()
    app.router.add_get("/careers", careers)
    app.router.add_get("/robots.txt", robots)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    return runner, f"http://127.0.0.1:{port}"


@pytest.mark.asyncio
async def test_crawl_local_server():
    runner, base = await _start_server()
    try:
        cfg = CrawlConfig(per_host_delay_seconds=0.0, request_timeout_seconds=5.0)
        engine = CrawlEngine(cfg)
        # SSRF guard blocks loopback; bypass only for this test.
        import job_finder.crawler.url_utils as uu
        orig = uu.is_safe_url
        uu.is_safe_url = lambda url: (True, "")
        try:
            jobs = await engine.crawl([f"{base}/careers"])
        finally:
            uu.is_safe_url = orig
        assert len(jobs) == 1
        assert jobs[0].title == "Senior Backend Engineer"
        assert engine.stats.pages_fetched == 1
    finally:
        await runner.cleanup()