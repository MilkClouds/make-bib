#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "filelock",
#     "httpx",
#     "rich",
#     "typer",
# ]
# ///
"""Local DBLP database for fast title-based paper lookup.

Downloads conference proceedings BibTeX from DBLP's table-of-contents API,
stores them as JSON keyed by normalized title for O(1) lookup.
Approach borrowed from Rebiber (github.com/yuchenlin/rebiber).

Data layout:
    data/dblp/{conf_name}/{year}.json
    Each file: {normalized_title: bibtex_string, ...}

    data/dblp/{conf_name}/_status.json
    Tracks sync progress: {
        "complete_years": [2010, 2015, ...],
        "pages_done": {"2020": [0, 1], ...}
    }
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Annotated, Any

import httpx
import typer
from filelock import FileLock
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

# -- Paths --
DATA_DIR = Path(__file__).parent / "data" / "dblp"
MAX_PAGES = 5
PAGE_SIZE = 1000

# DBLP mirrors (for reference / fallback)
# Primary: https://dblp.org
# Mirrors: https://dblp.uni-trier.de, https://dblp.dagstuhl.de
DBLP_BASE = "https://dblp.org"

# -- Title normalization (Rebiber approach) --


def normalize_title(title: str) -> str:
    """Strip non-alpha characters and lowercase for fuzzy title matching."""
    return re.sub(r"[^a-zA-Z]", "", title).lower()


# -- BibTeX field extraction --


def _bib_field(bibtex: str, name: str) -> str | None:
    """Extract a field value from a BibTeX entry. Handles both {value} and bare value."""
    # Try braced: field = {value},
    m = re.search(rf"^\s*{name}\s*=\s*\{{(.+?)\}}\s*[,}}]", bibtex, re.MULTILINE | re.DOTALL)
    if m:
        return m.group(1).strip()
    # Try bare: field = value,
    m = re.search(rf"^\s*{name}\s*=\s*([^,\s]+)\s*,", bibtex, re.MULTILINE)
    return m.group(1).strip() if m else None


def _bib_key(bibtex: str) -> str | None:
    """Extract the entry key from @type{key, ...}."""
    m = re.match(r"@\w+\{([^,]+),", bibtex)
    return m.group(1).strip() if m else None


def _structured_from_bibtex(bibtex: str) -> dict[str, Any]:
    """Build structured entry from raw BibTeX string."""
    raw_title = _bib_field(bibtex, "title") or ""
    clean_title = re.sub(r"[{}]", "", raw_title).rstrip(".")
    author_str = _bib_field(bibtex, "author") or ""
    authors = [a.strip() for a in re.split(r"\s+and\s+", author_str)] if author_str else []
    return {
        "title": clean_title,
        "venue": _bib_field(bibtex, "booktitle") or _bib_field(bibtex, "journal"),
        "year": _bib_field(bibtex, "year"),
        "key": _bib_key(bibtex),
        "authors": authors,
        "bibtex": bibtex,
    }


# -- Conference definitions --
#
# Each entry supports:
#   dir:       DBLP directory name (may differ from key, e.g. neurips -> nips)
#   start/end: year range (end defaults to CURRENT_YEAR)
#   step:      for biennial conferences (default 1)
#   years:     explicit year list for irregular schedules (overrides start/end/step)
#   type:      "journals" for journal venues (default: "conf")
#   vol_start: journal volume numbering {"year": ..., "vol": ...}
#   suffixes:  alternative DBLP toc key suffixes to try as fallback (e.g. ["", "c"] for sigmod)
#   extra_tocs: additional toc suffixes to always fetch and merge (e.g. ["f"] for Findings)
#
# Known DBLP toc API limitations:
#   - COLT 2011-2012: pages exist on DBLP website but toc API returns empty
#     (published via JMLR W&CP, not indexed in toc format)
#   - AISTATS pre-2013: same issue (JMLR W&CP proceedings)
#   - SIGMOD 2023+: DBLP changed toc key from sigmod{year} to sigmod{year}c
#

CURRENT_YEAR = 2026

CONFERENCES: dict[str, dict[str, Any]] = {
    # ML / AI
    "neurips": {"dir": "nips", "start": 2020},
    "nips": {"dir": "nips", "start": 2000, "end": 2019},
    "icml": {"dir": "icml", "start": 2010},
    "iclr": {"dir": "iclr", "start": 2013},
    "aaai": {"dir": "aaai", "start": 2010},
    "ijcai": {  # biennial odd years until 2015, annual from 2016
        "dir": "ijcai",
        "years": [2011, 2013, 2015, *range(2016, CURRENT_YEAR + 1)],
    },
    "aistats": {"dir": "aistats", "start": 2013},  # pre-2013: DBLP toc unavailable
    "uai": {"dir": "uai", "start": 2010},
    "colt": {"dir": "colt", "start": 2010},  # 2011-2012: DBLP toc unavailable
    "mlsys": {"dir": "mlsys", "start": 2019},
    # CV
    "cvpr": {"dir": "cvpr", "start": 2010},
    "iccv": {"dir": "iccv", "start": 2011, "step": 2},  # odd years only
    "eccv": {"dir": "eccv", "start": 2010, "step": 2},  # even years only
    "bmvc": {"dir": "bmvc", "start": 2015},
    "accv": {"dir": "accv", "start": 2010, "step": 2},  # even years only
    "miccai": {"dir": "miccai", "start": 2015},
    # NLP / IR
    "acl": {"dir": "acl", "start": 2010, "extra_tocs": ["f"]},  # f = Findings (2021+)
    "emnlp": {"dir": "emnlp", "start": 2010, "extra_tocs": ["f"]},  # f = Findings (2020+)
    "naacl": {  # irregular schedule (alternates with EACL, sometimes skipped)
        "dir": "naacl",
        "years": [2010, 2012, 2013, 2015, 2016, 2018, 2019, 2021, 2022, 2024, 2025],
        "extra_tocs": ["f"],  # f = Findings (2022+)
    },
    "eacl": {  # irregular schedule (roughly every 2-3 years)
        "dir": "eacl",
        "years": [2012, 2014, 2017, 2021, 2023, 2024],
    },
    "coling": {"dir": "coling", "start": 2010, "step": 2},  # even years only
    "sigir": {"dir": "sigir", "start": 2015},
    "wsdm": {"dir": "wsdm", "start": 2015},
    "cikm": {"dir": "cikm", "start": 2015},
    "www": {"dir": "www", "start": 2015},
    # Systems / Data / HCI
    "kdd": {"dir": "kdd", "start": 2010},
    "chi": {"dir": "chi", "start": 2015},
    "sigmod": {"dir": "sigmod", "start": 2015, "suffixes": ["", "c"]},  # 2023+: key=sigmod{year}c
    "recsys": {"dir": "recsys", "start": 2015},
    # Audio / Speech
    "icassp": {"dir": "icassp", "start": 2015},
    "interspeech": {"dir": "interspeech", "start": 2015},
    # Theory
    "stoc": {"dir": "stoc", "start": 2015},
    "soda": {"dir": "soda", "start": 2015},
    # Robotics
    "corl": {"dir": "corl", "start": 2017},
    "rss": {"dir": "rss", "start": 2015},
    "iros": {"dir": "iros", "start": 2015},
    "icra": {"dir": "icra", "start": 2015},
    # Journals (use toc for journal volumes)
    "tacl": {"dir": "tacl", "start": 2013, "type": "journals", "vol_start": {"year": 2013, "vol": 1}},
    "jmlr": {"dir": "jmlr", "start": 2010, "type": "journals", "vol_start": {"year": 2000, "vol": 1}},
}


def _year_range(conf: dict[str, Any]) -> list[int]:
    """Generate the list of years for a conference."""
    if "years" in conf:
        return list(conf["years"])
    start = conf["start"]
    end = conf.get("end", CURRENT_YEAR)
    step = conf.get("step", 1)
    return list(range(start, end + 1, step))


# -- BibTeX parsing --


def _parse_bib_entries(bib_text: str) -> list[tuple[str, str]]:
    """Parse BibTeX text into (normalized_title, raw_bibtex_string) pairs."""
    results: list[tuple[str, str]] = []
    entries = re.split(r"(?=@\w+\{)", bib_text)

    for entry in entries:
        entry = entry.strip()
        if not entry or not entry.startswith("@"):
            continue

        title_match = re.search(
            r"^\s*title\s*=\s*\{(.+?)\}\s*[,}]",
            entry,
            re.MULTILINE | re.DOTALL,
        )
        if not title_match:
            continue

        title = title_match.group(1).strip()
        clean_title = re.sub(r"[{}]", "", title)
        norm = normalize_title(clean_title)

        if norm:
            # Remove noisy DBLP metadata fields
            cleaned = entry
            for field in ("month", "timestamp", "biburl", "bibsource"):
                cleaned = re.sub(
                    rf"^\s*{field}\s*=\s*\{{[^}}]*\}}\s*,?\s*\n?",
                    "",
                    cleaned,
                    flags=re.MULTILINE,
                )
            results.append((norm, cleaned.strip()))

    return results


# -- Data I/O --


def _year_path(conf_name: str, year: int) -> Path:
    """Path to a single year's JSON file."""
    return DATA_DIR / conf_name / f"{year}.json"


