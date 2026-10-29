"""Async crawl engine: bounded concurrency, retries, robots, and adapters."""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Iterable
from urllib.parse import urlparse

import aiohttp
from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from job_finder.adapters.base import FeedRequest, get_adapters
from job_finder.config import CrawlConfig
from job_finder.crawler.robots import RobotsCache
from job_finder.crawler.url_utils import is_safe_url
from job_finder.models import (
    CrawlStats,
    FetchResult,
    JobPosting,
    RawJob,
    canonicalize_url,
)

log = logging.getLogger(__name__)


class PlaywrightSetupError(RuntimeError):
    """Raised when the requested optional browser runtime is unavailable."""


class CrawlEngine:
    def __init__(self, config: CrawlConfig) -> None:
        self.config = config
        self.stats = CrawlStats()
        self._host_semaphores: dict[str, asyncio.Semaphore] = defaultdict(
            lambda: asyncio.Semaphore(config.per_host_concurrency)
        )
        self._host_delay_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._host_last_fetch: dict[str, float] = {}
        self._seen_requests: set[tuple[str, str]] = set()
        self._seen_lock = asyncio.Lock()
        self._pages_started = 0
        self._pages_lock = asyncio.Lock()
        self.browser = None
        self._playwright = None

    async def crawl(self, seed_urls: Iterable[str]) -> list[JobPosting]:
        if not isinstance(self.config.user_agent, str):
            raise TypeError(
                f"user_agent must be a string, got {type(self.config.user_agent).__name__}"
            )

        playwright_manager = None
        try:
            if self.config.playwright_fallback:
                try:
                    from playwright.async_api import async_playwright
                except ImportError as exc:
                    raise PlaywrightSetupError(
                        "Playwright fallback is enabled but Playwright is not installed; "
                        "install jobfinder[browser] and run `playwright install chromium`"
                    ) from exc
                playwright_manager = async_playwright()
                self._playwright = await playwright_manager.start()
                try:
                    self.browser = await self._playwright.chromium.launch()
                except Exception as exc:
                    raise PlaywrightSetupError(
                        "Could not launch Playwright Chromium; run `playwright install chromium`"
                    ) from exc

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
                for result in results:
                    if isinstance(result, Exception):
                        log.warning("crawl task failed: %s", result)
                        continue
                    jobs.extend(result)
                return jobs
        finally:
            if self.browser is not None:
                await self.browser.close()
                self.browser = None
            if self._playwright is not None:
                await self._playwright.stop()
                self._playwright = None

    async def _bounded_fetch(
        self,
        sem: asyncio.Semaphore,
        url: str,
        *,
        method: str = "GET",
        json_body: dict[str, object] | None = None,
        expand_providers: bool = True,
        career_page_url: str | None = None,
    ) -> list[JobPosting]:
        request_key = (method.upper(), canonicalize_url(url))
        async with self._seen_lock:
            if request_key in self._seen_requests:
                return []
            self._seen_requests.add(request_key)

        async with sem:
            ok, reason = is_safe_url(url)
            if not ok:
                self._record_failure(url, f"unsafe: {reason}")
                return []
            if self.config.respect_robots and not await self.robots.allowed(url):
                self.stats.pages_skipped_robots += 1
                log.info("robots disallow: %s", url)
                return []

            async with self._pages_lock:
                if self._pages_started >= self.config.max_total_pages:
                    return []
                self._pages_started += 1

            result = await self._fetch_with_retry(url, method, json_body)
            if result.error or result.content is None:
                self._record_failure(url, result.error or "no content")
                return []
            self.stats.pages_fetched += 1
            page_url = result.final_url or url
            html = result.content.decode("utf-8", errors="replace")
            jobs = self._extract(
                page_url, html, result.content_type or "", career_page_url,
            )
            if not jobs and self.config.playwright_fallback and "html" in (result.content_type or "").lower():
                rendered = await self._render_page(page_url)
                if rendered is not None:
                    html = rendered
                    jobs = self._extract(
                        page_url, html, "text/html", career_page_url,
                    )

            if jobs:
                self.stats.jobs_extracted += len(jobs)

            feed_requests = (
                self._feed_requests(page_url, html) if expand_providers else []
            )

        if feed_requests:
            feed_results = await asyncio.gather(*(
                self._bounded_fetch(
                    sem,
                    feed.url,
                    method=feed.method,
                    json_body=feed.json_body,
                    expand_providers=False,
                    career_page_url=feed.career_page_url,
                )
                for feed in feed_requests
            ), return_exceptions=True)
            for result in feed_results:
                if isinstance(result, Exception):
                    log.warning("provider feed task failed: %s", result)
                    continue
                jobs.extend(result)
        return jobs

    async def _fetch_with_retry(
        self,
        url: str,
        method: str = "GET",
        json_body: dict[str, object] | None = None,
    ) -> FetchResult:
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
                        return await self._fetch_once(url, method, json_body)
            except (RetryError, aiohttp.ClientError, asyncio.TimeoutError) as exc:
                return FetchResult(url=url, status=0, error=f"{type(exc).__name__}: {exc}")

    async def _respect_host_delay(self, host: str) -> None:
        loop = asyncio.get_running_loop()
        async with self._host_delay_locks[host]:
            last = self._host_last_fetch.get(host, 0.0)
            wait = self.config.per_host_delay_seconds - (loop.time() - last)
            if wait > 0:
                await asyncio.sleep(wait)
            self._host_last_fetch[host] = loop.time()

    async def _fetch_once(
        self,
        url: str,
        method: str = "GET",
        json_body: dict[str, object] | None = None,
    ) -> FetchResult:
        async with self.session.request(
            method, url, json=json_body, allow_redirects=True, max_redirects=5,
        ) as response:
            final = str(response.url)
            if final != url:
                ok, reason = is_safe_url(final)
                if not ok:
                    return FetchResult(
                        url=url,
                        status=response.status,
                        error=f"redirect unsafe: {reason}",
                    )
            content_type = response.headers.get("Content-Type", "")
            if "html" not in content_type.lower() and "json" not in content_type.lower():
                return FetchResult(
                    url=url,
                    status=response.status,
                    error=f"content-type {content_type!r}",
                )
            if response.status >= 400:
                return FetchResult(url=url, status=response.status, error=f"http {response.status}")
            if response.content_length and response.content_length > self.config.max_response_bytes:
                return FetchResult(url=url, status=response.status, error="response too large")
            body = await response.read()
            if len(body) > self.config.max_response_bytes:
                return FetchResult(
                    url=url,
                    status=response.status,
                    error="response too large (streamed)",
                )
            return FetchResult(
                url=url,
                status=response.status,
                content=body,
                final_url=final,
                content_type=content_type,
            )

    def _extract(
        self,
        url: str,
        html: str,
        content_type: str,
        career_page_url: str | None = None,
    ) -> list[JobPosting]:
        for adapter in get_adapters():
            if not adapter.can_handle(url, html, content_type):
                continue
            try:
                raws: list[RawJob] = adapter.extract(url, html)
            except Exception as exc:  # adapter bugs must not kill the run
                log.warning("adapter %s failed on %s: %s", adapter.name, url, exc)
                continue
            if not raws:
                continue
            return [
                JobPosting.from_raw(raw, career_page_url=career_page_url or url)
                for raw in raws
            ]
        return []

    def _feed_requests(self, url: str, html: str) -> list[FeedRequest]:
        requests: list[FeedRequest] = []
        seen: set[tuple[str, str]] = set()
        for adapter in get_adapters():
            try:
                candidates = adapter.feed_requests(url, html)
            except Exception as exc:  # provider discovery must not kill the page
                log.warning("adapter %s feed discovery failed on %s: %s", adapter.name, url, exc)
                continue
            for request in candidates:
                key = (request.method.upper(), canonicalize_url(request.url))
                if key not in seen:
                    seen.add(key)
                    requests.append(request)
        return requests

    async def _render_page(self, url: str) -> str | None:
        from playwright.async_api import Error as PlaywrightError
        from playwright.async_api import TimeoutError as PlaywrightTimeoutError

        context = await self.browser.new_context(service_workers="block")

        async def guard_request(route) -> None:
            request = route.request
            if request.resource_type in {"image", "font", "media", "websocket"}:
                await route.abort()
                return
            safe, _ = await asyncio.to_thread(is_safe_url, request.url)
            if not safe:
                await route.abort()
                return
            if self.config.respect_robots and not await self.robots.allowed(request.url):
                await route.abort()
                return
            host = urlparse(request.url).netloc
            await self._respect_host_delay(host)
            await route.continue_()

        try:
            await context.route("**/*", guard_request)
            page = await context.new_page()
            try:
                await page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=int(self.config.request_timeout_seconds * 1000),
                )
                try:
                    await page.wait_for_load_state("networkidle", timeout=2500)
                except PlaywrightTimeoutError:
                    pass
                final_url = page.url
                safe, reason = await asyncio.to_thread(is_safe_url, final_url)
                if not safe:
                    self._record_failure(url, f"rendered redirect unsafe: {reason}")
                    return None
                content = await page.content()
                if len(content.encode("utf-8")) > self.config.max_response_bytes:
                    self._record_failure(url, "rendered response too large")
                    return None
                self.stats.pages_fetched += 1
                return content
            finally:
                await page.close()
        except PlaywrightError as exc:
            self._record_failure(url, f"playwright {type(exc).__name__}: {exc}")
            return None
        finally:
            await context.close()

    def _record_failure(self, url: str, reason: str) -> None:
        self.stats.pages_failed += 1
        self.stats.failures.append({"url": url, "reason": reason})
        log.warning("fetch failed: %s — %s", url, reason)
