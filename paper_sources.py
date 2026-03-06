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
from urllib.parse import quote

import httpx
from dotenv import load_dotenv
from rich.console import Console

load_dotenv()

# -- Type alias --
SourceData = dict[str, Any]


# =============================================================================
# Helpers
# =============================================================================


def _normalize_paper_id(paper_id: str) -> str:
    """Add type prefix for Semantic Scholar API (ARXIV:, DOI:, etc.)."""
    if re.match(r"^(DOI|ARXIV|CorpusId|PMID|ACL|MAG|URL):", paper_id, re.IGNORECASE):
        return paper_id
    if "openreview.net" in paper_id:
        return f"URL:{paper_id}"
    if re.match(r"^\d{4}\.\d{4,5}(v\d+)?$", paper_id):
        return f"ARXIV:{paper_id}"
    if re.match(r"^10\.\d{4,}/", paper_id):
        return f"DOI:{paper_id}"
    return paper_id


def _extract_ids_from_input(paper_id: str) -> dict[str, str | None]:
    """Extract IDs directly from the input string, without S2."""
    ids: dict[str, str | None] = {
        "doi": None,
        "arxiv_id": None,
        "acl_id": None,
        "dblp_key": None,
        "openreview_id": None,
        "title": None,
        "venue": None,
    }
    raw = paper_id.strip()
    bare = re.sub(r"^(DOI:|doi:|ARXIV:|arxiv:)", "", raw)

    m = re.match(r"https?://openreview\.net/forum\?id=([A-Za-z0-9_-]+)", raw)
    if m:
        ids["openreview_id"] = m.group(1)
        return ids

    if re.match(r"^10\.\d{4,}/", bare):
        ids["doi"] = bare
        m = re.match(r"^10\.18653/v1/(.+)$", bare)
        if m:
            ids["acl_id"] = m.group(1)
    elif re.match(r"^\d{4}\.\d{4,5}(v\d+)?$", bare):
        ids["arxiv_id"] = bare

    return ids


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
    url = f"{_S2_BASE}/paper/{quote(normalized, safe=':/')}"
    params = {"fields": _S2_FIELDS}
    req = {"url": url, "params": params}

    try:
        resp = _get(client, url, headers=_s2_headers(), params=params)
    except httpx.HTTPError as e:
        return _error("semantic_scholar", req, str(e))
    if not resp:
        return _error("semantic_scholar", req, "not found")

    return {"source": "semantic_scholar", "request": req, "status": "ok", "response": resp.json()}


# =============================================================================
# Exact-fetch functions (ID-based, no judgment)
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
    return {"source": "crossref", "request": req, "status": "ok", "response": response}


def fetch_dblp(client: httpx.Client, dblp_key: str) -> SourceData:
    """Fetch DBLP record by exact key via XML endpoint."""
    url = f"https://dblp.org/rec/{dblp_key}.xml"
    req = {"url": url}
    try:
        resp = _get(client, url)
        if not resp:
            return {"source": "dblp", "request": req, "status": "no_match"}
    except httpx.HTTPError as e:
        return _error("dblp", req, str(e))

    root = ET.fromstring(resp.text)
    entry = root[0] if len(root) > 0 else None
    if entry is None:
        return _error("dblp", req, "empty XML response")

    info: dict[str, Any] = {"key": dblp_key, "type": entry.tag}
    authors = []
    for child in entry:
        if child.tag == "author":
            authors.append(child.text or "")
        elif child.text:
            info[child.tag] = child.text
    if authors:
        info["authors"] = {"author": [{"text": a} for a in authors]}

    return {"source": "dblp", "request": req, "status": "ok", "response": info}


_ARXIV_NS = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}


def fetch_arxiv(client: httpx.Client, arxiv_id: str, *, raw: bool = False) -> SourceData:
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

    if raw:
        return {"source": "arxiv", "request": req, "status": "ok", "response": {"xml": resp.text}}

    authors = [el.findtext("atom:name", "", _ARXIV_NS) for el in entry.findall("atom:author", _ARXIV_NS)]
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


def _or_val(content: dict, key: str) -> Any:
    """Extract value from OpenReview content field (handles both v1 plain and v2 {value: …} wrapper)."""
    v = content.get(key)
    return v.get("value") if isinstance(v, dict) else v


