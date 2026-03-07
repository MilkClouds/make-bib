#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
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
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Annotated, Any

import httpx
import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

# -- Paths --
DATA_DIR = Path(__file__).parent / "data" / "dblp"

# -- Title normalization (Rebiber approach) --


def normalize_title(title: str) -> str:
    """Strip non-alpha characters and lowercase for fuzzy title matching."""
    return re.sub(r"[^a-zA-Z]", "", title).lower()


# -- BibTeX field extraction --


def _bib_field(bibtex: str, name: str) -> str | None:
    """Extract a field value from a BibTeX entry. Handles both {value} and bare value."""
    # Try braced: field = {value},
    m = re.search(rf'^\s*{name}\s*=\s*\{{(.+?)\}}\s*[,}}]', bibtex, re.MULTILINE | re.DOTALL)
    if m:
        return m.group(1).strip()
    # Try bare: field = value,
    m = re.search(rf'^\s*{name}\s*=\s*([^,\s]+)\s*,', bibtex, re.MULTILINE)
    return m.group(1).strip() if m else None


def _bib_key(bibtex: str) -> str | None:
    """Extract the entry key from @type{key, ...}."""
    m = re.match(r'@\w+\{([^,]+),', bibtex)
    return m.group(1).strip() if m else None


def _structured_from_bibtex(bibtex: str) -> dict[str, Any]:
    """Build structured entry from raw BibTeX string."""
    raw_title = _bib_field(bibtex, "title") or ""
    clean_title = re.sub(r'[{}]', '', raw_title).rstrip(".")
    author_str = _bib_field(bibtex, "author") or ""
    authors = [a.strip() for a in re.split(r'\s+and\s+', author_str)] if author_str else []
    return {
        "title": clean_title,
        "venue": _bib_field(bibtex, "booktitle") or _bib_field(bibtex, "journal"),
        "year": _bib_field(bibtex, "year"),
        "key": _bib_key(bibtex),
        "authors": authors,
        "bibtex": bibtex,
    }


# -- Conference definitions --

CONFERENCES: dict[str, dict[str, Any]] = {
    # ML / AI
    "neurips": {"dir": "nips", "start": 2018},
    "nips": {"dir": "nips", "start": 2000, "end": 2017},
    "icml": {"dir": "icml", "start": 2010},
    "iclr": {"dir": "iclr", "start": 2013},
    "aaai": {"dir": "aaai", "start": 2010},
    "ijcai": {"dir": "ijcai", "start": 2010},
    "aistats": {"dir": "aistats", "start": 2010},
    "uai": {"dir": "uai", "start": 2010},
    "colt": {"dir": "colt", "start": 2010},
    "mlsys": {"dir": "mlsys", "start": 2019},
    # CV
    "cvpr": {"dir": "cvpr", "start": 2010},
    "iccv": {"dir": "iccv", "start": 2011, "step": 2},  # odd years only
    "eccv": {"dir": "eccv", "start": 2010, "step": 2},  # even years only
    "bmvc": {"dir": "bmvc", "start": 2015},
    "accv": {"dir": "accv", "start": 2010, "step": 2},
    "miccai": {"dir": "miccai", "start": 2015},
    # NLP / IR
    "acl": {"dir": "acl", "start": 2010},
    "emnlp": {"dir": "emnlp", "start": 2010},
    "naacl": {"dir": "naacl", "start": 2010},
    "eacl": {"dir": "eacl", "start": 2012},
    "coling": {"dir": "coling", "start": 2010, "step": 2},
    "findings": {"dir": "findings", "start": 2020},  # ACL Findings
    "sigir": {"dir": "sigir", "start": 2015},
    "wsdm": {"dir": "wsdm", "start": 2015},
    "cikm": {"dir": "cikm", "start": 2015},
    "www": {"dir": "www", "start": 2015},
    # Systems / Data / HCI
    "kdd": {"dir": "kdd", "start": 2010},
    "chi": {"dir": "chi", "start": 2015},
    "sigmod": {"dir": "sigmod", "start": 2015},
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
    # LLM / recent
    "colm": {"dir": "colm", "start": 2024},
    # Journals (use toc for journal volumes)
    "tacl": {"dir": "tacl", "start": 2013, "type": "journals"},
    "jmlr": {"dir": "jmlr", "start": 2010, "type": "journals"},
}

CURRENT_YEAR = 2026


def _year_range(conf: dict[str, Any]) -> list[int]:
    """Generate the list of years for a conference."""
    start = conf["start"]
    end = conf.get("end", CURRENT_YEAR)
    step = conf.get("step", 1)
    return list(range(start, end + 1, step))


# -- BibTeX parsing --


def _parse_bib_entries(bib_text: str) -> list[tuple[str, str]]:
    """Parse BibTeX text into (normalized_title, raw_bibtex_string) pairs."""
    results: list[tuple[str, str]] = []
    entries = re.split(r'(?=@\w+\{)', bib_text)

    for entry in entries:
        entry = entry.strip()
        if not entry or not entry.startswith("@"):
            continue

        title_match = re.search(
            r'^\s*title\s*=\s*\{(.+?)\}\s*[,}]',
            entry,
            re.MULTILINE | re.DOTALL,
        )
        if not title_match:
            continue

        title = title_match.group(1).strip()
        clean_title = re.sub(r'[{}]', '', title)
        norm = normalize_title(clean_title)

        if norm:
            # Remove noisy DBLP metadata fields
            cleaned = entry
            for field in ("month", "timestamp", "biburl", "bibsource"):
                cleaned = re.sub(
                    rf'^\s*{field}\s*=\s*\{{[^}}]*\}}\s*,?\s*\n?',
                    '',
                    cleaned,
                    flags=re.MULTILINE,
                )
            results.append((norm, cleaned.strip()))

    return results