def _status_path(conf_name: str) -> Path:
    """Path to the status file for a conference directory."""
    return DATA_DIR / conf_name / "_status.json"


def _load_status(conf_name: str) -> dict[str, Any]:
    """Load sync status for a conference. Returns default if missing."""
    path = _status_path(conf_name)
    if not path.exists():
        return {"complete_years": [], "pages_done": {}}
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {"complete_years": [], "pages_done": {}}


def _save_status(conf_name: str, status: dict[str, Any]) -> None:
    """Save sync status for a conference with file locking."""
    path = _status_path(conf_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = FileLock(str(path) + ".lock")
    with lock:
        path.write_text(json.dumps(status, indent=2, ensure_ascii=False))


def _load_year(conf_name: str, year: int) -> dict[str, str]:
    """Load a single year file. Returns empty dict if missing."""
    path = _year_path(conf_name, year)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _save_year(conf_name: str, year: int, data: dict[str, str]) -> Path:
    """Save a single year file with file locking. Creates directories as needed."""
    path = _year_path(conf_name, year)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = FileLock(str(path) + ".lock")
    with lock:
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    return path


# -- Download --


def _build_toc_query(conf_name: str, conf: dict[str, Any], year: int) -> str:
    """Build DBLP toc query string."""
    dblp_dir = conf["dir"]
    db_type = conf.get("type", "conf")
    if db_type == "journals":
        vol_start = conf.get("vol_start")
        if vol_start:
            vol = vol_start["vol"] + (year - vol_start["year"])
        else:
            vol = year
        return f"toc:db/journals/{dblp_dir}/{dblp_dir}{vol}.bht:"
    return f"toc:db/conf/{dblp_dir}/{conf_name}{year}.bht:"


def _fetch_page(
    client: httpx.Client,
    query: str,
    page: int,
    console: Console,
) -> list[tuple[str, str]] | None:
    """Fetch a single page of BibTeX results from DBLP.

    Returns parsed (norm_title, bibtex) pairs, or None on failure.
    Empty list means no results (end of pagination).
    """
    url = f"{DBLP_BASE}/search/publ/api"
    params = {"q": query, "h": str(PAGE_SIZE), "f": str(page * PAGE_SIZE), "format": "bib"}

    for attempt in range(5):
        try:
            resp = client.get(url, params=params)
            if resp.status_code == 429:
                wait = (attempt + 1) * 20
                console.print(f"  [yellow]Rate limited, waiting {wait}s...[/]", highlight=False)
                time.sleep(wait)
                continue
            if resp.status_code in (500, 502, 503, 504):
                wait = (attempt + 1) * 10
                if attempt < 4:
                    time.sleep(wait)
                    continue
                console.print(f"  [red]Page {page} failed: {resp.status_code}[/]", highlight=False)
                return None
            resp.raise_for_status()
            break
        except httpx.HTTPError as e:
            if attempt < 4:
                time.sleep((attempt + 1) * 10)
                continue
            console.print(f"  [red]Page {page} failed: {e}[/]", highlight=False)
            return None
    else:
        return None

    bib_text = resp.text.strip()
    if not bib_text:
        return []

    parsed = _parse_bib_entries(bib_text)
    return parsed if parsed else []


def _fetch_query_all_pages(
    client: httpx.Client,
    query: str,
    console: Console,
) -> tuple[dict[str, str], bool]:
    """Fetch all pages for a single toc query. Returns (entries, success)."""
    entries: dict[str, str] = {}
    had_failure = False

    for page in range(MAX_PAGES):
        parsed = _fetch_page(client, query, page, console)

        if parsed is None:
            had_failure = True
            time.sleep(5)
            continue

        if not parsed:
            break

        for norm_title, bib_entry in parsed:
            entries[norm_title] = bib_entry

        if len(parsed) < 900:
            break

        time.sleep(5)

    return entries, not had_failure


def _download_venue_year(
    client: httpx.Client,
    conf_name: str,
    conf: dict[str, Any],
    year: int,
    pages_done: list[int],
    console: Console,
) -> tuple[dict[str, str], list[int], bool]:
    """Download BibTeX entries for one conference year.

    Handles split proceedings: if the base query returns empty,
    tries {conf}{year}-1, -2, -3, ... until a part returns empty.

    Args:
        pages_done: Legacy field (kept for caller compat, unused with split logic).

    Returns:
        (entries, new_pages_done, is_complete):
        - entries: {norm_title: bib_entry} from newly fetched pages
        - new_pages_done: always [] (page-level resume not used with split support)
        - is_complete: True if all parts fetched successfully
    """
    db_type = conf.get("type", "conf")
    dblp_dir = conf["dir"]
    all_entries: dict[str, str] = {}
    all_ok = True

    # 1. Try base query
    base_query = _build_toc_query(conf_name, conf, year)
    entries, ok = _fetch_query_all_pages(client, base_query, console)
    if entries:
        all_entries.update(entries)
        if not ok:
            all_ok = False
    else:
        # 2. Try alternative suffixes as fallback (e.g. sigmod2023c)
        for suffix in conf.get("suffixes", []):
            if not suffix:
                continue
            suffix_query = f"toc:db/conf/{dblp_dir}/{conf_name}{year}{suffix}.bht:"
            entries, ok = _fetch_query_all_pages(client, suffix_query, console)
            if entries:
                all_entries.update(entries)
                if not ok:
                    all_ok = False
                break
            time.sleep(2)

        # 3. Try split proceedings: -1, -2, -3, ...
        if not all_entries and db_type != "journals":
            num_parts = 0
            for part in range(1, 50):  # safety cap
                part_query = f"toc:db/conf/{dblp_dir}/{conf_name}{year}-{part}.bht:"
                part_entries, part_ok = _fetch_query_all_pages(client, part_query, console)
                if not part_entries:
                    break
                num_parts = part
                all_entries.update(part_entries)
                if not part_ok:
                    all_ok = False
                time.sleep(2)
            if all_entries:
                console.print(f"    [dim]split proceedings: {num_parts} parts[/]", highlight=False)

    # 4. Always fetch extra toc volumes (e.g. Findings) and merge
    for extra in conf.get("extra_tocs", []):
        extra_query = f"toc:db/conf/{dblp_dir}/{conf_name}{year}{extra}.bht:"
        extra_entries, extra_ok = _fetch_query_all_pages(client, extra_query, console)
        if extra_entries:
            console.print(f"    [dim]+{len(extra_entries)} from {conf_name}{year}{extra}[/]", highlight=False)
            all_entries.update(extra_entries)
            if not extra_ok:
                all_ok = False
            time.sleep(2)

    # Never mark complete with 0 entries — likely not yet on DBLP
    if not all_entries:
        return {}, [], False

    return all_entries, [], all_ok


def sync(
    conferences: list[str] | None = None,
    years: list[int] | None = None,
    force: bool = False,
    console: Console | None = None,
) -> None:
    """Download DBLP proceedings and build local JSON database.

    Args:
        conferences: List of conference names to sync (default: all).
        years: Only sync these specific years (default: all years for each conference).
        force: Re-download even complete years (merges with existing data).
    """
    console = console or Console(stderr=True)

    targets = conferences or list(CONFERENCES.keys())
    invalid = [c for c in targets if c not in CONFERENCES]
    if invalid:
        console.print(f"[red]Unknown conferences: {', '.join(invalid)}[/]")
        console.print(f"[dim]Available: {', '.join(sorted(CONFERENCES.keys()))}[/]")
        return

    failures: list[tuple[str, int]] = []

    with httpx.Client(timeout=60.0) as client:
        for conf_name in targets:
            conf = CONFERENCES[conf_name]
            conf_dir = conf["dir"]
            all_years = _year_range(conf)
            sync_years = [y for y in all_years if y in years] if years else all_years

            if not sync_years:
                continue

            status = _load_status(conf_dir)
            complete_years = set(status.get("complete_years", []))
            pages_done_map: dict[str, list[int]] = status.get("pages_done", {})

            # Filter out complete years unless --force
            if not force:
                pending = [y for y in sync_years if y not in complete_years]
            else:
                pending = list(sync_years)

            if not pending:
                console.print(f"\n[bold]{conf_name}[/] — all {len(sync_years)} years complete")
                continue

            skipped = len(sync_years) - len(pending)
            skip_msg = f", {skipped} complete" if skipped else ""
            console.print(f"\n[bold]{conf_name}[/] ({len(pending)} to sync{skip_msg})")

            total_new = 0
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                console=console,
            ) as progress:
                task = progress.add_task(f"  {conf_name}", total=len(pending))

                for year in pending:
                    progress.update(task, description=f"  {conf_name} {year}")
                    year_pages_done = pages_done_map.get(str(year), [])

                    entries, new_pages_done, is_complete = _download_venue_year(
                        client,
                        conf_name,
                        conf,
                        year,
                        year_pages_done,
                        console,
                    )

                    # Save entries (merge with existing)
                    if entries:
                        existing = _load_year(conf_dir, year)
                        existing.update(entries)
                        _save_year(conf_dir, year, existing)
                        total_new += len(entries)

                    # Update status
                    if is_complete:
                        complete_years.add(year)
                        pages_done_map.pop(str(year), None)
                    elif new_pages_done != year_pages_done:
                        pages_done_map[str(year)] = new_pages_done

                    if not is_complete:
                        failures.append((conf_name, year))

                    # Save status after each year
                    _save_status(
                        conf_dir,
                        {
                            "complete_years": sorted(complete_years),
                            "pages_done": pages_done_map,
                        },
                    )

                    progress.advance(task)
                    time.sleep(1)  # polite inter-year delay

            if total_new > 0:
                console.print(f"  [green]+{total_new} entries synced[/]")
            else:
                console.print("  [dim]No new entries[/]")

    # Summary
    if failures:
        console.print(f"\n[yellow]Incomplete: {len(failures)} conference-years failed:[/]")
        for conf_name, year in failures:
            console.print(f"  [yellow]{conf_name} {year}[/]")
        console.print("[dim]Re-run sync to retry failed years.[/]")
    else:
        console.print("\n[green]All conference-years synced successfully.[/]")


