"""URL safety and canonicalisation helpers."""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urljoin, urlparse

from job_finder.models import canonicalize_url

_BLOCKED_HOSTNAMES = {"localhost", "metadata.google.internal"}


def is_safe_url(url: str) -> tuple[bool, str]:
    """Reject non-HTTP(S), private-network, and link-local targets.

    Returns (ok, reason). DNS resolution failure is treated as unsafe for
    fetching, but callers may still canonicalise the URL for storage.
    """
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False, f"scheme {parsed.scheme!r} not allowed"
    host = parsed.hostname
    if not host:
        return False, "no hostname"
    if host.lower() in _BLOCKED_HOSTNAMES:
        return False, "blocked hostname"
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        return False, f"dns error: {exc}"
    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            continue
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast):
            return False, f"resolved to non-public ip {ip}"
    return True, ""


def resolve_relative(base: str, link: str) -> str:
    """Resolve a possibly-relative link against a base URL."""
    if not link:
        return ""
    try:
        joined = urljoin(base, link.strip())
    except ValueError:
        return ""
    return canonicalize_url(joined)