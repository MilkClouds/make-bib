#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "httpx",
#     "rich",
#     "python-dotenv",
# ]
# ///
"""Fetch paper metadata from multiple academic sources and present raw results.

This tool fetches and presents. It never judges.
For each source, it shows: where it asked, what it asked, and what came back.
Run with --help for full usage, source descriptions, and output format details.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from typing import Any

import httpx
from dotenv import load_dotenv
from rich.console import Console

load_dotenv()

# -- Type alias: each source returns this structure --
# {
#   "request":  {"url": str, "params": dict},       # what was asked
#   "response": {... source-specific raw fields},    # what came back
#   "error":    str | None,                          # if it failed
#   "status":   "ok" | "no_match" | "error" | "skipped",
#   "skip_reason": str | None,                       # why skipped
# }
SourceData = dict[str, Any]


# =============================================================================
# Helpers
# =============================================================================


def _normalize_paper_id(paper_id: str) -> str:
    """Add ARXIV: prefix to bare arXiv IDs."""
    if ":" in paper_id or "/" in paper_id:
        return paper_id
    if re.match(r"^\d{4}\.\d{4,5}(v\d+)?$", paper_id):
        return f"ARXIV:{paper_id}"
    return paper_id


def _titles_match(t1: str, t2: str) -> bool:
    """Fuzzy title match: ignore punctuation and case."""

    def norm(t: str) -> str:
        return " ".join(re.sub(r"[^\w\s]", " ", t.lower()).split())

    return norm(t1) == norm(t2)


def _get(client: httpx.Client, url: str, *, headers: dict | None = None, **kwargs: Any) -> httpx.Response | None:
    """GET with retry on 429. Returns None on 404/410. Raises on other errors."""
    hdrs = headers or {}
    for attempt in range(3):
        resp = client.get(url, headers=hdrs, **kwargs)
        if resp.status_code in (404, 410):
            return None
        if resp.status_code == 429:
            wait = (attempt + 1) * 5
            print(f"  Rate limited ({url[:60]}…), retrying in {wait}s…", file=sys.stderr)
            time.sleep(wait)
            continue
        resp.raise_for_status()
        return resp
    return None


def _skipped(name: str, reason: str) -> SourceData:
    return {"source": name, "status": "skipped", "skip_reason": reason}


def _error(name: str, request: dict, err: str) -> SourceData:
    return {"source": name, "request": request, "status": "error", "error": err}


# =============================================================================
# Semantic Scholar (ID resolution)
# =============================================================================

_S2_BASE = "https://api.semanticscholar.org/graph/v1"
_S2_FIELDS = "paperId,externalIds,venue,title"


def _s2_headers() -> dict[str, str]:
    key = os.environ.get("SEMANTIC_SCHOLAR_API_KEY")
    return {"x-api-key": key} if key else {}


def resolve_s2(client: httpx.Client, paper_id: str) -> SourceData:
    """Resolve a paper ID to external IDs via Semantic Scholar."""
    normalized = _normalize_paper_id(paper_id)
    url = f"{_S2_BASE}/paper/{normalized}"
    params = {"fields": _S2_FIELDS}
    req = {"url": url, "params": params}

    try:
        resp = _get(client, url, headers=_s2_headers(), params=params)
    except httpx.HTTPError as e:
        return _error("semantic_scholar", req, str(e))
    if not resp:
        return _error("semantic_scholar", req, "not found")

    data = resp.json()
    return {
        "source": "semantic_scholar",
        "request": req,
        "status": "ok",
        "response": data,
    }


# =============================================================================
# CrossRef
# =============================================================================


def fetch_crossref(client: httpx.Client, doi: str, *, raw: bool = False) -> SourceData:
    doi = doi.removeprefix("DOI:").removeprefix("doi:")
    url = f"https://api.crossref.org/works/{doi}"
    req = {"url": url}

    try:
        ua = "paper_sources/0.1 (https://github.com/bibtools)"
        email = os.environ.get("CROSSREF_EMAIL")
        if email:
            ua += f" (mailto:{email})"
        resp = _get(client, url, headers={"User-Agent": ua})
    except httpx.HTTPError as e:
        return _error("crossref", req, str(e))
    if not resp:
        return {"source": "crossref", "request": req, "status": "no_match"}

    msg = resp.json().get("message", {})
    if raw:
        response = msg
    else:
        response = {
            "title": msg.get("title"),
            "author": msg.get("author"),
            "published": msg.get("published"),
            "issued": msg.get("issued"),
            "container-title": msg.get("container-title"),
            "DOI": msg.get("DOI"),
            "type": msg.get("type"),
            "page": msg.get("page"),
            "volume": msg.get("volume"),
            "issue": msg.get("issue"),
            "publisher": msg.get("publisher"),
        }
    return {
        "source": "crossref",
        "request": req,
        "status": "ok",
        "response": response,
    }


# =============================================================================
# DBLP
# =============================================================================


def fetch_dblp(client: httpx.Client, title: str, venue: str | None = None, *, raw: bool = False) -> SourceData:
    if not title:
        return _skipped("dblp", "no title")

    queries = [f"{title} {venue}", title] if venue else [title]
    last_req: dict = {}

    last_error: str | None = None
    for query in queries:
        url = "https://dblp.org/search/publ/api"
        params = {"q": query, "format": "json", "h": 10}
        last_req = {"url": url, "params": params}

        try:
            resp = _get(client, url, params=params)
            if not resp:
                last_error = "not found"
                continue
        except httpx.HTTPError as e:
            last_error = str(e)
            continue  # try next query variant

        last_error = None
        hits = resp.json().get("result", {}).get("hits", {}).get("hit", [])
        for hit in hits:
            info = hit.get("info", {})
            hit_title = (info.get("title") or "").rstrip(".")
            if _titles_match(title, hit_title):
                return {
                    "source": "dblp",
                    "request": last_req,
                    "status": "ok",
                    "response": hit if raw else info,
                }

    if last_error:
        return _error("dblp", last_req, last_error)
    return {"source": "dblp", "request": last_req, "status": "no_match"}


# =============================================================================
# arXiv (Atom API)
# =============================================================================

_ARXIV_NS = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}


def fetch_arxiv(client: httpx.Client, arxiv_id: str, *, raw: bool = False) -> SourceData:  # noqa: ARG001
    arxiv_id = arxiv_id.upper().removeprefix("ARXIV:").lower()
    if "v" in arxiv_id:
        arxiv_id = arxiv_id.rsplit("v", 1)[0]

    url = "https://export.arxiv.org/api/query"
    params = {"id_list": arxiv_id, "max_results": "1"}
    req = {"url": url, "params": params}

    try:
        resp = client.get(url, params=params)
        resp.raise_for_status()
    except httpx.HTTPError as e:
        return _error("arxiv", req, str(e))

    root = ET.fromstring(resp.text)
    entry = root.find("atom:entry", _ARXIV_NS)
    if entry is None:
        return _error("arxiv", req, "no entry in response")

    entry_id = entry.findtext("atom:id", "", _ARXIV_NS)
    if "error" in entry_id.lower():
        return _error("arxiv", req, f"arxiv error: {entry_id}")

    # Extract structured data from XML (but don't normalize — keep close to source)
    authors = [
        el.findtext("atom:name", "", _ARXIV_NS)
        for el in entry.findall("atom:author", _ARXIV_NS)
    ]
    categories = []
    for tag in ("arxiv:primary_category", "atom:category"):
        for el in entry.findall(tag, _ARXIV_NS):
            if (term := el.get("term")) and term not in categories:
                categories.append(term)

    return {
        "source": "arxiv",
        "request": req,
        "status": "ok",
        "response": {
            "id": entry_id,
            "title": " ".join((entry.findtext("atom:title", "", _ARXIV_NS) or "").split()),
            "authors": authors,
            "published": entry.findtext("atom:published", "", _ARXIV_NS),
            "updated": entry.findtext("atom:updated", "", _ARXIV_NS),
            "summary": (entry.findtext("atom:summary", "", _ARXIV_NS) or "").strip(),
            "categories": categories,
            "comment": entry.findtext("arxiv:comment", None, _ARXIV_NS),
        },
    }


# =============================================================================
# OpenReview (v1 search + v2 fallback)
# =============================================================================


def _or_val(content: dict, key: str) -> Any:
    """Extract value from OpenReview content field (handles both v1 plain and v2 {value: …} wrapper)."""
    v = content.get(key)
    return v.get("value") if isinstance(v, dict) else v


def fetch_openreview(client: httpx.Client, title: str, *, raw: bool = False) -> SourceData:
    if not title:
        return _skipped("openreview", "no title")

    last_req: dict = {}
    for base in ("https://api.openreview.net", "https://api2.openreview.net"):
        url = f"{base}/notes/search"
        params = {"query": title, "limit": "5", "source": "forum"}
        last_req = {"url": url, "params": params}

        try:
            resp = _get(client, url, params=params)
            if not resp:
                continue
        except httpx.HTTPError:
            continue

        for note in resp.json().get("notes", []):
            content = note.get("content", {})
            note_title = _or_val(content, "title")
            if note_title and _titles_match(title, note_title):
                if raw:
                    response = note
                else:
                    response: dict[str, Any] = {}
                    for key in ("title", "authors", "venue", "venueid", "_bibtex", "abstract", "keywords", "TL;DR"):
                        val = _or_val(content, key)
                        if val:
                            response[key] = val
                    response["id"] = note.get("id")
                    response["forum"] = note.get("forum")
                    response["invitation"] = (note.get("invitations") or [note.get("invitation")])[0]
                    response["url"] = f"https://openreview.net/forum?id={note.get('id', '')}"
                return {
                    "source": "openreview",
                    "request": last_req,
                    "status": "ok",
                    "response": response,
                }

    return {"source": "openreview", "request": last_req, "status": "no_match"}


# =============================================================================
# ACL Anthology
# =============================================================================


def fetch_acl(client: httpx.Client, acl_id: str, *, raw: bool = False) -> SourceData:  # noqa: ARG001
    if not acl_id:
        return _skipped("acl_anthology", "no acl_id")

    url = f"https://aclanthology.org/{acl_id}.bib"
    req = {"url": url}

    try:
        resp = client.get(url, follow_redirects=True)
        if resp.status_code == 404:
            return {"source": "acl_anthology", "request": req, "status": "no_match"}
        resp.raise_for_status()
    except httpx.HTTPError as e:
        return _error("acl_anthology", req, str(e))

    # Return raw BibTeX — don't parse it into fields
    return {
        "source": "acl_anthology",
        "request": req,
        "status": "ok",
        "response": {"bibtex": resp.text.strip()},
    }


# =============================================================================
# Orchestrator
# =============================================================================

# Source metadata: helps AI agents understand what each source provides and how to interpret it
_SOURCE_META: dict[str, dict[str, str]] = {
    "dblp": {
        "description": "Bibliographic database. Provides venue short name, year, entry type, author disambiguation.",
        "docs": "https://dblp.org/faq/How+to+use+the+dblp+search+API.html",
        "key_fields": "venue, year, type, key, ee (external URL)",
    },
    "crossref": {
        "description": "Publisher metadata via DOI. Provides container-title (journal/proceedings name), author with affiliations, page, volume.",
        "docs": "https://api.crossref.org/swagger-ui/index.html",
        "key_fields": "container-title, author, type, page, volume, publisher",
    },
    "openreview": {
        "description": "Conference submission platform. Provides venue with acceptance type (Oral/Spotlight/Poster), BibTeX, keywords, reviews.",
        "docs": "https://docs.openreview.net/reference/api-v1/notes/search",
        "key_fields": "venue, venueid, _bibtex, keywords, invitation",
    },
    "acl_anthology": {
        "description": "Authoritative source for ACL venues (ACL, EMNLP, NAACL, etc). Returns complete, copy-ready BibTeX.",
        "docs": "https://aclanthology.org/info/contributing/",
        "key_fields": "bibtex (complete @inproceedings with booktitle, pages, doi)",
    },
    "arxiv": {
        "description": "Preprint server. Provides categories, submission/update dates, author comments. Least authoritative for published papers.",
        "docs": "https://info.arxiv.org/help/api/index.html",
        "key_fields": "categories, published, updated, comment",
    },
}

# (name, fetch_fn, fields_from_ids) — first field is required, rest are optional
_SOURCES: list[tuple[str, Any, tuple[str, ...]]] = [
    ("dblp", fetch_dblp, ("title", "venue")),
    ("crossref", fetch_crossref, ("doi",)),
    ("openreview", fetch_openreview, ("title",)),
    ("acl_anthology", fetch_acl, ("acl_id",)),
    ("arxiv", fetch_arxiv, ("arxiv_id",)),
]

ALL_SOURCES = [name for name, _, _ in _SOURCES]


def _extract_ids(s2_data: dict) -> dict[str, str | None]:
    """Extract external IDs from S2 response into a flat lookup."""
    ext = s2_data.get("externalIds") or {}
    return {
        "doi": ext.get("DOI"),
        "arxiv_id": ext.get("ArXiv"),
        "acl_id": ext.get("ACL"),
        "title": s2_data.get("title"),
        "venue": s2_data.get("venue"),
    }


def fetch_all(
    paper_id: str, log: Console, *, sources: list[str] | None = None, raw: bool = False,
) -> list[SourceData]:
    """Resolve paper ID, then fetch from all applicable sources. Returns list of SourceData."""
    enabled = sources or ALL_SOURCES
    results: list[SourceData] = []

    with httpx.Client(timeout=30.0) as client:
        # Step 1: Resolve IDs via Semantic Scholar
        log.print(f"[dim]Resolving {paper_id} via Semantic Scholar…[/]")
        s2 = resolve_s2(client, paper_id)
        results.append(s2)

        if s2["status"] != "ok":
            log.print(f"[red]  Failed: {s2.get('error', 'unknown')}[/]")
            return results

        ids = _extract_ids(s2["response"])
        log.print(f"[dim]  → DOI={ids['doi'] or '—'}  arXiv={ids['arxiv_id'] or '—'}  "
                  f"venue={ids['venue'] or '—'}  ACL={ids['acl_id'] or '—'}[/]")
        log.print()

        # Step 2: Fetch from each enabled source
        for name, fetch_fn, fields in _SOURCES:
            if name not in enabled:
                results.append(_skipped(name, "disabled"))
                log.print(f"  [dim]{name}: skipped (disabled)[/]")
                continue

            args = [ids.get(f) for f in fields]
            if not args[0]:  # first field is required
                results.append(_skipped(name, f"no {fields[0]}"))
                log.print(f"  [dim]{name}: skipped (no {fields[0]})[/]")
                continue

            log.print(f"  [dim]{name}: fetching…[/]", end="")
            result = fetch_fn(client, *args, raw=raw)
            results.append(result)

            status = result["status"]
            if status == "ok":
                log.print(" [green]ok[/]")
            elif status == "no_match":
                log.print(" [yellow]no match[/]")
            else:
                log.print(f" [red]{result.get('error', 'error')}[/]")

    return results


# =============================================================================
# Display: Rich (human-readable)
# =============================================================================


def _format_url(req: dict) -> str:
    url = req.get("url", "")
    params = req.get("params")
    if params:
        return url + "?" + "&".join(f"{k}={v}" for k, v in params.items())
    return url


def _print_json(console: Console, data: Any) -> None:
    """Print prettified JSON with syntax highlighting."""
    console.print_json(json.dumps(data, ensure_ascii=False))


def display_rich(results: list[SourceData], console: Console) -> None:
    console.print()

    # S2 is the ID resolver — show as preamble, not a regular source
    s2 = results[0] if results and results[0]["source"] == "semantic_scholar" else None
    sources = results[1:] if s2 else results

    if s2:
        if s2["status"] == "ok":
            resp = s2.get("response", {})
            console.print("[bold]Resolved via Semantic Scholar[/]")
            console.print(f"  [dim]GET {_format_url(s2.get('request', {}))}[/]")
            console.print()
            console.print(f"  [cyan]title[/]:  {resp.get('title', '—')}")
            console.print(f"  [cyan]venue[/]:  {resp.get('venue', '—')}")
            ids = resp.get("externalIds", {})
            for k, v in ids.items():
                console.print(f"  [cyan]{k}[/]:  {v}")
        else:
            console.print(f"[bold red]Semantic Scholar: {s2.get('error', 'resolution failed')}[/]")
            console.print(f"  [dim]GET {_format_url(s2.get('request', {}))}[/]")
        console.print()

    for data in sources:
        status = data["status"]

        if status == "skipped":
            continue

        name = data["source"]

        if status == "ok":
            console.rule(f"[bold green]{name}[/bold green]")
        elif status == "no_match":
            console.rule(f"[bold yellow]{name} (no match)[/bold yellow]")
        else:
            console.rule(f"[bold red]{name} (error)[/bold red]")

        req = data.get("request", {})
        if req:
            console.print(f"  [dim]GET {_format_url(req)}[/]")

        if data.get("error"):
            console.print(f"\n  [red]{data['error']}[/]\n")
            continue

        resp = data.get("response", {})
        if resp:
            console.print()
            _print_json(console, resp)

        console.print()


# =============================================================================
# Display: JSON (for AI agents)
# =============================================================================


def _clean(d: Any) -> Any:
    """Strip None values recursively for cleaner JSON output."""
    if isinstance(d, dict):
        return {k: _clean(v) for k, v in d.items() if v is not None}
    if isinstance(d, list):
        return [_clean(x) for x in d]
    return d


def _inject_meta(results: list[SourceData]) -> list[SourceData]:
    """Add source metadata (description, docs, key_fields) to each result."""
    enriched = []
    for data in results:
        name = data.get("source", "")
        meta = _SOURCE_META.get(name)
        if meta and data.get("status") not in ("skipped",):
            data = {**data, "_meta": meta}
        enriched.append(data)
    return enriched


def display_json(results: list[SourceData]) -> None:
    """JSON output with source metadata for AI agents."""
    enriched = _inject_meta(results)
    print(json.dumps(_clean(enriched), indent=2, ensure_ascii=False))


def display_raw(results: list[SourceData], source_name: str) -> None:
    """Structured output for --raw: S2 resolution + the one requested source + schema."""
    s2 = results[0] if results and results[0]["source"] == "semantic_scholar" else None
    target = next((r for r in results if r["source"] == source_name and r["status"] != "skipped"), None)

    output: dict[str, Any] = {}

    if s2 and s2["status"] == "ok":
        resp = s2["response"]
        output["resolved"] = {
            "title": resp.get("title"),
            "venue": resp.get("venue"),
            "ids": resp.get("externalIds"),
        }

    if target:
        meta = _SOURCE_META.get(source_name, {})
        output["api"] = {
            "endpoint": target.get("request", {}).get("url"),
            "params": target.get("request", {}).get("params"),
            "docs": meta.get("docs"),
            "description": meta.get("description"),
            "key_fields": meta.get("key_fields"),
        }
        output["status"] = target["status"]
        if target.get("error"):
            output["error"] = target["error"]
        if target.get("response"):
            output["response"] = target["response"]
    else:
        output["status"] = "unavailable"
        output["error"] = f"Could not fetch from {source_name} (missing required ID)"

    print(json.dumps(_clean(output), indent=2, ensure_ascii=False))


# =============================================================================
# CLI
# =============================================================================


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch paper metadata from multiple academic sources and present raw results.\n"
        "Resolves paper IDs via Semantic Scholar, then queries each source independently.\n"
        "No normalization or judgment — raw data for human or AI agent decision-making.",
        epilog=(
            "examples:\n"
            "  %(prog)s 2010.11929                         # arXiv ID → fetch all sources\n"
            "  %(prog)s 10.18653/v1/N19-1423                # DOI → fetch all sources\n"
            "  %(prog)s --json 1706.03762                   # JSON for piping to AI agent\n"
            "  %(prog)s --sources dblp,arxiv 2010.11929     # only specific sources\n"
            "  %(prog)s --raw crossref 10.18653/v1/N19-1423 # full raw CrossRef API response\n"
            "\n"
            "sources (in display order):\n"
            "  dblp           bibliographic DB — venue, year, type, author disambiguation\n"
            "  crossref       publisher metadata via DOI — container-title, author, page, volume\n"
            "  openreview     conference submissions — venue+acceptance type, BibTeX, keywords\n"
            "  acl_anthology  authoritative ACL venue BibTeX (ACL, EMNLP, NAACL, etc.)\n"
            "  arxiv          preprint metadata — categories, dates, comments (least authoritative)\n"
            "\n"
            "environment variables:\n"
            "  SEMANTIC_SCHOLAR_API_KEY  higher rate limits for S2 ID resolution\n"
            "  CROSSREF_EMAIL           polite pool with better rate limits (any valid email)"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "paper_id",
        help="paper identifier: arXiv ID (2010.11929), DOI (10.18653/v1/N19-1423), "
        "or Semantic Scholar ID (ARXIV:2010.11929, DOI:10.xxx, CorpusId:12345)",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="output as JSON array. each element has: source, status (ok|no_match|error|skipped), "
        "request ({url, params} — reproducible via GET), response (source-specific raw data), "
        "and _meta ({description, docs, key_fields} per source). "
        "first element is always semantic_scholar (ID resolver)",
    )
    parser.add_argument(
        "--sources",
        help=f"comma-separated list of sources to query (default: all). choices: {','.join(ALL_SOURCES)}",
    )
    parser.add_argument(
        "--raw", metavar="SOURCE",
        help="fetch full unfiltered API response from one source as JSON. "
        "output: {resolved (title/venue/ids from S2), api (endpoint/params/docs — "
        "reproducible via GET endpoint?params), status, response (raw API body)}. "
        f"choices: {','.join(ALL_SOURCES)}",
    )
    args = parser.parse_args()

    sources = None
    raw = False
    if args.raw:
        if args.raw not in ALL_SOURCES:
            parser.error(f"Unknown source: {args.raw}. Choose from: {', '.join(ALL_SOURCES)}")
        sources = [args.raw]
        raw = True
    elif args.sources:
        sources = [s.strip() for s in args.sources.split(",")]
        invalid = [s for s in sources if s not in ALL_SOURCES]
        if invalid:
            parser.error(f"Unknown sources: {', '.join(invalid)}. Choose from: {', '.join(ALL_SOURCES)}")

    log = Console(stderr=True)
    results = fetch_all(args.paper_id, log, sources=sources, raw=raw)

    if raw:
        display_raw(results, args.raw)
    elif args.json:
        display_json(results)
    else:
        display_rich(results, Console())


if __name__ == "__main__":
    main()
