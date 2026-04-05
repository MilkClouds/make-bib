---
name: make-bib
description: >
  Generate accurate BibTeX entries from authoritative sources (DBLP, ACL Anthology, PMLR, CrossRef, arXiv).
  Use this skill whenever the user needs a citation, BibTeX entry, bibliography fix, or wants to look up
  where/whether a paper was published — even if they don't explicitly say "BibTeX." Triggers on: paper titles,
  arXiv IDs, DOIs, DBLP keys, "cite this paper", "add to references", reference list verification, or any
  academic citation task.
---

# make-bib

`$ARGUMENTS` — accepts `arxiv:ID`, `doi:ID`, `dblp:KEY`, `openreview:ID`, a title in quotes, or an abbreviation.

For background on how bibliographic sources work and their reliability characteristics, see `${CLAUDE_SKILL_DIR}/citation-guide.md`.

## Principles

Each principle exists because a specific class of citation error is common and hard to catch after the fact.

**Ask when uncertain.** Citations involve judgment calls — which of two similar titles is the right paper, whether something is workshop or main track, what venue a paper belongs to. Guessing wrong means the user silently gets a wrong citation in their manuscript. Use `AskUserQuestion` for any ambiguous case: multiple candidates, unclear venue, conflicting metadata across sources.

**One source per entry.** Every field in a BibTeX entry (title, authors, year, venue) should come from the same source. Mixing metadata across sources — even "just the author order" from a different database — creates entries where no single source can verify the whole record. If sources disagree on a field, use the chosen source as-is or ask the user.

**Discovery tools are not citation sources.** Semantic Scholar and Google Scholar optimize for finding papers, not for metadata accuracy. Their venue names, dates, and author formatting frequently contain errors. Use them to locate papers and collect external IDs, then get the actual BibTeX from authoritative sources downstream.

**Honest representation.** Citing a preprint as a published paper (or vice versa) is academic misrepresentation. Workshop papers need "Workshop" in the booktitle — using only the parent conference name makes them look like main-track publications.

**Entry types follow publication status.** Conference or workshop paper → `@inproceedings`. Journal article → `@article`. Preprint → per `[arxiv].entry_type` in bibstyle.toml.

**`bibstyle.toml` governs formatting.** When present in the working directory, it overrides all defaults for field selection, venue style, key format, and arxiv conventions. When absent, the defaults in the schema section below still apply.

## Tools

`uv run ${CLAUDE_SKILL_DIR}/scripts/paper_sources.py`:
- `fetch <id>` — fetch metadata from all sources by ID (`arxiv:`, `doi:`, `dblp:`, `openreview:`). Add `--json` for structured output.
- `search <source> "<title>"` — title search on a single source (`dblp`, `crossref`, `arxiv`, `openreview`, `s2`).

`uv run ${CLAUDE_SKILL_DIR}/scripts/dblp_local.py`:
- `sync` — download or update the local DBLP database.
- `search "<title>"` — search the local DB by normalized title. No rate limit — prefer this over API calls for CS paper discovery.

Rate limits apply to external APIs. Keep concurrent make-bib invocations to 3 or fewer. On 429 errors, wait and retry once — don't spawn extra subagents to work around throttling.

## Workflow

### 0. Prerequisites

Check two things before starting.

**`bibstyle.toml`** — look in the working directory:
- Found → read it; all formatting decisions come from this file.
- Not found → ask the user: (1) create with defaults from the schema section below, or (2) customize settings first. Write the file before proceeding.

**`SEMANTIC_SCHOLAR_API_KEY`** — check the environment:
- Set → proceed.
- Not set → ask the user with options: (1) paste a key (free at semanticscholar.org/product/api) — write it to `.env`, (2) skip — proceed with `--allow-no-s2-key`, noting that unauthenticated requests face heavy throttling.

### 1. Find the paper

Identify the paper and collect its external IDs (DOI, arXiv ID, DBLP key, ACL ID).

- **ID input** → run `fetch`.
- **Title or abbreviation** → run `search s2` to locate the paper and collect IDs, then `fetch` with those IDs.
- **Non-paper input** (software, dataset, book) → ask for the desired citation format and stop.

If the input is ambiguous and search returns multiple plausible matches, ask the user to pick. A wrong paper is worse than a brief interruption.

Log the paper title and collected IDs before moving on.

### 2. Determine publication status

Determine whether the paper is formally published (and where) or still a preprint. This distinction drives everything downstream — a published paper should be cited at its venue, not as an arXiv preprint.

Check in order of authority:

1. **DBLP** (local DB first, then API) — if DBLP lists it under a venue, it's published there. Try title search, key lookup, and DOI. Published titles sometimes differ from arXiv titles, so try multiple approaches before concluding it's absent.
2. **OpenReview** (`search openreview "<exact title>"`) — confirms acceptance decisions directly. Check the `invitation` field to distinguish workshop from main track.
3. **Publisher page** — presence in ACL Anthology, ACM DL, PMLR, IEEE Xplore, or Springer is definitive.

