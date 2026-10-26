import csv
import json
from datetime import datetime, timezone

from job_finder.exports import csv_export, json_export
from job_finder.models import JobMatch, JobPosting


def _match():
    job = JobPosting(title="Engineer", url="https://x.example/j/1",
                     company="X", discovered_at=datetime.now(timezone.utc))
    return JobMatch(job=job, score=42.0, reasons=["title match"])


def test_csv_export(tmp_path):
    path = tmp_path / "out.csv"
    csv_export.export([_match()], str(path))
    rows = list(csv.DictReader(path.open()))
    assert rows[0]["title"] == "Engineer"
    assert rows[0]["score"] == "42.0"


def test_json_export(tmp_path):
    path = tmp_path / "out.json"
    json_export.export([_match()], str(path))
    data = json.loads(path.read_text())
    assert data[0]["job"]["title"] == "Engineer"
    assert data[0]["score"] == 42.0