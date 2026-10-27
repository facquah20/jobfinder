"""Command-line interface."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

import aiohttp

from job_finder.config import CrawlConfig
from job_finder.crawler.engine import CrawlEngine, PlaywrightSetupError
from job_finder.discovery.company_discovery import discover_career_pages
from job_finder.discovery.search_sources import GoogleCustomSearchSource
from job_finder.exports import csv_export, json_export
from job_finder.matching.parser import parse_query
from job_finder.matching.scorer import score_job
from job_finder.models import JobMatch
from job_finder.storage.database import JobRepository

log = logging.getLogger("jobfinder")


async def _discover_company_seeds(
    companies: list[str], cfg: CrawlConfig
) -> dict[str, list[str]]:
    timeout = aiohttp.ClientTimeout(total=cfg.request_timeout_seconds)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        source = GoogleCustomSearchSource(
            session,
            cfg.google_search_api_key or "",
            cfg.google_search_engine_id or "",
        )
        return await discover_career_pages(companies, source)


def _cmd_search(args: argparse.Namespace) -> int:
    cfg = CrawlConfig.from_env()
    if args.database:
        cfg.database_path = args.database
    if args.no_robots:
        cfg.respect_robots = False
    if args.playwright:
        cfg.playwright_fallback = True

    seeds = [line.strip() for line in args.seed if line.strip()]
    if not seeds and args.seeds_file:
        with open(args.seeds_file, encoding="utf-8") as fh:
            seeds = [line.strip() for line in fh if line.strip()]
    companies = [company.strip() for company in args.company if company.strip()]
    if not seeds and not companies:
        print("error: provide a seed URL, --seeds-file, or --company",
              file=sys.stderr)
        return 2

    if companies:
        if not cfg.google_search_api_key or not cfg.google_search_engine_id:
            print(
                "error: --company requires JOBFINDER_GOOGLE_API_KEY and "
                "JOBFINDER_GOOGLE_CSE_ID",
                file=sys.stderr,
            )
            return 2
        try:
            discovered = asyncio.run(_discover_company_seeds(companies, cfg))
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
            log.error("company discovery failed: %s", exc)
            return 1
        for company, urls in discovered.items():
            if urls:
                print(f"discovered careers pages for {company}: {', '.join(urls)}")
                seeds.extend(urls)
        if not seeds:
            print("error: no careers pages found for the requested companies",
                  file=sys.stderr)
            return 1

    query = parse_query(
        args.query, location=args.location,
        remote_ok=args.remote, min_score=args.min_score,
    )

    engine = CrawlEngine(cfg)
    try:
        jobs = asyncio.run(engine.crawl(seeds))
    except PlaywrightSetupError as exc:
        log.error("%s", exc)
        return 1

    repo = JobRepository(cfg.database_path)
    inserted, updated = repo.upsert_many(jobs)
    print(f"crawled: fetched={engine.stats.pages_fetched} "
          f"robots_skipped={engine.stats.pages_skipped_robots} "
          f"failed={engine.stats.pages_failed} "
          f"extracted={engine.stats.jobs_extracted}")

    stored = repo.all()
    matches: list[JobMatch] = []
    for job in stored:
        m = score_job(job, query)
        if m is not None:
            matches.append(m)
    matches.sort(key=lambda m: m.score, reverse=True)
    if args.limit:
        matches = matches[: args.limit]

    for m in matches:
        print(f"[{m.score:5.1f}] {m.job.title} — {m.job.company or '?'}")
        print(f"        {m.job.url}")
        print(f"        {m.job.location or 'location unknown'} | "
              f"{m.job.work_arrangement.value} | {m.job.status.value}")
        print(f"        why: {'; '.join(m.reasons)}")

    if args.csv:
        csv_export.export(matches, args.csv)
        print(f"wrote CSV: {args.csv}")
    if args.json_out:
        json_export.export(matches, args.json_out)
        print(f"wrote JSON: {args.json_out}")

    repo.record_stats(engine.stats.model_dump())
    repo.close()
    return 0


def _cmd_stats(args: argparse.Namespace) -> int:
    repo = JobRepository(args.database)
    jobs = repo.all()
    print(f"stored jobs: {len(jobs)}")
    by_source: dict[str, int] = {}
    for j in jobs:
        by_source[j.source] = by_source.get(j.source, 0) + 1
    for src, n in sorted(by_source.items()):
        print(f"  {src}: {n}")
    repo.close()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="jobfinder")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("search", help="Crawl seeds, rank, and export matches")
    p.add_argument("--query", required=True)
    p.add_argument("--location", default=None)
    p.add_argument("--remote", action="store_true")
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--min-score", type=float, default=0.0)
    p.add_argument("--seed", action="append", default=[],
                   help="Career-page URL (repeatable)")
    p.add_argument("--seeds-file", help="Text file, one URL per line")
    p.add_argument("--company", action="append", default=[],
                   help="Company name to discover careers pages for (repeatable)")
    p.add_argument("--database", default=None)
    p.add_argument("--csv")
    p.add_argument("--json-out")
    p.add_argument("--no-robots", action="store_true")
    p.add_argument("--playwright", action="store_true",
                   help="Render pages with Playwright when static extraction finds no jobs")
    p.add_argument("--verbose", action="store_true")
    p.set_defaults(func=_cmd_search)

    s = sub.add_parser("stats", help="Show stored job counts")
    s.add_argument("--database", default="jobfinder.sqlite3")
    s.set_defaults(func=_cmd_stats)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if getattr(args, "verbose", False) else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())