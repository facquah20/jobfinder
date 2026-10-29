"""Adapter protocol and registry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from typing import Protocol, runtime_checkable

from job_finder.models import RawJob


@dataclass(frozen=True, slots=True)
class FeedRequest:
    """A public provider feed request discovered from a careers page."""

    url: str
    method: str = "GET"
    json_body: dict[str, Any] | None = None
    career_page_url: str | None = None


@runtime_checkable
class Adapter(Protocol):
    name: str
    priority: int  # lower = tried first

    def can_handle(self, url: str, html: str, content_type: str) -> bool: ...
    def extract(self, url: str, html: str) -> list[RawJob]: ...
    def feed_requests(self, url: str, html: str) -> list[FeedRequest]: ...


_REGISTRY: list[Adapter] = []


def register(adapter: Adapter) -> Adapter:
    _REGISTRY.append(adapter)
    _REGISTRY.sort(key=lambda a: a.priority)
    return adapter


def get_adapters() -> list[Adapter]:
    return list(_REGISTRY)