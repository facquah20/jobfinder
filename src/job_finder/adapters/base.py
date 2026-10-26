"""Adapter protocol and registry."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from job_finder.models import RawJob

@runtime_checkable
class Adapter(Protocol):
    name: str
    priority: int  # lower = tried first

    def can_handle(self, url: str, html: str, content_type: str) -> bool: ...
    def extract(self, url: str, html: str) -> list[RawJob]: ...


_REGISTRY: list[Adapter] = []


def register(adapter: Adapter) -> Adapter:
    _REGISTRY.append(adapter)
    _REGISTRY.sort(key=lambda a: a.priority)
    return adapter


def get_adapters() -> list[Adapter]:
    return list(_REGISTRY)