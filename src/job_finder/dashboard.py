"""Local web dashboard for browsing and searching stored jobs."""

from __future__ import annotations

import asyncio
import logging
import threading
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from job_finder.config import CrawlConfig
from job_finder.crawler.engine import CrawlEngine
from job_finder.matching.parser import parse_query
from job_finder.matching.scorer import score_job
from job_finder.models import (
    EmploymentType,
    JobMatch,
    JobPosting,
    JobStatus,
    WorkArrangement,
)
from job_finder.storage.database import JobRepository

log = logging.getLogger(__name__)
_ASSET_DIR = Path(__file__).with_name("static")


class CrawlRequest(BaseModel):
    seeds: list[str] = Field(min_length=1, max_length=50)

    @field_validator("seeds")
    @classmethod
    def clean_seeds(cls, seeds: list[str]) -> list[str]:
        cleaned = list(dict.fromkeys(seed.strip() for seed in seeds if seed.strip()))
        if not cleaned:
            raise ValueError("provide at least one seed URL")
        if any(len(seed) > 2048 for seed in cleaned):
            raise ValueError("seed URLs must be 2048 characters or fewer")
        return cleaned


def _job_result(job: JobPosting, match: JobMatch | None) -> dict:
    return {
        "job": job.model_dump(mode="json"),
        "score": match.score if match else None,
        "reasons": match.reasons if match else [],
    }


def create_app(database_path: str) -> FastAPI:
    """Create the dashboard app bound to the selected SQLite database."""
    app = FastAPI(title="Jobfinder Dashboard", docs_url=None, redoc_url=None)
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["127.0.0.1", "localhost"],
    )
    app.mount("/assets", StaticFiles(directory=_ASSET_DIR), name="assets")
    crawl_lock = threading.Lock()
    crawl_state: dict[str, object] = {
        "state": "idle",
        "started_at": None,
        "finished_at": None,
        "seeds": [],
        "jobs_found": 0,
        "error": None,
    }

    def repository() -> Generator[JobRepository, None, None]:
        repo = JobRepository(database_path)
        try:
            yield repo
        finally:
            repo.close()

    def perform_crawl(seeds: list[str]) -> None:
        with crawl_lock:
            crawl_state.update(
                state="running",
                started_at=None,
                finished_at=None,
                seeds=seeds,
                jobs_found=0,
                error=None,
            )
            crawl_state["started_at"] = datetime.now(timezone.utc).isoformat()
        try:
            cfg = CrawlConfig.from_env()
            cfg.database_path = database_path
            engine = CrawlEngine(cfg)
            jobs = asyncio.run(engine.crawl(seeds))
            repo = JobRepository(database_path)
            try:
                repo.upsert_many(jobs)
                repo.record_stats(engine.stats.model_dump())
            finally:
                repo.close()
            with crawl_lock:
                crawl_state["jobs_found"] = len(jobs)
                crawl_state["state"] = "completed"
                crawl_state["finished_at"] = datetime.now(timezone.utc).isoformat()
        except Exception as exc:
            log.exception("Dashboard crawl failed")
            with crawl_lock:
                crawl_state["error"] = str(exc)
                crawl_state["state"] = "failed"
                crawl_state["finished_at"] = datetime.now(timezone.utc).isoformat()

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(_ASSET_DIR / "dashboard.html")

    @app.get("/api/stats")
    def stats(repo: JobRepository = Depends(repository)) -> dict:
        jobs = repo.all()
        sources = Counter(job.source for job in jobs)
        companies = {job.company.strip().casefold() for job in jobs if job.company}
        return {
            "total_jobs": len(jobs),
            "remote_jobs": sum(
                job.work_arrangement == WorkArrangement.REMOTE
                or "remote" in f"{job.title} {job.description}".casefold()
                for job in jobs
            ),
            "companies": len(companies),
            "sources": dict(sorted(sources.items())),
            "recent_runs": repo.recent_runs(5),
        }

    @app.get("/api/jobs")
    def jobs(
        q: str = Query(default="", max_length=300),
        location: str | None = Query(default=None, max_length=200),
        remote_only: bool = False,
        source: str | None = Query(default=None, max_length=100),
        status: JobStatus | None = None,
        work_arrangement: WorkArrangement | None = None,
        employment_type: EmploymentType | None = None,
        min_score: float = Query(default=0, ge=0, le=100),
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=25, ge=1, le=100),
        repo: JobRepository = Depends(repository),
    ) -> dict:
        location_value = location.strip() if location else ""
        has_search = bool(q.strip() or location_value or remote_only)
        query = parse_query(
            q,
            location=location_value or None,
            remote_ok=remote_only,
            min_score=min_score,
        )
        matching_jobs: list[tuple[JobPosting, JobMatch | None]] = []
        location_filter = location_value.casefold()
        for job in repo.all():
            if source and job.source.casefold() != source.casefold():
                continue
            if status and job.status != status:
                continue
            if work_arrangement and job.work_arrangement != work_arrangement:
                continue
            if employment_type and job.employment_type != employment_type:
                continue
            if location_filter and location_filter not in " ".join(
                (job.location or "", job.title, job.description)
            ).casefold():
                continue
            if remote_only and job.work_arrangement != WorkArrangement.REMOTE:
                if "remote" not in f"{job.title} {job.description}".casefold():
                    continue
            match = score_job(job, query) if has_search else None
            if match is None and has_search:
                continue
            matching_jobs.append((job, match))

        if has_search:
            matching_jobs.sort(key=lambda item: item[1].score, reverse=True)
        else:
            matching_jobs.sort(
                key=lambda item: item[0].discovered_at,
                reverse=True,
            )
        total = len(matching_jobs)
        start = (page - 1) * page_size
        results = [
            _job_result(job, match)
            for job, match in matching_jobs[start : start + page_size]
        ]
        return {
            "jobs": results,
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    @app.post("/api/crawl", status_code=202)
    def start_crawl(
        request: CrawlRequest,
        background_tasks: BackgroundTasks,
    ) -> dict:
        with crawl_lock:
            if crawl_state["state"] in {"queued", "running"}:
                raise HTTPException(status_code=409, detail="A crawl is already running")
            crawl_state.update(
                state="queued",
                started_at=None,
                finished_at=None,
                seeds=request.seeds,
                jobs_found=0,
                error=None,
            )
        background_tasks.add_task(perform_crawl, request.seeds)
        return {"state": "queued", "seeds": request.seeds}

    @app.get("/api/crawl/status")
    def get_crawl_status() -> dict:
        with crawl_lock:
            return dict(crawl_state)

    return app
