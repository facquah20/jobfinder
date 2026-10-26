from datetime import datetime, timezone

from job_finder.models import JobPosting
from job_finder.storage.database import JobRepository


def _job(url="https://x.example/jobs/1", title="Engineer"):
    return JobPosting(title=title, url=url, company="X",
                      discovered_at=datetime.now(timezone.utc))


def test_insert_then_dedupe(tmp_path):
    repo = JobRepository(str(tmp_path / "t.db"))
    assert repo.upsert_many([_job()]) == (1, 0)
    assert repo.upsert_many([_job()]) == (0, 1)
    assert len(repo.all()) == 1
    repo.close()


def test_different_urls_persist(tmp_path):
    repo = JobRepository(str(tmp_path / "t.db"))
    repo.upsert_many([_job(url="https://x.example/jobs/1"),
                      _job(url="https://x.example/jobs/2")])
    assert len(repo.all()) == 2
    repo.close()