# -- Data I/O --


def _year_path(conf_name: str, year: int) -> Path:
    """Path to a single year's JSON file."""
    return DATA_DIR / conf_name / f"{year}.json"


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
    """Save a single year file. Creates directories as needed."""
    path = _year_path(conf_name, year)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    return path


# -- Download --


def _build_toc_query(conf_name: str, conf: dict[str, Any], year: int) -> str:
    """Build DBLP toc query string."""
    dblp_dir = conf["dir"]
    db_type = conf.get("type", "conf")
    if db_type == "journals":
        return f"toc:db/journals/{dblp_dir}/{dblp_dir}{year}.bht:"
    return f"toc:db/conf/{dblp_dir}/{conf_name}{year}.bht:"


def _download_venue_year(
    client: httpx.Client,
    conf_name: str,
    conf: dict[str, Any],
    year: int,
    console: Console,
) -> dict[str, str] | None:
    """Download all BibTeX entries for one conference year.

    Returns {norm_title: bib_entry}, or None on network/server error.
    """
    query = _build_toc_query(conf_name, conf, year)
    entries: dict[str, str] = {}

    for step in range(5):  # max 5 pages of 1000
        url = "https://dblp.org/search/publ/api"
        params = {"q": query, "h": "1000", "f": str(step * 1000), "format": "bib"}

        for attempt in range(3):
            try:
                resp = client.get(url, params=params)
                if resp.status_code == 429:
                    wait = (attempt + 1) * 20
                    console.print(f"  [yellow]Rate limited, waiting {wait}s...[/]", highlight=False)
                    time.sleep(wait)
                    continue
                if resp.status_code == 503:
                    raise httpx.HTTPStatusError(
                        f"503 Service Unavailable", request=resp.request, response=resp
                    )
                resp.raise_for_status()
                break
            except httpx.HTTPError as e:
                if attempt < 2:
                    time.sleep(5)
                    continue
                console.print(f"  [red]Error: {e}[/]", highlight=False)
                return None
        else:
            return None

        bib_text = resp.text.strip()
        if not bib_text:
            break

        parsed = _parse_bib_entries(bib_text)
        if not parsed:
            break

        for norm_title, bib_entry in parsed:
            entries[norm_title] = bib_entry

        if len(parsed) < 900:
            break

        time.sleep(5)  # polite delay between pages

    return entries


def sync(
    conferences: list[str] | None = None,
    years: list[int] | None = None,
    console: Console | None = None,
) -> None:
    """Download DBLP proceedings and build local JSON database.

    Args:
        conferences: List of conference names to sync (default: all).
        years: Only sync these specific years (default: all years for each conference).
    """
    console = console or Console(stderr=True)

    targets = conferences or list(CONFERENCES.keys())
    invalid = [c for c in targets if c not in CONFERENCES]
    if invalid:
        console.print(f"[red]Unknown conferences: {', '.join(invalid)}[/]")
        console.print(f"[dim]Available: {', '.join(sorted(CONFERENCES.keys()))}[/]")
        return

    with httpx.Client(timeout=60.0) as client:
        for conf_name in targets:
            conf = CONFERENCES[conf_name]
            all_years = _year_range(conf)
            sync_years = [y for y in all_years if y in years] if years else all_years

            if not sync_years:
                continue

            console.print(f"\n[bold]{conf_name}[/] ({len(sync_years)} years)")

            total_new = 0
            consecutive_errors = 0
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                console=console,
            ) as progress:
                task = progress.add_task(f"  {conf_name}", total=len(sync_years))

                for year in sync_years:
                    progress.update(task, description=f"  {conf_name} {year}")
                    entries = _download_venue_year(client, conf_name, conf, year, console)

                    if entries is None:
                        consecutive_errors += 1
                        if consecutive_errors >= 3:
                            console.print(f"  [red]Aborting {conf_name}: server unavailable[/]")
                            break
                    else:
                        consecutive_errors = 0
                        if entries:
                            existing = _load_year(conf_name, year)
                            existing.update(entries)
                            _save_year(conf_name, year, existing)
                            total_new += len(entries)

                    progress.advance(task)
                    time.sleep(1)  # polite inter-year delay

            if total_new > 0:
                console.print(f"  [green]+{total_new} entries synced[/]")
            else:
                console.print(f"  [yellow]No new entries[/]")


# -- Search --


def _load_db() -> dict[str, str]:
    """Load all year JSON files from data directory into a single lookup dict."""
    db: dict[str, str] = {}
    if not DATA_DIR.exists():
        return db
    for path in DATA_DIR.rglob("*.json"):
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
    """
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
) -> None:
    """Download DBLP proceedings and build local JSON database."""
    targets = [c.strip() for c in conferences.split(",")] if conferences else None
    year_list = [int(y.strip()) for y in year.split(",")] if year else None
    sync(conferences=targets, years=year_list)


@app.command("search")
def cli_search(
    title: Annotated[str, typer.Argument(help="Paper title to search for")],
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    max_results: Annotated[int, typer.Option("--max", "-n", help="Max substring match results")] = 5,
) -> None:
    """Search local database by title."""
    results = search(title, max_results=max_results)
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

        conf_count = 0
        year_files = sorted(conf_dir.glob("*.json"))
        for path in year_files:
            try:
                data = json.loads(path.read_text())
                conf_count += len(data)
            except (json.JSONDecodeError, OSError):
                pass
        total += conf_count
        year_range = ""
        if year_files:
            years = [p.stem for p in year_files]
            year_range = f" ({years[0]}–{years[-1]})"
        console.print(f"  {conf_dir.name:20s} {conf_count:>6,} entries{year_range}")

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


if __name__ == "__main__":
    app()
