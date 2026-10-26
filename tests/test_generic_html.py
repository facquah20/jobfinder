from pathlib import Path

from job_finder.adapters import generic_html  # noqa: F401
from job_finder.adapters.base import get_adapters

FIX = Path(__file__).parent / "fixtures"


def _adapter():
    return next(a for a in get_adapters() if a.name == "generic_html")


def test_extracts_job_page():
    html = (FIX / "generic_job.html").read_text()
    jobs = _adapter().extract("https://globex.example/careers/data-analyst", html)
    assert len(jobs) == 1
    assert "Data Analyst" in jobs[0].title
    assert jobs[0].company == "Globex"


def test_ignores_non_job_page():
    html = (FIX / "not_a_job.html").read_text()
    jobs = _adapter().extract("https://globex.example/about", html)
    assert jobs == []