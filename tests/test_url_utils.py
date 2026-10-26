import pytest

from job_finder.crawler.url_utils import is_safe_url, resolve_relative
from job_finder.models import canonicalize_url


def test_canonicalize_strips_tracking_and_fragment():
    url = "https://Example.COM/Jobs/1?utm_source=x&id=5#top"
    assert canonicalize_url(url) == "https://example.com/Jobs/1?id=5"


def test_resolve_relative():
    assert resolve_relative("https://x.example/a/b", "../c") == "https://x.example/c"


def test_rejects_loopback():
    ok, reason = is_safe_url("http://127.0.0.1/x")
    assert not ok
    assert "non-public" in reason or "blocked" in reason


def test_rejects_file_scheme():
    ok, _ = is_safe_url("file:///etc/passwd")
    assert not ok