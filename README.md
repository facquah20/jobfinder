# jobfinder

# `jobfinder` — Configurable Job Discovery & Career-Page Crawling System

> **A production-shaped Python system that turns a natural-language job description into ranked, deduplicated, verified direct links to real vacancies on company career pages.**

---

## Table of Contents

1. [What this project is](#1-what-this-project-is)
2. [What this project is *not*](#2-what-this-project-is-not)
3. [Current status and capability matrix](#3-current-status-and-capability-matrix)
4. [Key design principles](#4-key-design-principles)
5. [System architecture](#5-system-architecture)
6. [Data model](#6-data-model)
7. [Installation](#7-installation)
8. [Quick start](#8-quick-start)
9. [Command reference](#9-command-reference)
10. [Configuration reference](#10-configuration-reference)
11. [How crawling works](#11-how-crawling-works)
12. [How extraction works](#12-how-extraction-works)
13. [How matching works](#13-how-matching-works)
14. [How deduplication works](#14-how-deduplication-works)
15. [How persistence works](#15-how-persistence-works)
16. [Safety, ethics, and compliance](#16-safety-ethics-and-compliance)
17. [Output formats](#17-output-formats)
18. [Testing](#18-testing)
19. [Project layout](#19-project-layout)
20. [Troubleshooting](#20-troubleshooting)
21. [Known limitations](#21-known-limitations)
22. [Roadmap (Stages 3–5)](#22-roadmap-stages-35)
23. [Dependency rationale](#23-dependency-rationale)
24. [Contributing](#24-contributing)
25. [License and legal notes](#25-license-and-legal-notes)

---

## 1. What this project is

`jobfinder` is a **configurable job discovery and career-page crawling system** written in modern Python (3.12+). It is designed to:

- Accept a **natural-language description** of the kind of job you want (e.g. *"Mid-level backend engineer using Python and FastAPI, remote-friendly"*).
- Crawl one or more **seed career pages** asynchronously, respecting `robots.txt`, per-host rate limits, and safe-URL rules.
- Extract individual **job vacancy records** from pages using structured data (schema.org `JobPosting` JSON-LD) first, with a conservative heuristic fallback.
- **Deduplicate** postings across sources using canonical URLs and a stable `(company, title, location)` hash.
- **Rank** postings against your query with a transparent, explainable weighted scorer.
- **Persist** every job to SQLite so runs are incremental and repeatable.
- **Export** results as CSV and JSON, with a terminal summary and per-match reasons.

It is **not** a scraper-of-everything. It is a **disciplined pipeline** with clear boundaries between discovery, crawling, extraction, scoring, persistence, and export — so each can be improved without rewriting the rest.

---

## 2. What this project is *not*

Being explicit protects both users and maintainers:

- **Not a general web scraper.** It only fetches URLs you provide (or, in Stage 3, URLs discovered through documented, permitted sources).
- **Not a circumvention tool.** It does **not** bypass CAPTCHAs, authentication, paywalls, or anti-bot systems. It does **not** rotate identities, proxies, or user agents to evade restrictions.
- **Not a claim of exhaustive coverage.** It cannot search "the entire internet". Coverage equals the seed list you supply (plus, later, sources you enable).
- **Not an automatic applier.** It never submits applications. It returns links; a human clicks them.
- **Not a source of truth about job status.** A HTTP 200 response does **not** mean a vacancy is open. Status is `unknown` unless positively verified (Stage 4).
- **Not an LLM wrapper.** Semantic/embedding matching is a Stage 5 optional module. The current matcher is deterministic and fully explainable.

---

## 3. Current status and capability matrix

The project is being built in the five stages described in the original specification. This README documents **Stages 1 and 2**, which are complete as source code (tests must be run locally to verify — see §18).

| Capability | Stage | Status |
|---|---|---|
| Natural-language query parsing | 2 | ✅ Implemented |
| Async crawl engine with bounded concurrency | 2 | ✅ Implemented |
| `robots.txt` enforcement | 2 | ✅ Implemented |
| Per-host rate limiting | 2 | ✅ Implemented |
| Retry with exponential backoff + jitter | 2 | ✅ Implemented |
| SSRF protection on seeds and redirects | 2 | ✅ Implemented |
| schema.org `JobPosting` extraction (incl. `@graph`) | 2 | ✅ Implemented |
| Conservative generic HTML fallback | 2 | ✅ Implemented |
| Explainable weighted scoring | 2 | ✅ Implemented |
| Deduplication | 2 | ✅ Implemented |
| SQLite persistence with incremental upsert | 2 | ✅ Implemented |
| CSV export | 2 | ✅ Implemented |
| JSON export | 2 | ✅ Implemented |
| CLI: `search`, `stats` | 2 | ✅ Implemented |
| Provider adapters (Greenhouse, Lever, Ashby, Workday) | 3 | ❌ Not yet |
| Company-name → careers-page discovery | 3 | ❌ Not yet |
| Playwright fallback for JS-rendered pages | 3 | ❌ Not yet |
| Job-status re-verification | 4 | ❌ Not yet |
| Scheduled / repeated runs | 4 | ❌ Not yet |
| Web dashboard | 5 | ❌ Not yet |
| Semantic / embedding matcher | 5 | ❌ Not yet |
| Multi-user profiles | 5 | ❌ Not yet |
| Notifications | 5 | ❌ Not yet |

The Stage 1–2 boundary is deliberate: get extraction, scoring, and dedupe **correct and tested** before adding breadth.

---

## 4. Key design principles

These principles explain nearly every implementation choice in the codebase.

1. **Separation of concerns over cleverness.**
   Discovery, crawling, extraction, scoring, persistence, and export live in separate modules. A bug in the scorer never crashes the crawler; an adapter crash is caught per-page.

2. **Structured data first, heuristics last.**
   JSON-LD `JobPosting` is checked before any HTML heuristic. The generic HTML extractor is labelled `source="generic_html"` and is intentionally pessimistic — it requires multiple positive signals before emitting a job.

3. **Explainability over accuracy theatre.**
   Every score comes with a list of human-readable reasons (`"title matches ['backend', 'engineer'] (+20)"`). A job with no reasons is not returned. There is no opaque numeric score.

4. **Uncertainty is expressed, not hidden.**
   A job is never `active` merely because it returned HTTP 200. It is `unknown` with `status_evidence` until verified.

5. **Safety is a first-class feature.**
   `is_safe_url()` is called on every seed **and again after every redirect**. Loopback, private, link-local, and reserved IPs are rejected. Non-HTTP(S) schemes are rejected.

6. **Respect is default-on.**
   `robots.txt` is fetched, cached, and enforced before **every** page fetch. Per-host delays default to 1 request/sec. `--no-robots` exists but is documented as discouraged.

7. **Incremental by design.**
   SQLite stores `first_seen` and `last_seen`. Rerunning the crawler on the same seeds **does not** duplicate rows; it updates them.

8. **Missing data is never invented.**
   `JobPosting` fields default to `None` or `unknown`. `location`, `salary`, `posting_date`, `identifier` are all optional.

---

## 5. System architecture

### 5.1 Component diagram

```
                    ┌──────────────────────────────┐
                    │          CLI (argparse)      │
                    │   jobfinder/cli.py           │
                    └───────────────┬──────────────┘
                                    │
             ┌──────────────────────┼──────────────────────┐
             │                      │                      │
             ▼                      ▼                      ▼
   ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
   │   Config        │    │  Query Parser   │    │   Seed input    │
   │ config.py       │    │ matching/parser │    │ --seed / file   │
   └────────┬────────┘    └────────┬────────┘    └────────┬────────┘
            │                      │                      │
            │                      │                      ▼
            │                      │            ┌─────────────────┐
            │                      │            │  Crawl Engine   │
            │                      │            │ crawler/engine  │
            │                      │            └────────┬────────┘
            │                      │                     │
            │                      │         ┌───────────┼───────────┐
            │                      │         ▼           ▼           ▼
            │                      │  ┌───────────┐ ┌─────────┐ ┌──────────┐
            │                      │  │  Robots   │ │  URL    │ │  Retry   │
            │                      │  │  Cache    │ │ Safety  │ │(tenacity)│
            │                      │  └───────────┘ └─────────┘ └──────────┘
            │                      │                     │
            │                      │                     ▼
            │                      │            ┌─────────────────┐
            │                      │            │ Adapter Registry│
            │                      │            │ (priority order)│
            │                      │            └────────┬────────┘
            │                      │                     │
            │                      │       ┌─────────────┼─────────────┐
            │                      │       ▼             ▼             ▼
            │                      │  ┌──────────┐ ┌───────────┐ ┌──────────┐
            │                      │  │schema_org│ │ generic_  │ │ (Stage 3:│
            │                      │  │          │ │   html    │ │ providers)│
            │                      │  └──────────┘ └───────────┘ └──────────┘
            │                      │                     │
            │                      │                     ▼
            │                      │            ┌─────────────────┐
            │                      │            │   JobPosting    │
            │                      │            │   (validated)   │
            │                      │            └────────┬────────┘
            │                      │                     │
            │                      ▼                     ▼
            │             ┌─────────────────┐   ┌─────────────────┐
            └────────────▶│  Scorer         │◀──│  SQLite Repo    │
                          │ matching/scorer │   │ storage/database│
                          └────────┬────────┘   └─────────────────┘
                                   │
                                   ▼
                          ┌─────────────────┐
                          │  JobMatch list  │
                          └────────┬────────┘
                                   │
                        ┌──────────┼──────────┐
                        ▼          ▼          ▼
                  ┌─────────┐ ┌────────┐ ┌──────────┐
                  │Terminal │ │  CSV   │ │   JSON   │
                  └─────────┘ └────────┘ └──────────┘
```

### 5.2 Data flow

1. The CLI parses arguments into a `SearchQuery` (via `matching/parser.py`) and a `CrawlConfig` (via `config.py`).
2. `CrawlEngine` is constructed with the config.
3. The engine opens an `aiohttp` session with conservative defaults.
4. Seed URLs are dispatched concurrently (bounded by a global semaphore).
5. For each URL:
   - `is_safe_url()` is checked.
   - `RobotsCache.allowed()` is checked (cached per host).
   - The URL is fetched with retry, per-host delay, and per-host concurrency.
   - Redirects are followed up to `max_redirects`, and **the final URL is re-checked for safety**.
6. HTML is passed to the adapter registry in priority order.
7. Extracted `RawJob` objects are normalised into `JobPosting` records.
8. All `JobPosting` records from the run are upserted to SQLite.
9. Every stored job is scored against the query, producing `JobMatch` objects.
10. Matches are sorted by score, truncated to `--limit`, printed, and optionally exported.

### 5.3 Module responsibilities

| Module | Responsibility |
|---|---|
| `jobfinder/src/job_finder/cli.py` | Argument parsing, orchestration, output formatting |
| `jobfinder/src/job_finder/config.py` | Runtime configuration dataclass, environment variables |
| `jobfinder/src/job_finder/models.py` | Pydantic models: `RawJob`, `JobPosting`, `SearchQuery`, `JobMatch`, `CrawlStats`, `FetchResult`, enums, `canonicalize_url` |
| `jobfinder/src/job_finder/crawler/engine.py` | Async crawl loop, retries, per-host limits, adapter dispatch |
| `jobfinder/src/job_finder/crawler/robots.py` | `robots.txt` fetch and cache |
| `jobfinder/src/job_finder/crawler/url_utils.py` | SSRF guards, redirect safety, relative URL resolution |
| `jobfinder/src/job_finder/adapters/base.py` | Adapter `Protocol` and priority registry |
| `jobfinder/src/job_finder/adapters/schema_org.py` | JSON-LD `JobPosting` extraction (handles `@graph`, nested arrays) |
| `jobfinder/src/job_finder/adapters/generic_html.py` | Conservative heuristic fallback |
| `jobfinder/src/job_finder/matching/parser.py` | NL query → `SearchQuery` |
| `jobfinder/src/job_finder/matching/scorer.py` | Weighted, explainable scoring |
| `jobfinder/src/job_finder/storage/database.py` | SQLite repository with upsert and dedupe |
| `jobfinder/src/job_finder/exports/csv_export.py` | CSV export |
| `jobfinder/src/job_finder/exports/json_export.py` | JSON export |

---

## 6. Data model

### 6.1 Enumerations

```python
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
```

### 6.2 `RawJob` — adapter output

A partially-populated dict-like record. Adapters emit `RawJob`; the engine converts them into `JobPosting`.

| Field | Type | Notes |
|---|---|---|
| `title` | `str` | Required |
| `url` | `str` | Required |
| `source` | `str` | Adapter name |
| `company` | `str \| None` | |
| `location` | `str \| None` | |
| `description_html` | `str \| None` | |
| `employment_type` | `str \| None` | |
| `posting_date` | `str \| None` | |
| `salary` | `str \| None` | |
| `identifier` | `str \| None` | |
| `raw` | `dict[str, Any]` | Debug/extras |

### 6.3 `JobPosting` — normalised record

The persisted, validated representation:

| Field | Type | Notes |
|---|---|---|
| `title` | `str` | Required |
| `company` | `str \| None` | |
| `url` | `str` | Required; the **direct vacancy URL** |
| `career_page_url` | `str \| None` | The page the vacancy was found on |
| `description` | `str` | Plain text, whitespace-normalised |
| `location` | `str \| None` | |
| `work_arrangement` | `WorkArrangement` | Default `unknown` |
| `employment_type` | `EmploymentType` | Guessed from strings when possible |
| `salary` | `str \| None` | Free-form when present |
| `posting_date` | `str \| None` | ISO-ish |
| `identifier` | `str \| None` | Requisition number / source ID |
| `source` | `str` | Adapter name |
| `status` | `JobStatus` | Default `unknown` |
| `status_evidence` | `str` | Human-readable justification |
| `discovered_at` | `datetime` | UTC |
| `canonical_url` | `str` | Computed on construction |

**`dedupe_key()`** returns a SHA-256 of `canonical_url | company | title | location` (lowercased, stripped). Two records with the same key are treated as the same job.

### 6.4 `SearchQuery` — user intent

```python
class SearchQuery(BaseModel):
    raw_query: str
    title_tokens: list[str]
    must_have_skills: list[str]
    nice_to_have_skills: list[str]
    exclusions: list[str]
    seniority: str | None
    location: str | None
    remote_ok: bool
    min_score: float
```

### 6.5 `JobMatch` — scored job

```python
class JobMatch(BaseModel):
    job: JobPosting
    score: float           # 0–100
    reasons: list[str]     # human-readable contributions
```

### 6.6 `CrawlStats` — run telemetry

```python
class CrawlStats(BaseModel):
    pages_fetched: int
    pages_skipped_robots: int
    pages_failed: int
    jobs_extracted: int
    jobs_deduplicated: int
    failures: list[dict[str, str]]  # {"url": ..., "reason": ...}
```

---

## 7. Installation

### 7.1 Requirements

- **Python 3.12+** (uses `StrEnum`, PEP 604 union syntax, `slots=True` dataclasses)
- A POSIX-like shell (Linux, macOS, WSL). Windows users should use WSL or adjust activation paths.
- No external services, API keys, or databases required.

### 7.2 Setup

```bash
git clone <your-repo-url> jobfinder
cd jobfinder

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -e ".[dev]"
```

### 7.3 Verify installation

```bash
python -m jobfinder --help
pytest -q
```

If both commands succeed, you're ready.

---

## 8. Quick start

### 8.1 Create a seed file

```bash
cat > seeds.txt <<'EOF'
https://careers.example-company.com
https://another-company.com/jobs
EOF
```

Seed URLs may point to **general careers pages**, **job listing pages**, or **individual job pages**. The crawler processes each URL once, and the adapter layer decides what (if anything) is a job.

### 8.2 Run a search

```bash
python -m jobfinder search \
  --query "Mid-level backend engineer using Python and FastAPI" \
  --location "Remote" \
  --remote \
  --seeds-file seeds.txt \
  --limit 25 \
  --csv results.csv \
  --json-out results.json
```

### 8.3 Read the output

Each match prints as:

```
[ 68.0] Senior Backend Engineer — Acme Corp
        https://acme.example/jobs/123
        Berlin, DE | remote | unknown
        why: title matches ['backend', 'engineer'] (+20); skills present: ['python', 'fastapi'] (+30); remote work mentioned (+20)
```

- The bracketed number is the **normalised score** (0–100).
- The second line is the **direct vacancy URL** — this is the URL you should open.
- The third line shows location, work arrangement, and status.
- The fourth line lists **why** the job matched — every scoring contribution, in order.

### 8.4 Inspect the database

```bash
python -m jobfinder stats
# stored jobs: 17
#   schema_org: 15
#   generic_html: 2
```

---

## 9. Command reference

### 9.1 `jobfinder search`

Crawl seeds, score jobs, and export matches.

```
usage: jobfinder search [options]

Required
  --query TEXT              Natural-language job description.
                            e.g. "Mid-level backend engineer using Python"

Optional
  --location TEXT           Free-form location filter text.
  --remote                  Boost jobs mentioning remote work.
  --limit N                 Max results to display (default: 50).
  --min-score FLOAT         Drop matches below this score (0–100, default 0).
  --seed URL                Add a seed URL (repeatable).
  --seeds-file PATH         Read seed URLs from a text file, one per line.
  --database PATH           SQLite path (overrides JOBFINDER_DB).
  --csv PATH                Write CSV export.
  --json-out PATH           Write JSON export.
  --no-robots               Disable robots.txt enforcement. DISCOURAGED.
  --verbose                 DEBUG-level logging.
```

**Behaviour:**
- Fetches each seed once.
- All extracted jobs are upserted to SQLite (INSERT or UPDATE by `dedupe_key`).
- **Scoring runs over the entire DB**, not just the current run's jobs. This means a fresh `--query` re-ranks all stored jobs — useful for exploring different searches against the same crawled corpus.

### 9.2 `jobfinder stats`

```
usage: jobfinder stats [--database PATH]

# Output:
# stored jobs: 42
#   schema_org: 38
#   generic_html: 4
```

### 9.3 Exit codes

| Code | Meaning |
|---|---|
| 0 | Success |
| 2 | Bad arguments (e.g. missing seeds) |
| 1 | Unhandled error (should not occur; logged) |

---

## 10. Configuration reference

### 10.1 `CrawlConfig` fields

Set defaults in code, or override via environment variables.

| Field | Default | Env var | Description |
|---|---|---|---|
| `user_agent` | `"jobfinder/0.1 (+https://example.invalid/bot)"` | `JOBFINDER_USER_AGENT` | HTTP User-Agent. **Set this to a real contact URL when crawling real sites.** |
| `max_concurrency` | `5` | `JOBFINDER_CONCURRENCY` | Global in-flight request cap |
| `per_host_concurrency` | `2` | — | Max concurrent requests per host |
| `per_host_delay_seconds` | `1.0` | `JOBFINDER_HOST_DELAY` | Minimum spacing between requests to the same host |
| `request_timeout_seconds` | `20.0` | `JOBFINDER_TIMEOUT` | Total per-request timeout |
| `max_retries` | `3` | — | Attempts on transient network failure |
| `max_response_bytes` | `3_000_000` | — | Reject responses larger than this |
| `max_pages_per_host` | `200` | — | Safety cap per host (advisory in Stage 2) |
| `max_total_pages` | `5_000` | — | Safety cap per run |
| `respect_robots` | `True` | `JOBFINDER_ROBOTS` (`1`/`0`) | Enforce `robots.txt` |
| `database_path` | `"jobfinder.sqlite3"` | `JOBFINDER_DB` | SQLite file path |

### 10.2 Recommended overrides for real-world crawling

```bash
export JOBFINDER_USER_AGENT="jobfinder/0.1 (+https://yourdomain.example/contact)"
export JOBFINDER_HOST_DELAY="2.0"      # be extra polite
export JOBFINDER_CONCURRENCY="3"
```

### 10.3 Security & secrets

There are **no API keys** in Stage 2. When Stage 3 adds optional APIs (e.g. Google Programmable Search for discovery), secrets must be provided via environment variables and **never committed**. An `.env.example` is provided as a template.

---

## 11. How crawling works

### 11.1 The request pipeline

For each seed URL, the engine:

1. **Counts against `max_total_pages`.** If exceeded, the URL is skipped.
2. **Validates safety** with `is_safe_url()` — see §16.
3. **Checks `robots.txt`** via `RobotsCache.allowed(url)`.
4. **Acquires the per-host semaphore** and **waits for the per-host delay**.
5. **Fetches with retry** using `tenacity`:
   - Retries on `aiohttp.ClientError` and `asyncio.TimeoutError`.
   - Exponential backoff with jitter, capped at 10 seconds.
   - `reraise=True` so the final failure propagates.
6. **Follows redirects** (max 5), re-checking safety on the final URL.
7. **Validates content-type** (must be `text/html` or `application/json`).
8. **Enforces size limits** — both `Content-Length` and streamed size.
9. **Decodes** as UTF-8 with replacement.
10. **Passes to the adapter registry.**

### 11.2 Retry semantics

- Only **transient** failures are retried (network errors, timeouts).
- HTTP 4xx are **not** retried (they're deterministic).
- HTTP 5xx are **not** retried in Stage 2 (Stage 4 will add this). They are recorded in `stats.failures`.

### 11.3 Failure recording

Every failure is recorded:

```python
stats.failures.append({"url": "...", "reason": "http 403"})
```

Failures never abort the run. At the end, the CLI prints aggregate counts.

### 11.4 What is *not* crawled in Stage 2

- **Internal links from a careers page** are not followed. Each seed is treated as a single page. Stage 3's discovery module will add link-following (with depth limits).
- **JavaScript-rendered pages** are not handled. They will extract zero jobs. Stage 3 adds Playwright.
- **Cross-host redirects** are followed only if the final destination is safe. `is_safe_url()` blocks hops to private IPs.

---

## 12. How extraction works

### 12.1 Adapter priority

The registry is sorted by `priority` (lower first):

| Priority | Adapter | Handles |
|---|---|---|
| 10 | `schema_org` | HTML containing `ld+json` with `JobPosting` |
| 90 | `generic_html` | Everything else |

The engine tries adapters in order and **stops at the first non-empty result**. This means a page with valid JSON-LD never falls back to heuristics.

### 12.2 `schema_org` adapter

- Parses every `<script type="application/ld+json">` block.
- Flattens `@graph` and nested arrays into a linear list of dicts.
- Matches nodes whose `@type` (or any element of `@type` list) is `"JobPosting"`.
- Extracts:
  - `title` from `title` or `name`
  - `url` from `url` (resolved relative to page), falling back to the page URL
  - `hiringOrganization.name` as `company`
  - `jobLocation.address` composed of `addressLocality, addressRegion, addressCountry`
  - `jobLocationType == "TELECOMMUTE"` → `"Remote"`
  - `description` (HTML retained as text; whitespace preserved for downstream)
  - `employmentType` (URL suffix extracted, e.g. `"https://schema.org/FULL_TIME"` → `"FULL_TIME"`)
  - `baseSalary.value.value` + `unitText` composed as a string
  - `datePosted`
  - `identifier` (either a scalar or `{"value": "..."}`)

**Malformed JSON is skipped silently** — a bad `ld+json` block does not fail the page.

### 12.3 `generic_html` adapter

This adapter is **deliberately pessimistic** — it must emit a job **only when the page really looks like a job page**, because false positives are worse than false negatives.

It requires **all** of the following:

1. A non-empty `h1` (or `<title>` fallback).
2. The **URL matches** a job-ish pattern (`/jobs/`, `/careers/{slug}/`, `/positions/`, etc.) **OR** the **title matches** a role-ish pattern (`engineer|developer|analyst|manager|...`).
3. The page text contains `"apply"` **or** `"job description"`.

If any check fails, it returns `[]`.

When it does emit a `RawJob`:
- `title` = `h1` (preferred) or `<title>`
- `company` = `og:site_name` if present
- `description` = text of `<main>` or `<article>` or `<body>`, first 20,000 characters
- `source` = `"generic_html"` (a signal downstream that confidence is lower)

### 12.4 Limitations of Stage 2 extraction

- **No pagination handling.** A careers page listing 10 jobs on page 1 will yield those 10 jobs only.
- **No per-job detail pages.** The generic adapter extracts the page it's on, not the pages it links to.
- **No JS rendering.** React/Vue SPAs will yield zero jobs unless they also emit JSON-LD in the initial HTML (some do, most don't).

These are explicitly Stage 3 concerns.

---

## 13. How matching works

### 13.1 Query parsing

`matching/parser.py` turns a raw query into a `SearchQuery`:

- **Title tokens:** words of length > 2 from the query.
- **Must-have skills:** intersections with a curated list (`python`, `fastapi`, `django`, `sql`, `react`, `kubernetes`, `pytorch`, etc. — ~40 terms).
- **Seniority:** regex match against `intern | junior | mid | senior | lead`.
- **Exclusions:** regex match for `excluding X | without X | no X | not X`.

This is intentionally conservative. An unrecognised skill is not guessed.

### 13.2 Scoring model

The scorer is fully deterministic. Every contribution is logged.

| Signal | Contribution | Notes |
|---|---|---|
| **Title tokens matched** | `+10 × hits`, capped at **+35** | Title matches are the strongest signal |
| **Must-have skills found** | `+30 × (found / total)` | If `must_have_skills` is empty, no bonus or penalty |
| **Missing must-have skills** | `−5 × missing` | Penalty accumulates linearly |
| **Seniority match** (title or first 2000 chars of description) | **+15** | Only if `seniority` is set |
| **Remote** (work arrangement or mention) | **+20** | Only if `--remote` given |
| **Location** (substring in title + description + location) | **+15** | Only if `--location` given |
| **Exclusion term present** | **−25 per term** | Any excluded term reduces the score |
| **Status `expired`** | **−40** | (Stage 4 will set this properly) |
| **Unpaid internship** | **−20** | Detected from description |
| **Final normalisation** | Clamp to `[0, 100]` | Below `min_score` → dropped |

### 13.3 Reasons

Every contribution appends a human-readable reason to `JobMatch.reasons`:

```
"title matches ['backend', 'engineer'] (+20)"
"skills present: ['python', 'fastapi'] (+30)"
"missing skills: ['rust'] (-5)"
"remote work mentioned (+20)"
"excluded term 'internship' present (-25)"
```

A `JobMatch` is **only** returned if at least one reason is produced. This prevents single-keyword false positives (e.g., a page with "Python" mentioned once in a boilerplate footer) from flooding results.

### 13.4 Re-ranking stored jobs

`jobfinder search` scores **the entire stored database**, not just the current run. This means:

```bash
# First run: crawl and score
jobfinder search --query "backend Python" --seeds-file seeds.txt

# Second run: no new seeds needed; re-score with a different query
jobfinder search --query "machine learning" --seed https://example.com/noop
```

(A future `--db-only` flag will remove the requirement for at least one seed.)

---

## 14. How deduplication works

Duplicate detection uses **two keys**:

### 14.1 Canonical URL

`canonicalize_url()`:

- Lowercases scheme and host.
- Drops the fragment.
- Removes tracking parameters: `utm_*`, `gclid`, `fbclid`, `ref`.
- Preserves path, params, and remaining query.

Two URLs that differ only in `?utm_source=` are treated as one.

### 14.2 Dedupe hash

```python
sha256(canonical_url | company | title | location)
```

All components are lowercased and stripped.

The hash is stored in `jobs.dedupe_key` with a **UNIQUE constraint**. An upsert attempt with an existing key **updates** the existing row (bumping `last_seen`) instead of inserting.

### 14.3 What this catches and does not catch

**Catches:**
- Same job re-crawled on a later run.
- Same job posted to two boards with identical title/location.
- Same URL with different tracking params.

**Does not catch:**
- Same job with slightly different titles ("Backend Engineer" vs. "Software Engineer, Backend") — a deliberate design choice, since these *may* be genuinely different openings.
- Same job at the same company in different cities.

When in doubt, the system prefers **false negatives over false positives** in dedupe.

---

## 15. How persistence works

### 15.1 Schema

```sql
CREATE TABLE jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_url TEXT NOT NULL,
    dedupe_key TEXT NOT NULL UNIQUE,
    payload TEXT NOT NULL,          -- JobPosting serialised as JSON
    first_seen TEXT NOT NULL,       -- ISO 8601
    last_seen TEXT NOT NULL
);
CREATE INDEX idx_jobs_canonical ON jobs(canonical_url);

CREATE TABLE run_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    finished_at TEXT NOT NULL,
    payload TEXT NOT NULL           -- CrawlStats serialised as JSON
);
```

### 15.2 Design choices

- **Payload as JSON.** Storing the full `JobPosting` serialised means the schema can evolve without migrations. Pydantic handles validation on read.
- **`first_seen` / `last_seen`.** Enables incremental crawling (Stage 4) to skip recently-verified jobs.
- **No separate `skills` / `locations` tables.** Deliberately denormalised for MVP simplicity. Normalisation is a Stage 4 concern.
- **`run_stats` table.** Every CLI invocation records a stats row. Useful for auditing.

### 15.3 Migrating to PostgreSQL

The repository class isolates all SQL. To move to PostgreSQL:

1. Replace `sqlite3.connect` with `psycopg` or `asyncpg`.
2. Change `AUTOINCREMENT` to `SERIAL` / `GENERATED ALWAYS AS IDENTITY`.
3. Replace `?` placeholders with `%s`.
4. Everything else — models, scoring, export — is unchanged.

---

## 16. Safety, ethics, and compliance

### 16.1 SS