# -- Search --


class IncompleteDBError(Exception):
    """Raised when the local DBLP database has incomplete data."""


def _check_db_completeness() -> list[tuple[str, int]]:
    """Check for incomplete years (data exists but not marked complete).

    Returns list of (conf_dir, year) tuples that are incomplete.
    """
    incomplete: list[tuple[str, int]] = []
    if not DATA_DIR.exists():
        return incomplete
    for conf_dir in DATA_DIR.iterdir():
        if not conf_dir.is_dir():
            continue
        status = _load_status(conf_dir.name)
        complete_years = set(status.get("complete_years", []))
        pages_done_map = status.get("pages_done", {})
        # Any year with pages_done but not complete is incomplete
        for year_str in pages_done_map:
            year = int(year_str)
            if year not in complete_years:
                incomplete.append((conf_dir.name, year))
    return incomplete


def _load_db() -> dict[str, str]:
    """Load all year JSON files from data directory into a single lookup dict."""
    db: dict[str, str] = {}
    if not DATA_DIR.exists():
        return db
    for path in DATA_DIR.rglob("*.json"):
        if path.name.startswith("_"):
            continue
        try:
            data = json.loads(path.read_text())
            db.update(data)
        except (json.JSONDecodeError, OSError):
            continue
    return db


def search(title: str, max_results: int = 5) -> list[dict[str, Any]]:
    """Search local DBLP database by title.

    Tries exact normalized match first (returns single-element list),
    then falls back to substring match (returns up to max_results candidates
    sorted by key length, shortest first).

    Returns list of structured dicts with keys: title, venue, year, key, authors, bibtex.
    Returns empty list if not found.

    Raises:
        IncompleteDBError: If the database has incomplete (partially synced) years.
    """
    incomplete = _check_db_completeness()
    if incomplete:
        details = ", ".join(f"{c}/{y}" for c, y in incomplete[:10])
        suffix = f" and {len(incomplete) - 10} more" if len(incomplete) > 10 else ""
        raise IncompleteDBError(
            f"Database has {len(incomplete)} incomplete years: {details}{suffix}. "
            f"Run 'dblp_local.py sync' to complete download."
        )

    db = _load_db()
    norm = normalize_title(title)

    # Exact match (O(1))
    entry = db.get(norm)
    if entry is not None:
        return [_structured_from_bibtex(entry)]

    # Substring match: find entries whose key contains the query
    if len(norm) < 10:
        return []  # too short, would match too many
    matches = [(k, v) for k, v in db.items() if norm in k]
    if not matches:
        return []
    # Sort by key length (shortest = closest match), return top N
    matches.sort(key=lambda x: len(x[0]))
    return [_structured_from_bibtex(v) for _, v in matches[:max_results]]


