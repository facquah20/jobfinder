"""Permitted external search sources for company careers-page discovery."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import aiohttp


@dataclass(frozen=True, slots=True)
class SearchResult:
    title: str
    url: str
    snippet: str = ""


class SearchSource(Protocol):
    async def search(self, query: str) -> list[SearchResult]: ...


class GoogleCustomSearchSource:
    """Google Programmable Search JSON API client."""

    endpoint = "https://google.serper.dev/search"

    def __init__(
        self,
        session: aiohttp.ClientSession,
        api_key: str,
        engine_id: str,
        *,
        result_limit: int = 10,
    ) -> None:
        if not api_key or not engine_id:
            raise ValueError("Google Custom Search API key and engine ID are required")
        self._session = session
        self._api_key = api_key
        self._engine_id = engine_id
        self._result_limit = min(max(result_limit, 1), 10)

    async def search(self, query: str) -> list[SearchResult]:
        async with self._session.get(
            self.endpoint,
            params={
                "apiKey": self._api_key,
                # "cx": self._engine_id,
                "q": query,
                "num": self._result_limit,
            },
        ) as response:
            response.raise_for_status()
            payload = await response.json()

        if not isinstance(payload, dict):
            raise ValueError("Google Custom Search returned an invalid response")
        items = payload.get("items", [])
        if not isinstance(items, list):
            raise ValueError("Google Custom Search returned an invalid items field")
        results: list[SearchResult] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            link = item.get("link")
            if not isinstance(link, str):
                continue
            results.append(SearchResult(
                title=str(item.get("title") or ""),
                url=link,
                snippet=str(item.get("snippet") or ""),
            ))
        return results
