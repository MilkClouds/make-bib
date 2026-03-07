---
name: make-bib
description: Generate accurate BibTeX for a paper
---

# make-bib

$ARGUMENTS — `arxiv:ID`, `doi:ID`, title in quotes, or abbreviation

For deeper background on source characteristics, see `${CLAUDE_SKILL_DIR}/citation-guide.md`.

## Rules

- **When in doubt, ask.**: citation involves judgment calls the user should make. Use `AskUserQuestion` whenever the right choice isn't clear — multiple candidates for the same title, ambiguous venue, workshop vs main track, conflicting metadata across sources. Silent guessing risks misrepresentation.
- **Single source of truth**: all fields in one entry MUST come from the same source. Never mix — not even "just the author order" from another source. If metadata differs between sources, use the chosen source as-is or `AskUserQuestion`.
- **Honest representation**: never cite a preprint as published or vice versa. Workshop papers must have "Workshop" in booktitle — using only the parent conference name is misrepresentation.
- **Discovery ≠ citation**: tools that help find papers (S2, Google Scholar, etc.) optimize for coverage, not metadata accuracy. Use them for discovery and ID collection, but never copy their venue names, author formatting, or dates into BibTeX fields.
- **Entry type**: conference/workshop → `@inproceedings`. Journal → `@article`. Preprint → per `[arxiv].entry_type`.
- **`bibstyle.toml` is law**: when present, it MUST override all defaults — source priority, fields, formatting. See schema section below.

## Tools

`uv run ${CLAUDE_SKILL_DIR}/scripts/paper_sources.py`:
- `fetch <id>` — ID-based fetch from all sources (arxiv:, doi:, dblp:, openreview:). `--json` for structured output.
- `search <source> "<title>"` — title search (dblp, crossref, arxiv, openreview, s2).

`uv run ${CLAUDE_SKILL_DIR}/scripts/dblp_local.py`:
- `sync` — download/update local DBLP database.
- `search "<title>"` — search local DB by normalized title. No rate limit — prefer over API calls.

**Rate limits**: External APIs have rate limits. Do not run more than 3 concurrent make-bib invocations. On 429 errors, wait and retry once — do not spawn more subagents to work around it.

## Workflow

Every step is mandatory. Skipping any step is a failure.

### 0. Check for `bibstyle.toml`

MUST run before any other step. Look for `bibstyle.toml` in the working directory.

- **Found** → read it and apply. Proceed to step 1.
- **Not found** → MUST stop and `AskUserQuestion` whether to (1) use the defaults from the schema section below, or (2) customize specific settings. Do not proceed to step 1 until the user answers.

### 1. Find the paper

**Goal**: identify the paper and collect external IDs (DOI, arXiv, DBLP key, ACL ID).

Non-paper input (software, dataset, book) → `AskUserQuestion` for citation format. Stop.

ID input → `fetch`. Title/abbreviation → `search s2` → get IDs → `fetch`.

**Disambiguation**: if the input is not an ID or exact full title and S2 returns multiple plausible matches, always `AskUserQuestion` — never silently pick one.

S2 is useful here for discovery — broad coverage, returns external IDs quickly. But S2 metadata (venue names, dates) is unreliable and must not carry over to later steps.

**Output**: log paper title and collected IDs.

### 2. Determine publication status

**Goal**: know whether the paper is formally published, and at which venue — or whether it remains a preprint.

`fetch --json <ID>` returns S2 venue hints and external IDs. These hints need confirmation from more authoritative sources:

- **Curated DB** (CS: `search dblp "<exact title>"`) — if DBLP lists it under a venue, it's formally published there.
- **Review platform** (`search openreview "<exact title>"`) — confirms acceptance decisions directly. Check `invitation` field to distinguish workshop from main track.
- **Publisher page** — presence in ACL Anthology, ACM DL, PMLR, etc. is definitive.

No venue confirmed → treat as arXiv preprint.

**Output**: log `status: published at {venue}` or `status: preprint`.

### 3. Get BibTeX

**Goal**: obtain citation data from the most authoritative source available.

**If step 2 confirmed a formal venue, never use arXiv as the BibTeX source.** Use the publisher (Tier 1) or DBLP (Tier 2). arXiv is only a BibTeX source for confirmed preprints — papers with no venue after step 2.

The hierarchy reflects trustworthiness — use the best source you can reach:

**Tier 1 — Publisher / Anthology** (authoritative metadata direct from publisher):