# -- CLI --

app = typer.Typer(
    help="Local DBLP database for fast title-based paper lookup.",
    no_args_is_help=True,
)


@app.command("sync")
def cli_sync(
    conferences: Annotated[
        str | None,
        typer.Option("--conferences", "-c", help="Comma-separated conference names (default: all)"),
    ] = None,
    year: Annotated[
        str | None,
        typer.Option("--year", "-y", help="Comma-separated years to sync (default: all)"),
    ] = None,
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Re-download even complete years (merges with existing)"),
    ] = False,
) -> None:
    """Download DBLP proceedings and build local JSON database."""
    targets = [c.strip() for c in conferences.split(",")] if conferences else None
    year_list = [int(y.strip()) for y in year.split(",")] if year else None
    sync(conferences=targets, years=year_list, force=force)


@app.command("search")
def cli_search(
    title: Annotated[str, typer.Argument(help="Paper title to search for")],
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    max_results: Annotated[int, typer.Option("--max", "-n", help="Max substring match results")] = 5,
) -> None:
    """Search local database by title."""
    try:
        results = search(title, max_results=max_results)
    except IncompleteDBError as e:
        console = Console(stderr=True)
        console.print(f"[red]Error: {e}[/]")
        raise typer.Exit(2)

    if not results:
        if json_output:
            print(json.dumps({"status": "no_match", "query": title, "normalized": normalize_title(title)}))
        else:
            console = Console(stderr=True)
            console.print(f"[yellow]No match for:[/] {title}")
            console.print(f"[dim]Normalized: {normalize_title(title)}[/]")
        raise typer.Exit(1)

    if json_output:
        print(json.dumps({"status": "ok", "query": title, "results": results}))
    else:
        for r in results:
            print(r["bibtex"])
            if len(results) > 1:
                print()


