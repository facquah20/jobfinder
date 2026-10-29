from datetime import datetime, timezone

import pytest
import httpx

from job_finder import dashboard
from job_finder.cli import build_parser
from job_finder.models import (
    CrawlStats,
    EmploymentType,
    JobPosting,
    JobStatus,
    WorkArrangement,
)
from job_finder.storage.database import JobRepository


def _job(
    *,
    title: str = "Senior Backend Engineer",
    url: str = "https://example.com/jobs/backend",
    company: str = "Example",
    location: str = "Remote",
    source: str = "greenhouse",
    work_arrangement: WorkArrangement = WorkArrangement.REMOTE,
) -> JobPosting:
    return JobPosting(
        title=title,
        url=url,
        company=company,
        location=location,
        description="Build Python services for our product team.",
        work_arrangement=work_arrangement,
        employment_type=EmploymentType.FULL_TIME,
        source=source,
        status=JobStatus.UNKNOWN,
        discovered_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
    )


@pytest.mark.asyncio
async def test_dashboard_renders_and_reports_saved_jobs(tmp_path):
    database = str(tmp_path / "jobs.sqlite3")
    repo = JobRepository(database)
    repo.upsert_many([_job()])
    repo.record_stats({"pages_fetched": 3, "jobs_extracted": 1})
    repo.close()

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=dashboard.create_app(database)),
        base_url="http://127.0.0.1",
    ) as client:
        page = await client.get("/")
        assets = await client.get("/assets/dashboard.js")
        stats = await client.get("/api/stats")
        jobs = await client.get("/api/jobs?q=backend&location=remote")

    assert page.status_code == 200
    assert "Find work that" in page.text
    assert assets.status_code == 200
    assert "safeJobUrl" in assets.text
    assert stats.json()["total_jobs"] == 1
    assert stats.json()["remote_jobs"] == 1
    assert stats.json()["companies"] == 1
    assert stats.json()["recent_runs"][0]["jobs_extracted"] == 1
    assert jobs.json()["total"] == 1
    assert jobs.json()["jobs"][0]["job"]["title"] == "Senior Backend Engineer"
    assert jobs.json()["jobs"][0]["score"] is not None


@pytest.mark.asyncio
async def test_dashboard_filters_and_paginates_saved_jobs(tmp_path):
    database = str(tmp_path / "jobs.sqlite3")
    repo = JobRepository(database)
    repo.upsert_many([
        _job(url="https://example.com/jobs/1"),
        _job(
            title="Product Designer",
            url="https://example.com/jobs/2",
            company="Design Co",
            location="London",
            source="lever",
            work_arrangement=WorkArrangement.ONSITE,
        ),
    ])
    repo.close()

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=dashboard.create_app(database)),
        base_url="http://127.0.0.1",
    ) as client:
        first_page = await client.get("/api/jobs?page_size=1&page=1")
        second_page = await client.get("/api/jobs?page_size=1&page=2")
        by_source = await client.get("/api/jobs?source=lever")
        remote_only = await client.get("/api/jobs?remote_only=true")
        whitespace_location = await client.get("/api/jobs?location=%20%20")

    assert first_page.json()["total"] == 2
    assert first_page.json()["page"] == 1
    assert second_page.json()["jobs"][0]["job"]["title"] == "Product Designer"
    assert by_source.json()["total"] == 1
    assert by_source.json()["jobs"][0]["job"]["source"] == "lever"
    assert remote_only.json()["total"] == 1
    assert whitespace_location.json()["total"] == 2


@pytest.mark.asyncio
async def test_dashboard_starts_crawl_and_persists_results(tmp_path, monkeypatch):
    database = str(tmp_path / "jobs.sqlite3")

    class FakeEngine:
        def __init__(self, config):
            self.stats = CrawlStats(pages_fetched=2, jobs_extracted=1)

        async def crawl(self, seeds):
            assert seeds == ["https://example.com/careers"]
            return [_job()]

    monkeypatch.setattr(dashboard, "CrawlEngine", FakeEngine)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=dashboard.create_app(database)),
        base_url="http://127.0.0.1",
    ) as client:
        response = await client.post(
            "/api/crawl",
            json={"seeds": [" https://example.com/careers ", "https://example.com/careers"]},
        )
        status = await client.get("/api/crawl/status")
        stats = await client.get("/api/stats")

    assert response.status_code == 202
    assert response.json()["seeds"] == ["https://example.com/careers"]
    assert status.json()["state"] == "completed"
    assert status.json()["jobs_found"] == 1
    assert stats.json()["total_jobs"] == 1
    assert stats.json()["recent_runs"][0]["pages_fetched"] == 2


@pytest.mark.asyncio
async def test_dashboard_rejects_empty_seed_list(tmp_path):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(
            app=dashboard.create_app(str(tmp_path / "jobs.sqlite3"))
        ),
        base_url="http://127.0.0.1",
    ) as client:
        response = await client.post("/api/crawl", json={"seeds": [" ", ""]})

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_dashboard_rejects_non_local_host_header(tmp_path):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(
            app=dashboard.create_app(str(tmp_path / "jobs.sqlite3"))
        ),
        base_url="http://127.0.0.1",
    ) as client:
        response = await client.get("/", headers={"host": "attacker.example"})

    assert response.status_code == 400


def test_dashboard_cli_uses_local_port_and_database():
    args = build_parser().parse_args(
        ["dashboard", "--database", "jobs.db", "--port", "8123"]
    )

    assert args.database == "jobs.db"
    assert args.port == 8123


@pytest.mark.parametrize("port", ["0", "65536"])
def test_dashboard_cli_rejects_invalid_port(port):
    with pytest.raises(SystemExit):
        build_parser().parse_args(["dashboard", "--port", port])
