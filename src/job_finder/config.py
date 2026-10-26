"""Runtime configuration. Loaded from environment with conservative defaults."""

from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_USER_AGENT = "job_finder/0.1 (+https://github.com/facquah20/jobfinder)"

@dataclass(slots=True)
class CrawlConfig:
    """Conservative crawl defaults. Override via CLI or env."""

    user_agent: str = DEFAULT_USER_AGENT
    max_concurrency: int = 5
    per_host_concurrency: int = 2
    per_host_delay_seconds: float = 1.0
    request_timeout_seconds: float = 20.0
    max_retries: int = 3
    max_response_bytes: int = 3_000_000
    max_pages_per_host: int = 200
    max_total_pages: int = 5_000
    respect_robots: bool = True
    database_path: str = "jobfinder.sqlite3"

    @classmethod
    def from_env(cls) -> "CrawlConfig":
        return cls(
            user_agent=os.environ.get("JOBFINDER_USER_AGENT", DEFAULT_USER_AGENT),
            max_concurrency=int(os.environ.get("JOBFINDER_CONCURRENCY", "5")),
            per_host_delay_seconds=float(os.environ.get("JOBFINDER_HOST_DELAY", "1.0")),
            request_timeout_seconds=float(os.environ.get("JOBFINDER_TIMEOUT", "20.0")),
            respect_robots=os.environ.get("JOBFINDER_ROBOTS", "1") != "0",
            database_path=os.environ.get("JOBFINDER_DB", "jobfinder.sqlite3"),
        )