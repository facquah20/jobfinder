"""JSON export of JobMatch results."""

from __future__ import annotations

import json
from pathlib import Path

from job_finder.models import JobMatch


def export(matches: list[JobMatch], path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    payload = [
        {
            "score": m.score,
            "reasons": m.reasons,
            "job": m.job.model_dump(mode="json"),
        }
        for m in matches
    ]
    Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")