If no venue is confirmed after exhausting these → treat as arXiv preprint.

Log: `status: published at {venue}` or `status: preprint`.

### 3. Get BibTeX

Obtain citation data from the most authoritative source available.

The critical constraint: **if step 2 confirmed a formal venue, do not use arXiv as the BibTeX source.** arXiv metadata reflects the preprint version — page numbers, venue, and sometimes even author lists differ from the published version. arXiv is a BibTeX source only for confirmed preprints (papers with no venue after step 2).

Try every source in tier order before falling back. A single failed method (e.g., title search miss) does not exhaust a source — try other methods (DOI lookup, key lookup, proceedings page) before moving to the next tier.

**Tier 1 — Publisher / Anthology** (authoritative metadata direct from publisher):

| Source | URL pattern | Scope |
|--------|-------------|-------|
| ACL Anthology | `aclanthology.org/{id}.bib` | DOI prefix `10.18653/` |
| PMLR | `proceedings.mlr.press/v{vol}/{key}.html` | ICML, AISTATS, CoRL, COLT, UAI, ALT |
| arXiv | `arxiv.org/abs/{id}` | Preprints only — no venue confirmed in step 2 |
| Other publishers | ACM DL, IEEE Xplore, Springer, etc. | Any venue with official proceedings |

**Tier 2 — Curated DB** (normalized, reliable):

| Source | URL pattern | Scope |
|--------|-------------|-------|
| DBLP | `dblp.org/rec/{key}.bib` | By key, title (local DB), or DOI (`dblp.org/doi/{doi}.bib`) |
| Field-specific | INSPIRE-HEP, ADS, PubMed | Non-CS papers |

**Tier 3 — Fallback** (constructed from API data — annotate as unverified):

| Source | URL pattern | Scope |
|--------|-------------|-------|
| CrossRef | `doi.org/{doi}` | DOI exists, no higher-tier source available |
| OpenReview | `openreview.net/forum?id={id}` | Recent acceptances not yet in Tier 1–2 |

CrossRef construction: `title` → title, `author[].family/given` → author, `container-title` → journal/booktitle, `published.date-parts` → year.

### 4. Format and output

Apply formatting from `bibstyle.toml` (or defaults if absent — see schema below).

Add a provenance comment showing exactly where the BibTeX came from. This lets the user (and future tools) trace each entry back to its source:

```bibtex
% source: dblp:conf/cvpr/HeZRS16 via dblp (https://dblp.org/rec/conf/cvpr/HeZRS16.bib)
@inproceedings{he2016deep,
  ...
}
```

Tier 3 sources get an additional warning — the user should know this entry wasn't verified against an authoritative source:

```bibtex
% ⚠ UNVERIFIED — constructed from API data, not from authoritative source
% source: doi:10.xxx via crossref (https://doi.org/10.xxx)
```

Output the annotated BibTeX entry.

### 5. Self-check

Walk through every item before outputting. If anything fails, fix it and re-check.

1. **Entry type** — matches publication status? Conference/workshop → `@inproceedings`, journal → `@article`, preprint → per `[arxiv].entry_type`.
2. **Venue name** — matches `[venue].style`? Default is `abbreviated`, meaning short acronyms (NeurIPS, ACL, CVPR) not descriptive names. Sources including DBLP return full names — convert them. If `proceedings_prefix` is true, prepend "Proceedings of".
3. **Fields** — only those listed in `[fields]` for this entry type? Strip stray fields (editor, publisher, address) unless they're explicitly configured.
4. **Key style** — matches `[key].style`? `lastname_year` → `he2016deep`, `lastname_venue_year` → `he_cvpr2016`, `acl` → ACL Anthology ID.
5. **Single source** — every field from exactly one source? No mixing.
6. **Source line** — `% source:` matches the actual BibTeX source? Tier 3 has `⚠ UNVERIFIED`?
7. **Honest representation** — preprint not cited as published? Workshop has "Workshop" in booktitle?

## `bibstyle.toml` schema

Controls all formatting. When present, overrides defaults. When absent, these defaults still apply — a missing file does not mean "no formatting rules."

```toml
[fields]
conference = ["title", "author", "booktitle", "year"]
journal = ["title", "author", "journal", "year", "volume", "number"]
# Optional fields: "pages", "doi", "url", "publisher", "address", "editor", "month"

[authors]
max = 0  # 0 = unlimited

[venue]
style = "abbreviated"       # "abbreviated" or "full"
proceedings_prefix = false   # true → "Proceedings of NeurIPS"

[key]
style = "lastname_year"     # "lastname_year", "lastname_venue_year", "acl"

[arxiv]
entry_type = "article"                       # "article" or "misc"
journal_format = "arXiv preprint arXiv:{id}" # or "CoRR"
```
