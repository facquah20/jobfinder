"""Async crawl engine: bounded concurrency, retries, robots, persistence."""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Iterable

import aiohttp
from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from job_finder.adapters.base import get_adapters
from job_finder.config import CrawlConfig
from job_finder.crawler.robots import RobotsCache
from job_finder.crawler.url_utils import is_safe_url
from job_finder.models import (
    CrawlStats,
    FetchResult,
    JobPosting,
    RawJob,
)

log = logging.getLogger(__name__)


class CrawlEngine:
    def __init__(self, config: CrawlConfig) -> None:
        self.config = config
        self.stats = CrawlStats()
        self._host_semaphores: dict[str, asyncio.Semaphore] = defaultdict(
            lambda: asyncio.Semaphore(config.per_host_concurrency)
        )
        self._host_delay_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._host_last_fetch: dict[str, float] = {}

    async def crawl(self, seed_urls: Iterable[str]) -> list[JobPosting]:
        connector = aiohttp.TCPConnector(limit=self.config.max_concurrency)
        headers = {"User-Agent": self.config.user_agent}
        timeout = aiohttp.ClientTimeout(total=self.config.request_timeout_seconds)
        async with aiohttp.ClientSession(
            connector=connector, headers=headers, timeout=timeout,
        ) as session:
            self.robots = RobotsCache(session, self.config.user_agent)
            self.session = session
            semaphore = asyncio.Semaphore(self.config.max_concurrency)
            tasks = [self._bounded_fetch(semaphore, url) for url in seed_urls]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            jobs: list[JobPosting] = []
            for res in results:
                if isinstance(res, Exception):
                    log.warning("crawl task failed: %s", res)
                    continue
                jobs.extend(res)
            return jobs

    async def _bounded_fetch(
        self, sem: asyncio.Semaphore, url: str
    ) -> list[JobPosting]:
        async with sem:
            if self.stats.pages_fetched >= self.config.max_total_pages:
                return []
            ok, reason = is_safe_url(url)
            if not ok:
                self._record_failure(url, f"unsafe: {reason}")
                return []
            if self.config.respect_robots and not await self.robots.allowed(url):
                self.stats.pages_skipped_robots += 1
                log.info("robots disallow: %s", url)
                return []
            result = await self._fetch_with_retry(url)
            if result.error or result.content is None:
                self._record_failure(url, result.error or "no content")
                return []
            self.stats.pages_fetched += 1
            html = result.content.decode("utf-8", errors="replace")
            return self._extract(result.final_url or url, html)

    async def _fetch_with_retry(self, url: str) -> FetchResult:
        from urllib.parse import urlparse
        host = urlparse(url).netloc
        async with self._host_semaphores[host]:
            await self._respect_host_delay(host)
            try:
                async for attempt in AsyncRetrying(
                    stop=stop_after_attempt(self.config.max_retries),
                    wait=wait_exponential_jitter(initial=1, max=10),
                    retry=retry_if_exception_type(
                        (aiohttp.ClientError, asyncio.TimeoutError)
                    ),
                    reraise=True,
                ):
                    with attempt:
                        return await self._fetch_once(url)
            except (RetryError, aiohttp.ClientError, asyncio.TimeoutError) as exc:
                return FetchResult(url=url, status=0, error=f"{type(exc).__name__}: {exc}")

    async def _respect_host_delay(self, host: str) -> None:
        loop = asyncio.get_event_loop()
        async with self._host_delay_locks[host]:
            last = self._host_last_fetch.get(host, 0.0)
            now = loop.time()
            wait = self.config.per_host_delay_seconds - (now - last)
            if wait > 0:
                await asyncio.sleep(wait)
            self._host_last_fetch[host] = loop.time()

    async def _fetch_once(self, url: str) -> FetchResult:
        assert self.session is not None
        async with self.session.get(url, allow_redirects=True, max_redirects=5) as resp:
            final = str(resp.url)
            if final != url:
                ok, reason = is_safe_url(final)
                if not ok:
                    return FetchResult(url=url, status=resp.status,
                                       error=f"redirect unsafe: {reason}")
            ctype = resp.headers.get("Content-Type", "")
            if "html" not in ctype and "json" not in ctype:
                return FetchResult(url=url, status=resp.status,
                                   error=f"content-type {ctype!r}")
            if resp.status >= 400:
                return FetchResult(url=url, status=resp.status,
                                   error=f"http {resp.status}")
            if resp.content_length and resp.content_length > self.config.max_response_bytes:
                return FetchResult(url=url, status=resp.status,
                                   error="response too large")
            body = await resp.read()
            if len(body) > self.config.max_response_bytes:
                return FetchResult(url=url, status=resp.status,
                                   error="response too large (streamed)")
            return FetchResult(url=url, status=resp.status, content=body, final_url=final)

    def _extract(self, url: str, html: str) -> list[JobPosting]:
        for adapter in get_adapters():
            if not adapter.can_handle(url, html, "text/html"):
                continue
            try:
                raws: list[RawJob] = adapter.extract(url, html)
            except Exception as exc:  # adapter bugs must not kill the run
                log.warning("adapter %s failed on %s: %s", adapter.name, url, exc)
                continue
            if not raws:
                continue
            self.stats.jobs_extracted += len(raws)
            return [JobPosting.from_raw(r, career_page_url=url) for r in raws]
        return []

    def _record_failure(self, url: str, reason: str) -> None:
        self.stats.pages_failed += 1
        self.stats.failures.append({"url": url, "reason": reason})
        log.warning("fetch failed: %s — %s", url, reason)