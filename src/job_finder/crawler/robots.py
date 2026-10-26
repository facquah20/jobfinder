"""robots.txt cache and checks."""

from __future__ import annotations

import asyncio
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import aiohttp


class RobotsCache:
    """Fetch and cache robots.txt per host. Fail-open only on network error."""

    def __init__(self, session: aiohttp.ClientSession, user_agent: str) -> None:
        self._session = session
        self._user_agent = user_agent
        self._cache: dict[str, RobotFileParser] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def allowed(self, url: str) -> bool:
        host = urlparse(url).netloc
        if host not in self._cache:
            self._locks.setdefault(host, asyncio.Lock())
            async with self._locks[host]:
                if host not in self._cache:
                    self._cache[host] = await self._fetch(url)
        return self._cache[host].can_fetch(self._user_agent, url)

    async def _fetch(self, url: str) -> RobotFileParser:
        parsed = urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        parser = RobotFileParser()
        parser.set_url(robots_url)
        try:
            async with self._session.get(robots_url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    text = await resp.text(errors="ignore")
                    parser.parse(text.splitlines())
                elif resp.status in (401, 403):
                    parser.disallow_all = True
                else:
                    parser.allow_all = True
        except (aiohttp.ClientError, asyncio.TimeoutError):
            # Conservative: if robots.txt can't be fetched, allow (RFC 9309 §2.2.1
            # treats 5xx as allow). We do NOT bypass explicit disallow rules.
            parser.allow_all = True
        return parser