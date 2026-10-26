"""Command-line interface."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from job_finder.config import CrawlConfig
from job_finder.crawler.engine import CrawlEngine
from job_finder.exports import csv_export, json_export
from job_finder.matching.parser import parse_query
from job_finder.matching.scorer import score_job
from job_finder.models import JobMatch
from job_finder.storage.database import JobRepository

log = logging.getLogger("jobfinder")


def _cmd_search(args: argparse.Namespace) -> int:
    cfg = CrawlConfig.from_env()
    if args.database:
        cfg.database_path = args.database
    if args.no_robots:
        cfg.respect_robots = False

    seeds = [line.strip() for line in args.seeds if line.strip()]
    if not seeds and args.seeds_file:
        with open(args.seeds_file, encoding="utf-8") as fh:
            seeds = [line.strip() for line in fh if line.strip()]
    if not seeds:
        print("error: provide at least one seed URL via --seed or --seeds-file",
              file=sys.stderr)
        return 2

    query = parse_query(
        args.query, location=args.location,
        remote_ok=args.remote, min_score=args.min_score,
    )

    engine = CrawlEngine(cfg)
    jobs = asyncio.run(engine.crawl(seeds))

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
    p.add_argument("--database", default=None)
    p.add_argument("--csv")
    p.add_argument("--json-out")
    p.add_argument("--no-robots", action="store_true")
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