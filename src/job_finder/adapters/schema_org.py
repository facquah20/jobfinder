"""Extract JobPosting from schema.org JSON-LD (handles @graph, nested)."""

from __future__ import annotations

import json
from typing import Any

from bs4 import BeautifulSoup

from job_finder.adapters.base import register
from job_finder.crawler.url_utils import resolve_relative
from job_finder.models import RawJob


def _walk_jsonld(node: Any) -> list[dict[str, Any]]:
    """Flatten @graph and nested arrays into a list of dicts."""
    out: list[dict[str, Any]] = []
    if isinstance(node, dict):
        if "@graph" in node and isinstance(node["@graph"], list):
            for child in node["@graph"]:
                out.extend(_walk_jsonld(child))
        out.append(node)
    elif isinstance(node, list):
        for item in node:
            out.extend(_walk_jsonld(item))
    return out


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _first(value: Any) -> Any:
    lst = _as_list(value)
    return lst[0] if lst else None


def _location_str(job: dict[str, Any]) -> str | None:
    loc = job.get("jobLocation")
    loc = _first(loc)
    if isinstance(loc, dict):
        addr = loc.get("address")
        addr = _first(addr)
        if isinstance(addr, dict):
            parts = [addr.get("addressLocality"),
                     addr.get("addressRegion"),
                     addr.get("addressCountry")]
            parts = [str(p) for p in parts if p]
            if parts:
                return ", ".join(parts)
        if loc.get("name"):
            return str(loc["name"])
    if job.get("jobLocationType") == "TELECOMMUTE":
        return "Remote"
    return None


def _employment(value: Any) -> str | None:
    v = _first(value)
    if not v:
        return None
    if isinstance(v, str):
        return v.split("/")[-1] if "/" in v else v
    return None


class SchemaOrgAdapter:
    name = "schema_org"
    priority = 10

    def can_handle(self, url: str, html: str, content_type: str) -> bool:
        return "ld+json" in html and "JobPosting" in html

    def extract(self, url: str, html: str) -> list[RawJob]:
        soup = BeautifulSoup(html, "lxml")
        jobs: list[RawJob] = []
        for script in soup.find_all("script", type="application/ld+json"):
            text = script.string or script.get_text() or ""
            if not text.strip():
                continue
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                continue
            for node in _walk_jsonld(data):
                types = _as_list(node.get("@type"))
                if "JobPosting" not in types:
                    continue
                title = node.get("title") or node.get("name")
                if not title:
                    continue
                apply_url = _first(node.get("url")) or url
                identifier = _first(node.get("identifier"))
                if isinstance(identifier, dict):
                    identifier = identifier.get("value")
                salary = None
                sal = _first(node.get("baseSalary"))
                if isinstance(sal, dict):
                    value = _first(sal.get("value"))
                    if isinstance(value, dict):
                        salary = f"{value.get('value', '')} {value.get('unitText', '')}".strip() or None
                    elif value:
                        salary = str(value)
                jobs.append(RawJob(
                    title=str(title),
                    url=resolve_relative(url, str(apply_url)),
                    source=self.name,
                    company=_first(node.get("hiringOrganization", {})).get("name")
                        if isinstance(_first(node.get("hiringOrganization")), dict) else None,
                    location=_location_str(node),
                    description_html=str(node.get("description") or ""),
                    employment_type=_employment(node.get("employmentType")),
                    posting_date=str(node.get("datePosted")) if node.get("datePosted") else None,
                    salary=salary,
                    identifier=str(identifier) if identifier else None,
                    raw={"jsonld_type": "JobPosting"},
                ))
        return jobs


register(SchemaOrgAdapter())