@app.command("stats")
def cli_stats() -> None:
    """Show local database statistics."""
    console = Console()
    if not DATA_DIR.exists():
        console.print("[yellow]No local database found. Run 'sync' first.[/]")
        return

    total = 0
    for conf_dir in sorted(DATA_DIR.iterdir()):
        if not conf_dir.is_dir():
            continue

        status = _load_status(conf_dir.name)
        complete_years = set(status.get("complete_years", []))
        pages_done = status.get("pages_done", {})
        incomplete_count = len([y for y in pages_done if int(y) not in complete_years])

        conf_count = 0
        year_files = sorted(p for p in conf_dir.glob("*.json") if not p.name.startswith("_"))
        for path in year_files:
            try:
                data = json.loads(path.read_text())
                conf_count += len(data)
            except (json.JSONDecodeError, OSError):
                pass
        total += conf_count
        year_range = ""
        if year_files:
            years_list = [p.stem for p in year_files]
            year_range = f" ({years_list[0]}–{years_list[-1]})"
        inc_tag = f" [yellow]({incomplete_count} incomplete)[/]" if incomplete_count else ""
        console.print(
            f"  {conf_dir.name:20s} {conf_count:>6,} entries  {len(complete_years):>3} complete{year_range}{inc_tag}"
        )

    console.print(f"\n  [bold]Total: {total:,} entries[/]")