| Source | URL | Scope |
|--------|-----|-------|
| ACL Anthology | `https://aclanthology.org/{id}.bib` | DOI prefix `10.18653/` |
| PMLR | `https://proceedings.mlr.press/v{vol}/{key}.html` | ICML, AISTATS, CoRL, COLT, UAI, ALT |
| arXiv | `https://arxiv.org/abs/{id}` | Preprint (no formal venue confirmed in step 2). Construct `@article` per `[arxiv]` settings |
| Other publishers | ACM DL, IEEE Xplore, Springer, etc. | Any venue with official proceedings page |

**Tier 2 — Curated DB** (normalized, reliable for CS):

| Source | URL | Scope |
|--------|-----|-------|
| DBLP | `https://dblp.org/rec/{key}.bib` | By key, by title (local DB), or by DOI (`dblp.org/doi/{doi}.bib`) |
| Others by field | INSPIRE-HEP (physics), ADS (astronomy), PubMed (medicine), etc. | See `[sources]` in bibstyle.toml |

**Tier 3 — Fallback** (constructed from API data — requires `⚠ UNVERIFIED` annotation):

| Source | Provenance URL | Scope |
|--------|---------------|-------|
| CrossRef | `https://doi.org/{doi}` | DOI exists, no higher-tier source. Construct from API JSON |
| OpenReview | `https://openreview.net/forum?id={id}` | Recent acceptances or workshops not yet in Tier 1–2. Auto-generated BibTeX — verify venue name and fields |

Constructing from CrossRef: `title`→title, `author[].family/given`→author, `container-title`→journal/booktitle, `published.date-parts`→year.

### 4. Validate, format, and output

**Goal**: a correct, consistently formatted entry with clear provenance.

Check rules. Format per `bibstyle.toml` (see schema section below).

Annotate with provenance. The `% source:` line MUST exactly match where the BibTeX was obtained — never mix namespaces (e.g., never write `arxiv:X via dblp`). Tier 1–2 get a source line; Tier 3 gets an additional warning:
```
% source: dblp:conf/cvpr/HeZRS16 via dblp (https://dblp.org/rec/conf/cvpr/HeZRS16.bib)

% ⚠ UNVERIFIED — constructed from API data, not from authoritative source
% source: doi:10.xxx via crossref (https://doi.org/10.xxx)
```

Output the annotated BibTeX entry only.

### 5. Pre-output checklist

**Goal**: catch mistakes before the user sees them. Walk through every item; if any fails, fix and re-check.

1. **Entry type** — conference/workshop → `@inproceedings`, journal → `@article`, preprint → per `[arxiv].entry_type`?
2. **Venue name** — read `[venue].style` (default: `abbreviated`). Compare the booktitle you are about to output against the style: abbreviated → must be a short acronym (e.g., RSS, NeurIPS, ACL, CVPR), not a descriptive name. Full → official name. `proceedings_prefix` true → prepend "Proceedings of". Sources (including DBLP) return full names — you must convert.
3. **Fields** — only those in `[fields]` for this entry type? No extra fields (editor, publisher, address, etc.) unless explicitly listed.
4. **Key style** — `[key].style` (default: `lastname_year`): `lastname_year` → `he2016deep`, `lastname_venue_year` → `he2016cvpr`, `acl` → ACL Anthology ID.
5. **Single source** — every field from exactly one source? No mixing across sources.
6. **Source line** — `% source:` exactly matches the actual BibTeX source? Tier 3 has `⚠ UNVERIFIED`?
7. **Honest representation** — preprint not cited as published? Workshop has "Workshop" in booktitle?

## `bibstyle.toml` schema

When present, `bibstyle.toml` MUST be followed — it strictly overrides all defaults. `[sources].verify` and `[sources].bibtex` replace the default tier order — only listed sources are used, in the listed order.

**If absent, the defaults shown below still apply.** Do not treat missing bibstyle.toml as "no formatting rules" — the schema defines the defaults.

```toml
[sources]
# Discovery & verification: checked to determine publication status
verify = ["s2", "dblp", "openreview"]
# BibTeX citation: tried in priority order (Tier 1 → Tier 3)
bibtex = ["acl_anthology", "pmlr", "dblp", "crossref", "arxiv"]
# Available: acl_anthology, pmlr, dblp, openreview, crossref, arxiv, inspire_hep, ads, pubmed

[fields]
conference = ["title", "author", "booktitle", "year"]
journal = ["title", "author", "journal", "year", "volume", "number"]
# Optional: "pages", "doi", "url", "publisher", "address", "editor", "month"

[authors]
max = 0  # 0 = unlimited

[venue]
style = "abbreviated"       # "abbreviated" or "full"
proceedings_prefix = false   # true: "Proceedings of NeurIPS"

[key]
style = "lastname_year"     # "lastname_year", "lastname_venue_year", "acl"

[arxiv]
entry_type = "article"                      # "article" or "misc"
journal_format = "arXiv preprint arXiv:{id}" # or "CoRR"
```