def _or_note_to_dict(note: dict, *, raw: bool) -> dict[str, Any]:
    """Convert an OpenReview note to a response dict."""
    content = note.get("content", {})
    if raw:
        return note
    response: dict[str, Any] = {}
    for key in ("title", "authors", "venue", "venueid", "_bibtex", "abstract", "keywords", "TL;DR"):
        val = _or_val(content, key)
        if val:
            response[key] = val
    response["id"] = note.get("id")
    response["forum"] = note.get("forum")
    response["invitation"] = (note.get("invitations") or [note.get("invitation")])[0]
    response["url"] = f"https://openreview.net/forum?id={note.get('id', '')}"
    return response


def fetch_openreview(client: httpx.Client, openreview_id: str, *, raw: bool = False) -> SourceData:
    """Fetch OpenReview note by exact forum ID."""
    for base in ("https://api2.openreview.net", "https://api.openreview.net"):
        url = f"{base}/notes"
        params = {"id": openreview_id}
        req = {"url": url, "params": params}
        try:
            resp = _get(client, url, params=params)
            if not resp:
                continue
        except httpx.HTTPError:
            continue
        notes = resp.json().get("notes", [])
        if notes:
            return {
                "source": "openreview",
                "request": req,
                "status": "ok",
                "response": _or_note_to_dict(notes[0], raw=raw),
            }

    return _error(
        "openreview",
        {"url": "https://api2.openreview.net/notes", "params": {"id": openreview_id}},
        "could not reach OpenReview API",
    )


def fetch_acl(client: httpx.Client, acl_id: str) -> SourceData:
    url = f"https://aclanthology.org/{acl_id}.bib"
    req = {"url": url}

    try:
        resp = client.get(url, follow_redirects=True)
        if resp.status_code == 404:
            return {"source": "acl_anthology", "request": req, "status": "no_match"}
        resp.raise_for_status()
    except httpx.HTTPError as e:
        return _error("acl_anthology", req, str(e))

    return {"source": "acl_anthology", "request": req, "status": "ok", "response": {"bibtex": resp.text.strip()}}


# =============================================================================
# Search functions (title-based, returns ALL results — no judgment)
# =============================================================================


def search_dblp(client: httpx.Client, title: str, venue: str | None = None) -> SourceData:  # noqa: ARG001
    """Search DBLP by title. Returns all hits — does NOT pick one."""
    query = title
    url = "https://dblp.org/search/publ/api"
    params = {"q": query, "format": "json", "h": 10}
    req = {"url": url, "params": params}

    try:
        resp = _get(client, url, params=params)
        if not resp:
            return _error("dblp", req, "not found")
    except httpx.HTTPError as e:
        return _error("dblp", req, str(e))

    hits = resp.json().get("result", {}).get("hits", {}).get("hit", [])
    results = []
    for hit in hits:
        info = hit.get("info", {})
        results.append(
            {
                "title": (info.get("title") or "").rstrip("."),
                "venue": info.get("venue"),
                "year": info.get("year"),
                "type": info.get("type"),
                "key": info.get("key"),
                "authors": [
                    a.get("text", "") if isinstance(a, dict) else str(a)
                    for a in (lambda v: v if isinstance(v, list) else [v])(info.get("authors", {}).get("author", []))
                ],
                "url": info.get("ee"),
            }
        )

    return {
        "source": "dblp",
        "request": req,
        "status": "ok",
        "match_type": "search",
        "response": {"query": query, "total": len(results), "hits": results},
    }


def search_openreview(client: httpx.Client, title: str) -> SourceData:
    """Search OpenReview by title. Returns all matching notes — does NOT pick one."""
    last_req: dict = {}
    for base in ("https://api.openreview.net", "https://api2.openreview.net"):
        url = f"{base}/notes/search"
        params = {"query": title, "limit": "10", "source": "forum"}
        last_req = {"url": url, "params": params}

        try:
            resp = _get(client, url, params=params)
            if not resp:
                continue
        except httpx.HTTPError:
            continue

        results = []
        for note in resp.json().get("notes", []):
            results.append(_or_note_to_dict(note, raw=False))

        return {
            "source": "openreview",
            "request": last_req,
            "status": "ok",
            "match_type": "search",
            "response": {"query": title, "total": len(results), "hits": results},
        }

    return _error("openreview", last_req, "could not reach OpenReview API")