@app.command("list-conferences")
def cli_list_conferences() -> None:
    """List all supported conferences."""
    console = Console()
    for name, conf in sorted(CONFERENCES.items()):
        years = _year_range(conf)
        year_range = f"{years[0]}–{years[-1]}"
        db_type = conf.get("type", "conf")
        tag = f"[dim]({db_type})[/]" if db_type != "conf" else ""
        console.print(f"  {name:20s} {year_range:15s} {tag}")


@app.command("reset-status")
def cli_reset_status(
    conferences: Annotated[
        str | None,
        typer.Option("--conferences", "-c", help="Comma-separated conference names (default: all affected)"),
    ] = None,
    year: Annotated[
        str | None,
        typer.Option("--year", "-y", help="Comma-separated years to reset (default: all years)"),
    ] = None,
    zero_only: Annotated[
        bool,
        typer.Option("--zero-only", help="Only reset years with 0 entries in their JSON file"),
    ] = True,
) -> None:
    """Remove falsely-completed years from _status.json so sync will re-fetch them.

    By default (--zero-only), only resets years marked complete but with 0 entries.
    """
    console = Console(stderr=True)
    targets = [c.strip() for c in conferences.split(",")] if conferences else list(CONFERENCES.keys())
    year_list = {int(y.strip()) for y in year.split(",")} if year else None

    total_reset = 0
    for conf_name in targets:
        if conf_name not in CONFERENCES:
            continue
        conf_dir = CONFERENCES[conf_name]["dir"]
        status = _load_status(conf_dir)
        complete_years = set(status.get("complete_years", []))
        if not complete_years:
            continue

        to_reset: set[int] = set()
        for y in complete_years:
            if year_list and y not in year_list:
                continue
            if zero_only:
                data = _load_year(conf_dir, y)
                if len(data) > 0:
                    continue
            to_reset.add(y)

        if not to_reset:
            continue

        status["complete_years"] = sorted(complete_years - to_reset)
        _save_status(conf_dir, status)
        total_reset += len(to_reset)
        years_str = ", ".join(str(y) for y in sorted(to_reset))
        console.print(f"  {conf_name}: reset {len(to_reset)} years ({years_str})")

    if total_reset:
        console.print(f"\n[green]Reset {total_reset} years. Run 'sync' to re-fetch.[/]")
    else:
        console.print("[dim]No years to reset.[/]")


if __name__ == "__main__":
    app()
