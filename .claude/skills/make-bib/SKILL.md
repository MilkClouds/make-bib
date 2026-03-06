---
name: make-bib
description: Generate accurate BibTeX for a paper by fetching metadata from multiple academic sources
---

# make-bib: Generate accurate BibTeX for a paper

$ARGUMENTS — `arxiv:ID`, `doi:ID`, `openreview:ID`, title in quotes, or abbreviation (e.g. "ResNet")

The script is at `scripts/paper_sources.py` (run via `uv run scripts/paper_sources.py`).

## Steps

1. **Find the venue.** If a venue exists, failing to find it is unacceptable.

   **Phase A — Obtain ID:** Get at least one paper ID and the canonical title.
   - ID input (`arxiv:`, `doi:`, `openreview:`): use directly.
   - Title/abbreviation input: `search s2 "<query>"` → if multiple candidates, use `AskUserQuestion` to let the user pick → obtain ID.

   **Phase B — Confirm venue:** Determine the highest-priority venue.
   - `fetch --json <ID>` → check S2 `venue` and `externalIds`.
   - Always cross-search by title, even when S2 reports a clear venue:
     - `search openreview "<full paper title>"` — use the complete title, not abbreviations.
     - `search dblp "<title>"` — check for DBLP listing.
     - If multiple or ambiguous results, use `AskUserQuestion` to let the user pick.
     - If a published version is found, record that source's ID (e.g. `openreview:xxx`).
     - If nothing found after all searches: confirmed as arXiv preprint.
   - Use `fetch` and `search` as many times as needed. Be thorough.

2. **Generate BibTeX from a single source of truth** — never mix fields from multiple sources.
   Pick the first matching official source and use it exclusively:
   - **OpenReview `_bibtex`**: If an OpenReview ID was found, `fetch openreview:<id>` → use the `_bibtex` field.
   - **ACL Anthology**: If the DOI starts with `10.18653/`, fetch the ACL Anthology BibTeX.
   - **arXiv**: If the paper is an arXiv preprint, `fetch arxiv:<id>` → construct from arXiv metadata.
   If an official source is used, go to step 4. Otherwise go to step 3.

3. **Fallback: construct BibTeX with human verification.** Use DBLP, CrossRef, and other aggregators as reference data. Present all available source data, and use `AskUserQuestion` (2–4 options with `label` + `description`) for every ambiguous field. Add a BibTeX comment:
   ```
   % NOTE: not from official source — double-check
   ```

4. **Apply `bibstyle.toml`** from the project root. If missing, ask via `AskUserQuestion` and create it. See schema below. Reformat the BibTeX to match user preferences (fields, venue style, author limits, key format, etc.).

5. **Annotate** the BibTeX with a comment above the entry:
   ```
   % source: <paper_id> via <source_name>
   ```
   Examples:
   - `% source: openreview:0JtNyaHbNx via openreview` — OpenReview `_bibtex`
   - `% source: doi:10.18653/v1/N19-1423 via acl_anthology` — ACL Anthology BibTeX
   - `% source: dblp:conf/cvpr/HeZRS16 via dblp` — DBLP (fallback)
   - `% source: doi:10.1038/nature14539 via crossref` — CrossRef (fallback)
   - `% source: arxiv:1706.03762 via arxiv` — arXiv metadata

6. Output ONLY the annotated BibTeX entry.

**Hard rules**:
- Venue precedence: Journal > Conference > Workshop > arXiv
- Protect proper nouns/acronyms: `{BERT}`, `{B}ayesian` — don't over-brace.
- Authors: `Last, First and Last, First`. Remove DBLP disambiguation numbers.
- Authors and all other fields must come from the same official source (step 2).
- When truncating authors with `and others`, count `and` separators mechanically.

**Pitfalls** (learned from real errors):
- S2 is only reliable for venue/ID discovery. Its author names can map to wrong people (e.g. "Qiang Liu" → "Qian Liu"), and its venue field omits track-level detail (e.g. "NeurIPS" for both main conference and workshops).
- OpenReview search results may include DBLP mirror notes (`invitation: "DBLP.org/-/Record"`). These lack track-level venue info. When picking a forum ID to fetch, prefer notes whose `invitation` contains the venue domain (e.g. `NeurIPS.cc/`, `ICLR.cc/`).

## `bibstyle.toml` schema and defaults

```toml
[fields]
# Which fields to include per entry type.
conference = ["title", "author", "booktitle", "year"]  # minimal
journal = ["title", "author", "journal", "year", "volume", "number"]
# Other fields you can add: "pages", "doi", "url", "publisher", "address", "editor", "month"

[authors]
# Max authors before truncating with "and others". 0 = no limit.
max = 0

[venue]
# "abbreviated" (NeurIPS) or "full" (Advances in Neural Information Processing Systems)
style = "abbreviated"
# Whether to prefix with "Proceedings of"
proceedings_prefix = false

[key]
# "lastname_year" (vaswani2017), "lastname_venue_year" (vaswani_neurips2017), "acl" (devlin-etal-2019-bert)
style = "lastname_year"

[arxiv]
# Entry type for arXiv preprints: "article" or "misc"
entry_type = "article"
# Journal field format. {id} is replaced with the arXiv ID.
journal_format = "arXiv preprint arXiv:{id}"
# Alternatives: "CoRR", or use eprint/archiveprefix fields instead
```