# =============================================================================
# Orchestrator
# =============================================================================

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

# Fetch dispatch: (name, fetch_fn, id_field)
_FETCH_SOURCES: list[tuple[str, Any, str]] = [
    ("dblp", fetch_dblp, "dblp_key"),
    ("crossref", fetch_crossref, "doi"),
    ("openreview", fetch_openreview, "openreview_id"),
    ("acl_anthology", fetch_acl, "acl_id"),
    ("arxiv", fetch_arxiv, "arxiv_id"),
]

ALL_SOURCES = [name for name, _, _ in _FETCH_SOURCES]


def _extract_ids(s2_data: dict) -> dict[str, str | None]:
    """Extract external IDs from S2 response into a flat lookup."""
    ext = s2_data.get("externalIds") or {}
    return {
        "doi": ext.get("DOI"),
        "arxiv_id": ext.get("ArXiv"),
        "acl_id": ext.get("ACL"),
        "dblp_key": ext.get("DBLP"),
        "openreview_id": None,
        "title": s2_data.get("title"),
        "venue": s2_data.get("venue"),
    }


def _resolve_ids(client: httpx.Client, paper_id: str, log: Console) -> tuple[SourceData, dict[str, str | None]]:
    """Resolve paper ID to a complete set of IDs. Returns (s2_result, ids_dict)."""
    log.print(f"[dim]Resolving {paper_id} via Semantic Scholar…[/]")
    s2 = resolve_s2(client, paper_id)

    if s2["status"] == "ok":
        ids = _extract_ids(s2["response"])
    else:
        log.print("[yellow]  S2 resolution failed, extracting IDs from input…[/]")
        ids = _extract_ids_from_input(paper_id)

    # Merge input-derived IDs to fill gaps
    for k, v in _extract_ids_from_input(paper_id).items():
        if v and not ids.get(k):
            ids[k] = v

    # If we have DOI but no title (S2 failed), get title from CrossRef
    if ids.get("doi") and not ids.get("title"):
        log.print("[dim]  Fetching title from CrossRef…[/]")
        cr = fetch_crossref(client, ids["doi"])
        if cr["status"] == "ok":
            titles = cr["response"].get("title", [])
            if titles:
                ids["title"] = titles[0]
                log.print(f"[dim]  → title: {ids['title']}[/]")

    log.print(
        f"[dim]  → DOI={ids['doi'] or '—'}  arXiv={ids['arxiv_id'] or '—'}  "
        f"venue={ids['venue'] or '—'}  ACL={ids['acl_id'] or '—'}[/]"
    )
    log.print()
    return s2, ids


def fetch_all(
    paper_id: str,
    log: Console,
    *,
    sources: list[str] | None = None,
    raw: bool = False,
) -> list[SourceData]:
    """Exact ID-based fetch from all sources. No fuzzy matching."""
    enabled = sources or ALL_SOURCES
    results: list[SourceData] = []

    with httpx.Client(timeout=30.0) as client:
        s2, ids = _resolve_ids(client, paper_id, log)
        results.append(s2)

        for name, fetch_fn, id_field in _FETCH_SOURCES:
            if name not in enabled:
                results.append(_skipped(name, "disabled"))
                continue

            id_val = ids.get(id_field)
            if not id_val:
                results.append(_skipped(name, f"no {id_field}"))
                log.print(f"  [dim]{name}: skipped (no {id_field})[/]")
                continue

            log.print(f"  [dim]{name}: fetching…[/]", end="")
            # CrossRef and arXiv accept raw kwarg; DBLP, OpenReview, ACL do not
            if name in ("crossref", "arxiv"):
                result = fetch_fn(client, id_val, raw=raw)
            else:
                result = fetch_fn(client, id_val)
            results.append(result)

            status = result["status"]
            if status == "ok":
                log.print(" [green]ok[/]")
            elif status == "no_match":
                log.print(" [yellow]no match[/]")
            else:
                log.print(f" [red]{result.get('error', 'error')}[/]")

    return results


