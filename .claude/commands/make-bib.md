# make-bib: Generate accurate BibTeX for a paper

$ARGUMENTS — `arxiv:ID`, `doi:ID`, `openreview:ID`, or title in quotes

## Steps

1. **Fetch metadata** using `paper_sources.py`.
   - ID input: `uv run paper_sources.py fetch --json <paper_id>`
   - Title input: `uv run paper_sources.py search s2 -t "<title>" --json` to find the paper, then fetch.
   - Use `search` and `fetch` subcommands flexibly as needed.

2. **Read `bibstyle.toml`** from the project root. If missing, ask the user about their preferences via `AskUserQuestion` and create it. See the schema below.

3. **Generate BibTeX** from the aggregated data, following `bibstyle.toml`. When sources conflict or data is ambiguous, use `AskUserQuestion` (2–4 options with `label` + `description`) — never silently pick one side.

   **Hard rules** (not configurable):
   - Venue precedence: Journal > Conference > Workshop > arXiv
   - Protect proper nouns/acronyms in titles: `{BERT}`, `{B}ayesian` — don't over-brace.
   - Authors: `Last, First and Last, First`. Remove DBLP disambiguation numbers.
   - Title source priority: DBLP > arXiv > CrossRef. Strip trailing periods.
   - ACL Anthology BibTeX is authoritative for ACL venues.

4. Output ONLY the BibTeX entry.

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
