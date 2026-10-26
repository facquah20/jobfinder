"""CSV export of JobMatch results."""

from __future__ import annotations

import csv
from pathlib import Path

from job_finder.models import JobMatch

_COLUMNS = [
    "title", "company", "url", "location", "work_arrangement",
    "employment_type", "posting_date", "score", "reasons", "status",
    "source", "discovered_at",
]


def export(matches: list[JobMatch], path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=_COLUMNS)
        writer.writeheader()
        for m in matches:
            writer.writerow({
                "title": m.job.title,
                "company": m.job.company or "",
                "url": m.job.url,
                "location": m.job.location or "",
                "work_arrangement": m.job.work_arrangement.value,
                "employment_type": m.job.employment_type.value,
                "posting_date": m.job.posting_date or "",
                "score": f"{m.score:.1f}",
                "reasons": "; ".join(m.reasons),
                "status": m.job.status.value,
                "source": m.job.source,
                "discovered_at": m.job.discovered_at.isoformat(),
            })