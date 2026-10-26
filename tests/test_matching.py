from job_finder.matching.parser import parse_query
from job_finder.matching.scorer import score_job
from job_finder.models import (
    EmploymentType, JobPosting, WorkArrangement,
)


def _job(**overrides):
    base = dict(
        title="Senior Backend Engineer",
        company="Acme",
        url="https://acme.example/jobs/1",
        description="We use Python, FastAPI, and PostgreSQL. Remote-friendly.",
        location="Berlin, DE",
        work_arrangement=WorkArrangement.REMOTE,
        employment_type=EmploymentType.FULL_TIME,
    )
    base.update(overrides)
    return JobPosting(**base)


def test_parse_extracts_skills_and_seniority():
    q = parse_query("Senior backend engineer with Python and FastAPI, remote")
    assert "python" in q.must_have_skills
    assert "fastapi" in q.must_have_skills
    assert q.seniority == "senior"


def test_high_score_for_relevant_job():
    q = parse_query("Senior backend engineer with Python and FastAPI",
                    remote_ok=True)
    m = score_job(_job(), q)
    assert m is not None
    assert m.score >= 50
    assert any("title" in r for r in m.reasons)


def test_missing_must_have_penalised():
    q = parse_query("Engineer with Python and Rust")
    m = score_job(_job(), q)
    # Rust missing → penalty applied
    assert m is None or m.score < 80


def test_exclusions_filter():
    q = parse_query("Engineer, excluding unpaid")
    unpaid = _job(title="Backend Engineer Intern",
                  description="Unpaid internship with Python.",
                  employment_type=EmploymentType.INTERNSHIP)
    m = score_job(unpaid, q)
    assert m is None or m.score < 50


def test_remote_match():
    q = parse_query("Backend engineer", remote_ok=True)
    m = score_job(_job(), q)
    assert m is not None
    assert any("remote" in r.lower() for r in m.reasons)