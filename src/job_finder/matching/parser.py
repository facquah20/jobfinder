"""Parse a natural-language query into structured SearchQuery."""

from __future__ import annotations

import re

from job_finder.models import SearchQuery

_SENIORITY_PATTERNS = {
    "intern": r"\bintern(ship)?\b",
    "junior": r"\b(junior|entry[- ]level|graduate)\b",
    "mid": r"\b(mid[- ]level|intermediate)\b",
    "senior": r"\b(senior|staff|principal)\b",
    "lead": r"\b(lead|manager|head of)\b",
}

_KNOWN_SKILLS = [
    "python", "fastapi", "django", "flask", "postgresql", "postgres",
    "sql", "mysql", "mongodb", "redis", "javascript", "typescript",
    "react", "vue", "node", "go", "rust", "java", "kotlin", "swift",
    "aws", "gcp", "azure", "docker", "kubernetes", "terraform",
    "machine learning", "pytorch", "tensorflow", "pandas", "numpy",
    "excel", "tableau", "power bi", "git", "linux", "ci/cd",
]

_EXCLUSION = re.compile(r"(?:excluding|without|no|not)\s+([a-z0-9 +#/.]+)", re.I)


def parse_query(raw: str, location: str | None = None,
                remote_ok: bool = False, min_score: float = 0.0) -> SearchQuery:
    text = raw.lower()
    seniority = None
    for name, pattern in _SENIORITY_PATTERNS.items():
        if re.search(pattern, text):
            seniority = name
            break
    must = [s for s in _KNOWN_SKILLS if re.search(rf"\b{re.escape(s)}\b", text)]
    exclusions = [m.group(1).strip().lower() for m in _EXCLUSION.finditer(raw)]
    exclusions = [e for e in exclusions if e and e not in {"degree", "requirement"}][:10]
    tokens = [t for t in re.split(r"[^a-z0-9+#/]+", text) if len(t) > 2]
    return SearchQuery(
        raw_query=raw,
        title_tokens=tokens,
        must_have_skills=must,
        exclusions=exclusions,
        seniority=seniority,
        location=location,
        remote_ok=remote_ok,
        min_score=min_score,
    )