# make-bib: Generate accurate BibTeX for a paper

$ARGUMENTS — `arxiv:ID`, `doi:ID`, `openreview:ID`, or title in quotes

## Steps

1. **Fetch metadata** using `paper_sources.py`.
   - ID input: `uv run paper_sources.py fetch --json <paper_id>`
   - Title input: `uv run paper_sources.py search s2 -t "<title>" --json` to find the paper, then fetch.
   - Use `search` and `fetch` subcommands flexibly as needed.

2. **Read `bibstyle.toml`** from the project root for user preferences (fields, author limits, venue style, key format, arXiv conventions). If the file doesn't exist, ask the user about their preferences and create it.

3. **Generate BibTeX** from the aggregated data, following `bibstyle.toml` settings. When sources conflict or data is ambiguous, use `AskUserQuestion` (2–4 options with `label` + `description`) — never silently pick one side.

   **Defaults** (when `bibstyle.toml` doesn't specify):
   - Venue precedence: Journal > Conference > Workshop > arXiv
   - Abbreviate well-known venues. If unsure, ask.
   - Protect proper nouns/acronyms in titles: `{BERT}`, `{B}ayesian` — don't over-brace.
   - Authors: `Last, First and Last, First`. Remove DBLP disambiguation numbers.
   - Title source priority: DBLP > arXiv > CrossRef. Strip trailing periods.
   - ACL Anthology BibTeX is authoritative for ACL venues. OpenReview `_bibtex` is useful but verify.

4. Output ONLY the BibTeX entry.
