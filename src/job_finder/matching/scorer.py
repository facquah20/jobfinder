"""Transparent weighted scoring. Each signal contributes points + reason."""

from __future__ import annotations

from job_finder.models import (
    EmploymentType, JobMatch, JobPosting, SearchQuery, WorkArrangement,
)


def _has(haystack: str, needle: str) -> bool:
    return needle.lower() in haystack.lower()


def score_job(job: JobPosting, query: SearchQuery) -> JobMatch | None:
    reasons: list[str] = []
    score = 0.0

    title = job.title.lower()
    desc = job.description.lower()
    full_text = f"{title} {desc} {job.location or ''}"

    # 1. Title relevance (0–35)
    title_hits = [t for t in query.title_tokens if t in title]
    if title_hits:
        pts = min(35.0, 10.0 * len(title_hits))
        score += pts
        reasons.append(f"title matches {title_hits[:5]} (+{pts:.0f})")

    # 2. Must-have skills (0–30)
    missing = [s for s in query.must_have_skills if not _has(full_text, s)]
    found = [s for s in query.must_have_skills if s not in missing]
    if found:
        pts = 30.0 * len(found) / len(query.must_have_skills)
        score += pts
        reasons.append(f"skills present: {found} (+{pts:.0f})")
    if missing:
        score -= 5.0 * len(missing)
        reasons.append(f"missing skills: {missing} (-{5 * len(missing):.0f})")

    # 3. Seniority (0–15)
    if query.seniority:
        if _has(title, query.seniority) or _has(desc[:2000], query.seniority):
            score += 15.0
            reasons.append(f"seniority '{query.seniority}' indicated (+15)")
        else:
            reasons.append(f"seniority '{query.seniority}' not indicated (+0)")

    # 4. Location / remote (0–20)
    if query.remote_ok:
        if job.work_arrangement == WorkArrangement.REMOTE or _has(full_text, "remote"):
            score += 20.0
            reasons.append("remote work mentioned (+20)")
    if query.location:
        if _has(full_text, query.location.lower()):
            score += 15.0
            reasons.append(f"location '{query.location}' mentioned (+15)")

    # 5. Exclusions (hard-ish penalty)
    for excl in query.exclusions:
        if _has(full_text, excl):
            score -= 25.0
            reasons.append(f"excluded term '{excl}' present (-25)")

    # 6. Status
    if job.status.value == "expired":
        score -= 40.0
        reasons.append("marked expired (-40)")

    # 7. Employment-type sanity: unpaid-ish interns excluded by default
    if job.employment_type == EmploymentType.INTERNSHIP and "unpaid" in desc:
        score -= 20.0
        reasons.append("unpaid internship (-20)")

    # Normalise to 0–100
    normalised = max(0.0, min(100.0, score))
    if normalised < query.min_score:
        return None
    if not reasons:
        return None
    return JobMatch(job=job, score=normalised, reasons=reasons)