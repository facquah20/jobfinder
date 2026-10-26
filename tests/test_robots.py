import asyncio
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest

from job_finder.crawler.robots import RobotsCache


@pytest.mark.asyncio
async def test_allow_all_when_robots_missing(monkeypatch):
    session = MagicMock()
    resp = MagicMock()
    resp.status = 404
    resp.text = AsyncMock(return_value="")

    class _Ctx:
        async def __aenter__(self): return resp
        async def __aexit__(self, *a): return False
    session.get = MagicMock(return_value=_Ctx())

    cache = RobotsCache(session, "jobfinder")
    assert await cache.allowed("https://x.example/a") is True


@pytest.mark.asyncio
async def test_disallow_rules_honoured():
    session = MagicMock()
    resp = MagicMock()
    resp.status = 200
    resp.text = AsyncMock(return_value="User-agent: *\nDisallow: /private\n")

    class _Ctx:
        async def __aenter__(self): return resp
        async def __aexit__(self, *a): return False
    session.get = MagicMock(return_value=_Ctx())

    cache = RobotsCache(session, "jobfinder")
    assert await cache.allowed("https://x.example/private/x") is False
    assert await cache.allowed("https://x.example/public") is True