def search_all(
    paper_id: str,
    log: Console,
    *,
    sources: list[str] | None = None,
) -> list[SourceData]:
    """Title-based search on DBLP and OpenReview. Returns all results — no judgment."""
    search_sources = {"dblp", "openreview"}
    enabled = set(sources) & search_sources if sources else search_sources
    results: list[SourceData] = []

    with httpx.Client(timeout=30.0) as client:
        s2, ids = _resolve_ids(client, paper_id, log)
        results.append(s2)

        title = ids.get("title")
        if not title:
            log.print(
                "[red]  No title available for search. "
                "Provide a paper ID that S2 can resolve, or a DOI for CrossRef title lookup.[/]"
            )
            return results

        venue = ids.get("venue")

        if "dblp" in enabled:
            log.print("  [dim]dblp: searching…[/]", end="")
            result = search_dblp(client, title, venue)
            results.append(result)
            n = result.get("response", {}).get("total", 0) if result["status"] == "ok" else 0
            log.print(f" [green]{n} results[/]" if result["status"] == "ok" else " [red]error[/]")

        if "openreview" in enabled:
            log.print("  [dim]openreview: searching…[/]", end="")
            result = search_openreview(client, title)
            results.append(result)
            n = result.get("response", {}).get("total", 0) if result["status"] == "ok" else 0
            log.print(f" [green]{n} results[/]" if result["status"] == "ok" else " [red]error[/]")

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
    console.print_json(json.dumps(data, ensure_ascii=False))


def _display_s2(s2: SourceData, console: Console) -> None:
    if s2["status"] == "ok":
        resp = s2.get("response", {})
        console.print("[bold]Resolved via Semantic Scholar[/]")
        console.print(f"  [dim]GET {_format_url(s2.get('request', {}))}[/]")
        console.print()
        console.print(f"  [cyan]title[/]:  {resp.get('title', '—')}")
        console.print(f"  [cyan]venue[/]:  {resp.get('venue', '—')}")
        for k, v in (resp.get("externalIds") or {}).items():
            console.print(f"  [cyan]{k}[/]:  {v}")
    else:
        console.print(f"[bold red]Semantic Scholar: {s2.get('error', 'resolution failed')}[/]")
        console.print(f"  [dim]GET {_format_url(s2.get('request', {}))}[/]")
    console.print()


def display_rich(results: list[SourceData], console: Console) -> None:
    console.print()

    s2 = results[0] if results and results[0]["source"] == "semantic_scholar" else None
    sources = results[1:] if s2 else results

    if s2:
        _display_s2(s2, console)

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


def display_search(results: list[SourceData], console: Console) -> None:
    """Display search results as numbered lists."""
    console.print()

    s2 = results[0] if results and results[0]["source"] == "semantic_scholar" else None
    sources = results[1:] if s2 else results

    if s2:
        _display_s2(s2, console)

    for data in sources:
        if data["status"] != "ok":
            name = data["source"]
            console.rule(f"[bold red]{name} (error: {data.get('error', '?')})[/bold red]")
            continue

        name = data["source"]
        resp = data.get("response", {})
        hits = resp.get("hits", [])
        query = resp.get("query", "")

        console.rule(f'[bold green]{name}[/bold green]  [dim]search: "{query}"  ({len(hits)} results)[/]')
        req = data.get("request", {})
        if req:
            console.print(f"  [dim]GET {_format_url(req)}[/]")
        console.print()

        if not hits:
            console.print("  [yellow]no results[/]\n")
            continue

        for i, hit in enumerate(hits, 1):
            if name == "dblp":
                title = hit.get("title", "—")
                venue = hit.get("venue", "—")
                year = hit.get("year", "—")
                key = hit.get("key", "—")
                authors = ", ".join(hit.get("authors", [])[:3])
                if len(hit.get("authors", [])) > 3:
                    authors += " et al."
                console.print(f"  [bold][{i}][/] {title}")
                console.print(f"      [cyan]venue[/]={venue}  [cyan]year[/]={year}  [cyan]key[/]={key}")
                console.print(f"      [dim]{authors}[/]")
            elif name == "openreview":
                title = hit.get("title", "—")
                venue = hit.get("venue", "—")
                invitation = hit.get("invitation", "—")
                url = hit.get("url", "—")
                console.print(f"  [bold][{i}][/] {title}")
                console.print(f"      [cyan]venue[/]={venue}")
                console.print(f"      [cyan]invitation[/]={invitation}")
                console.print(f"      [dim]{url}[/]")
            console.print()


