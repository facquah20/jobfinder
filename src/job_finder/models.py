"""Pydantic models for jobs, queries, and results."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from urllib.parse import urlparse, urlunparse

from pydantic import BaseModel, Field, HttpUrl, field_validator


class WorkArrangement(StrEnum):
    REMOTE = "remote"
    HYBRID = "hybrid"
    ONSITE = "onsite"
    UNKNOWN = "unknown"


class JobStatus(StrEnum):
    ACTIVE = "active"
    EXPIRED = "expired"
    UNKNOWN = "unknown"


class EmploymentType(StrEnum):
    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    CONTRACT = "contract"
    INTERNSHIP = "internship"
    UNKNOWN = "unknown"


def canonicalize_url(url: str) -> str:
    """Lowercase scheme+host, drop fragment and known tracking params."""
    p = urlparse(url.strip())
    if p.scheme not in {"http", "https"}:
        return url
    query_parts = []
    for pair in p.query.split("&"):
        if not pair:
            continue
        key = pair.split("=", 1)[0].lower()
        if key in {"utm_source", "utm_medium", "utm_campaign", "utm_term",
                   "utm_content", "gclid", "fbclid", "ref"}:
            continue
        query_parts.append(pair)
    return urlunparse((p.scheme.lower(), p.netloc.lower(), p.path,
                       p.params, "&".join(query_parts), ""))


class RawJob(BaseModel):
    """Adapter output before normalisation. May be partial."""

    title: str
    url: str
    source: str
    company: str | None = None
    location: str | None = None
    description_html: str | None = None
    employment_type: str | None = None
    posting_date: str | None = None
    salary: str | None = None
    identifier: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class JobPosting(BaseModel):
    """Normalised, validated job record."""

    title: str
    company: str | None = None
    url: str
    career_page_url: str | None = None
    description: str = ""
    location: str | None = None
    work_arrangement: WorkArrangement = WorkArrangement.UNKNOWN
    employment_type: EmploymentType = EmploymentType.UNKNOWN
    salary: str | None = None
    posting_date: str | None = None
    identifier: str | None = None
    source: str = "unknown"
    status: JobStatus = JobStatus.UNKNOWN
    status_evidence: str = ""
    discovered_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    canonical_url: str = ""

    @field_validator("url", mode="before")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()

    def model_post_init(self, __context: Any) -> None:
        if not self.canonical_url:
            self.canonical_url = canonicalize_url(self.url)

    def dedupe_key(self) -> str:
        """Stable key for cross-source duplicate detection."""
        parts = [
            self.canonical_url,
            (self.company or "").lower().strip(),
            self.title.lower().strip(),
            (self.location or "").lower().strip(),
        ]
        digest = hashlib.sha256("|".join(parts).encode()).hexdigest()
        return digest

    @classmethod
    def from_raw(cls, raw: RawJob, career_page_url: str | None = None) -> "JobPosting":
        return cls(
            title=raw.title.strip(),
            company=raw.company,
            url=raw.url,
            career_page_url=career_page_url,
            description=raw.description_html or "",
            location=raw.location,
            employment_type=_guess_employment(raw.employment_type),
            salary=raw.salary,
            posting_date=raw.posting_date,
            identifier=raw.identifier,
            source=raw.source,
        )


def _guess_employment(value: str | None) -> EmploymentType:
    if not value:
        return EmploymentType.UNKNOWN
    v = value.lower()
    if "intern" in v:
        return EmploymentType.INTERNSHIP
    if "part" in v:
        return EmploymentType.PART_TIME
    if "contract" in v or "temporary" in v:
        return EmploymentType.CONTRACT
    if "full" in v:
        return EmploymentType.FULL_TIME
    return EmploymentType.UNKNOWN


class SearchQuery(BaseModel):
    """User intent, normalised for scoring."""

    raw_query: str
    title_tokens: list[str] = Field(default_factory=list)
    must_have_skills: list[str] = Field(default_factory=list)
    nice_to_have_skills: list[str] = Field(default_factory=list)
    exclusions: list[str] = Field(default_factory=list)
    seniority: str | None = None
    location: str | None = None
    remote_ok: bool = False
    min_score: float = 0.0

    def text_blob(self) -> str:
        return " ".join([
            self.raw_query,
            " ".join(self.title_tokens),
            " ".join(self.must_have_skills),
            " ".join(self.nice_to_have_skills),
        ]).lower()


class JobMatch(BaseModel):
    job: JobPosting
    score: float
    reasons: list[str]


class CrawlStats(BaseModel):
    pages_fetched: int = 0
    pages_skipped_robots: int = 0
    pages_failed: int = 0
    jobs_extracted: int = 0
    jobs_deduplicated: int = 0
    failures: list[dict[str, str]] = Field(default_factory=list)


class FetchResult(BaseModel):
    url: str
    status: int
    content: bytes | None = None
    final_url: str | None = None
    error: str | None = None