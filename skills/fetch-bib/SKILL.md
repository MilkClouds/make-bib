---
name: fetch-bib
description: Fetch and verify BibTeX from authoritative sources. Use for citations, paper identifiers or titles, publication lookups, bibliography repairs, and .bib verification.
license: MIT
compatibility: Requires paperstack-cli>=0.3.2, Python 3.11+, uv, and network access for uncached lookups.
metadata:
  author: MilkClouds
  version: "2.0.0"
---

# fetch-bib

Use Paperstack to discover papers and inspect source records. The agent remains responsible for selecting the citable version, choosing one source, formatting BibTeX, and editing bibliography files.

## Principles

These rules are mandatory because violations produce plausible but incorrect citations.

1. **Ask when uncertain.** Stop for multiple plausible papers, conflicting venue records, or unclear workshop/main-track status. Never silently choose.
2. **Use one source per entry.** Every bibliographic field must be traceable to the selected record. Do not merge author lists, titles, years, pages, or venues across sources.
3. **Separate discovery from citation.** Semantic Scholar may locate a work and its identifiers, but is not a BibTeX source. Google Scholar is neither a source nor a publication-status authority.
4. **Represent publication status honestly.** Cite a formal publication instead of its preprint. Mark workshops as workshops. If no formal venue can be confirmed, cite the preprint.
5. **Derive the entry type from status.** Conference or workshop: `@inproceedings`; journal: `@article`; preprint: the configured arXiv type.
6. **Treat `bibstyle.toml` as authoritative for formatting.** It controls included fields, author limits, venue style, citation keys, and arXiv representation; it never overrides factual source metadata.

## Paperstack contract

Use structured output for all decisions:

```bash
paperstack paper metadata arxiv:2106.09685 --json
paperstack paper metadata doi:10.1109/CVPR.2016.90 --source crossref --json
paperstack paper metadata dblp:conf/nips/VaswaniSPUJGKP17 --source dblp --json
paperstack paper search "Attention Is All You Need" --source semantic-scholar --json
paperstack paper search "Attention Is All You Need" --source dblp --json
```

`metadata` accepts `arxiv:`, `doi:`, `dblp:`, and `openreview:`. Paperstack returns source records; it does not choose a citation or synthesize a final entry.

Do not configure a Paperstack corpus. `paperstack paper` and the optional DBLP index work without one.

## Workflow

Follow steps 0 through 5 in order. Do not produce or edit BibTeX before completing the publication-status and source-selection steps.

### 0. Prepare

1. Run `paperstack --help`.
   - If missing, ask before `uv tool install 'paperstack-cli>=0.3.2'`.
   - If the commands above are unavailable, stop and ask the user to upgrade Paperstack.
2. Check the working directory for `bibstyle.toml`.
   - If present, read it.
   - If absent, ask whether to create the defaults below or customize them. Write the chosen file before continuing.
3. Only when Semantic Scholar discovery is needed, run `paperstack config status`.
   - If its API key is absent, offer to continue with lower unauthenticated limits or have the user run `paperstack config set semantic-scholar.api-key`.
   - Never ask the user to paste a secret into chat and never write it to `.env`.
4. For bulk, offline, or repeated DBLP lookup, run `paperstack index dblp status --json`. Ask before `paperstack index dblp install` when the local selected-venue index would materially help. Online DBLP search remains valid.

### 1. Identify the work

- For an identifier, call `paperstack paper metadata <id> --json` and collect all stable IDs in the record.
- For a title or abbreviation, search Semantic Scholar to discover candidates and IDs, then search DBLP by exact title and any discovered DOI or key.
- For software, datasets, books, or other non-paper input, ask what citation form the user expects before continuing.

Confirm the title and identifiers before moving on. If candidates are ambiguous, show concise distinguishing details and ask the user to select one.

### 2. Determine publication status

Decide whether the work is a conference paper, workshop paper, journal article, or preprint. Check records in this order:

1. A field-specific anthology or official publisher page, when an identifier points to one.
2. DBLP through Paperstack, using title, DBLP key, and DOI where available.
3. OpenReview through Paperstack for acceptance and workshop/main-track status.
4. Crossref through Paperstack or an official conference page when the earlier checks are inconclusive.

Try alternate identifiers before treating a source as exhausted; published and preprint titles can differ. An optional DBLP index miss is not proof that a paper is unpublished.

If authoritative records conflict, ask the user. If no formal venue is confirmed after these checks, classify the work as a preprint.

### 3. Select the BibTeX source

Select exactly one source using the first applicable tier:

1. **Official publisher or anthology.** Prefer ACL Anthology records returned by Paperstack. When Paperstack lacks an adapter for PMLR, ACM, IEEE, Springer, or another publisher, use that publisher's official BibTeX export directly.
2. **arXiv through Paperstack.** Use only when step 2 classified the work as a preprint.
3. **DBLP through Paperstack.** The normal curated source for published CS papers when an official export is unavailable.
4. **Crossref or OpenReview through Paperstack.** Use only as an explicitly unverified fallback.

For a formally published work, never fall back to its arXiv record. If Paperstack returns `bibtex`, format that entry. Otherwise map only fields present in the selected structured record. Do not invent missing fields or add another local source wrapper.

### 4. Format and deliver

Apply `bibstyle.toml`. Mechanical changes may normalize whitespace, protect significant capitalization, remove DBLP author disambiguation suffixes such as `0001`, format the venue, and remove excluded fields. They must not change factual metadata or author order.

Add provenance immediately before every entry:

```bibtex
% source: dblp:conf/cvpr/HeZRS16 via paperstack/dblp (https://dblp.org/rec/conf/cvpr/HeZRS16.html)
@inproceedings{he2016deep,
  ...
}
```

Crossref and OpenReview fallback entries require both lines:

```bibtex
% UNVERIFIED - constructed from a fallback source record
% source: doi:10.example/record via paperstack/crossref (https://doi.org/10.example/record)
```

If the user requested only BibTeX, return it without changing files. For an add, repair, or bulk verification request, inspect the target bibliography first. Detect duplicates by DOI, arXiv ID, normalized title, and key; preserve local ordering and formatting; change only requested entries. Ask before replacing a duplicate under another key or resolving a key collision.

### 5. Self-check

Check every item before delivery; fix failures or disclose unresolved uncertainty.

1. The work and stable IDs match the request.
2. Publication status and entry type agree.
3. A workshop is visibly identified as a workshop.
4. A published work is not sourced from arXiv.
5. All factual fields come from the selected source record.
6. Fields, authors, venue, key, and arXiv form follow `bibstyle.toml`.
7. The provenance URL resolves to the record actually used.
8. Crossref or OpenReview fallback data is marked `UNVERIFIED`.

## Default `bibstyle.toml`

```toml
[fields]
conference = ["title", "author", "booktitle", "year"]
journal = ["title", "author", "journal", "year", "volume", "number"]

[authors]
max = 0

[venue]
style = "abbreviated"
proceedings_prefix = false

[key]
style = "lastname_year"

[arxiv]
entry_type = "article"
journal_format = "arXiv preprint arXiv:{id}"
```

`authors.max = 0` means unlimited. Supported venue styles are `abbreviated` and `full`; key styles are `lastname_year`, `lastname_venue_year`, and `acl`; arXiv entry types are `article` and `misc`. Field lists are allowlists. Preserve unknown configuration keys and prefer explicit user settings over these defaults.

## Failure behavior

When the user forbids network access, pass `--offline` to Paperstack. If the needed source record is not cached, stop rather than silently weakening verification. On source failure, proceed through the tier order and disclose the fallback; do not conceal missing or conflicting evidence.