# =============================================================================
# Display: JSON
# =============================================================================


def _clean(d: Any) -> Any:
    """Strip None values recursively for cleaner JSON output."""
    if isinstance(d, dict):
        return {k: _clean(v) for k, v in d.items() if v is not None}
    if isinstance(d, list):
        return [_clean(x) for x in d]
    return d


def _inject_meta(results: list[SourceData]) -> list[SourceData]:
    enriched = []
    for data in results:
        name = data.get("source", "")
        meta = _SOURCE_META.get(name)
        if meta and data.get("status") not in ("skipped",):
            data = {**data, "_meta": meta}
        enriched.append(data)
    return enriched


def display_json(results: list[SourceData]) -> None:
    enriched = _inject_meta(results)
    print(json.dumps(_clean(enriched), indent=2, ensure_ascii=False))


def display_raw(results: list[SourceData], source_name: str) -> None:
    s2 = results[0] if results and results[0]["source"] == "semantic_scholar" else None
    target = next((r for r in results if r["source"] == source_name and r["status"] != "skipped"), None)

    output: dict[str, Any] = {}
    if s2 and s2["status"] == "ok":
        resp = s2["response"]
        output["resolved"] = {"title": resp.get("title"), "venue": resp.get("venue"), "ids": resp.get("externalIds")}

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
        "Two modes:\n"
        "  (default)   Exact ID-based fetch — each source is queried by its native ID.\n"
        "              No fuzzy matching, no hidden judgment.\n"
        "  --search    Title-based search on DBLP and OpenReview.\n"
        "              Returns ALL results as a numbered list. You pick the right one.",
        epilog=(
            "examples:\n"
            "  %(prog)s 2010.11929                         # exact fetch via arXiv ID\n"
            "  %(prog)s 10.18653/v1/N19-1423                # exact fetch via DOI\n"
            "  %(prog)s 'https://openreview.net/forum?id=X' # exact fetch via OpenReview URL\n"
            "  %(prog)s --json 1706.03762                   # JSON for piping to AI agent\n"
            "  %(prog)s --search 1706.03762                 # search DBLP/OpenReview by title\n"
            "  %(prog)s --raw crossref 10.18653/v1/N19-1423 # full raw CrossRef API response\n"
            "\n"
            "fetch sources (exact ID-based):\n"
            "  dblp           exact key lookup (requires S2 to provide DBLP key)\n"
            "  crossref       DOI lookup — container-title, author, page, volume\n"
            "  openreview     forum ID lookup — venue, acceptance type, BibTeX, keywords\n"
            "  acl_anthology  ACL ID lookup — complete, copy-ready BibTeX\n"
            "  arxiv          arXiv ID lookup — categories, dates, comments\n"
            "\n"
            "search sources (title-based, returns list):\n"
            "  dblp           title search — returns up to 10 results\n"
            "  openreview     title search — returns up to 10 results\n"
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
        "Semantic Scholar ID (ARXIV:2010.11929, DOI:10.xxx, CorpusId:12345), "
        "or OpenReview URL (https://openreview.net/forum?id=XXX)",
    )
    parser.add_argument(
        "--search",
        action="store_true",
        help="search mode: resolve paper ID to title via S2, then search DBLP and OpenReview. "
        "returns ALL results as a numbered list (no judgment, no auto-picking). "
        "use this when exact IDs are not available",
    )
    parser.add_argument("--json", action="store_true", help="output as JSON array with _meta per source")
    parser.add_argument(
        "--sources", help=f"comma-separated list of sources (default: all). choices: {','.join(ALL_SOURCES)}"
    )
    parser.add_argument(
        "--raw",
        metavar="SOURCE",
        help=f"full unfiltered API response from one source. choices: {','.join(ALL_SOURCES)}",
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

    if args.search:
        results = search_all(args.paper_id, log, sources=sources)
        if args.json:
            display_json(results)
        else:
            display_search(results, Console())
    elif raw:
        results = fetch_all(args.paper_id, log, sources=sources, raw=True)
        display_raw(results, args.raw)
    elif args.json:
        results = fetch_all(args.paper_id, log, sources=sources)
        display_json(results)
    else:
        results = fetch_all(args.paper_id, log, sources=sources)
        display_rich(results, Console())


if __name__ == "__main__":
    main()
