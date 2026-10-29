"""Shared helpers for public applicant-tracking-system feeds."""

from __future__ import annotations

from urllib.parse import urlparse

from bs4 import BeautifulSoup


def provider_urls(url: str, html: str, domains: tuple[str, ...]) -> list[str]:
    """Return the page URL and linked ATS URLs for the requested domains."""
    candidates = [url]
    soup = BeautifulSoup(html, "lxml")
    for link in soup.find_all("a", href=True):
        candidates.append(str(link["href"]))

    urls: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        parsed = urlparse(candidate)
        if not parsed.scheme:
            from urllib.parse import urljoin

            parsed = urlparse(urljoin(url, candidate))
        host = (parsed.hostname or "").lower()
        if not any(host == domain or host.endswith(f".{domain}") for domain in domains):
            continue
        normalized = parsed._replace(fragment="").geturl()
        if normalized not in seen:
            seen.add(normalized)
            urls.append(normalized)
    return urls


def first_text(*values: object) -> str | None:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def json_items(data: object, *keys: str) -> list[dict[str, object]]:
    """Find a provider job list without assuming one envelope shape."""
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        for key in keys:
            value = data.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []
