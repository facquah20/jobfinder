from pathlib import Path

from job_finder.adapters import schema_org  # noqa: F401 (registers)
from job_finder.adapters.base import get_adapters

FIX = Path(__file__).parent / "fixtures"


def _adapter():
    return next(a for a in get_adapters() if a.name == "schema_org")


def test_extracts_job_from_graph():
    html = (FIX / "schema_org_job.html").read_text()
    jobs = _adapter().extract("https://acme.example/careers", html)
    assert len(jobs) == 1
    job = jobs[0]
    assert job.title == "Senior Backend Engineer"
    assert job.company == "Acme Corp"
    assert "Berlin" in (job.location or "")
    assert job.identifier == "REQ-123"
    assert job.url == "https://acme.example/jobs/123"


def test_can_handle_detects_ld_json():
    adapter = _adapter()
    html = (FIX / "schema_org_job.html").read_text()
    assert adapter.can_handle("https://x.example", html, "text/html")