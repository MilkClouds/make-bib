# make-bib: Generate clean BibTeX for a paper

$ARGUMENTS — `arxiv:ID`, `doi:ID`, `openreview:ID`, or title in quotes

## Steps

1. **Fetch**: `uv run paper_sources.py fetch --json <paper_id>`
   - For titles: `uv run paper_sources.py search s2 -t "<title>" --json` first, then fetch by best match.

2. **Resolve conflicts with `AskUserQuestion`** — never silently pick one side.
   - Venue ambiguity (workshop vs main conference, preprint vs published)
   - Conflicting venue names, titles, or years across sources
   - Provide 2–4 options with `label` + `description` showing the trade-off.

3. **Generate BibTeX** applying these conventions:

   **Venue precedence** (default): Journal > Conference > Workshop > arXiv

   **Entry type & fields**:
   - Conference → `@inproceedings{key, title, author, booktitle, year}` — no pages/editors/publishers/doi
   - Journal/arXiv → `@article{key, title, author, journal, year, volume, number}`
   - arXiv preprint: `journal={arXiv preprint arXiv:XXXX.XXXXX}`

   **Formatting**:
   - Abbreviate well-known venues (`NeurIPS`, `ICML`, etc.). If unsure, ask.
   - Protect proper nouns/acronyms in titles: `{BERT}`, `{ImageNet}`, `{B}ayesian` — don't over-brace.
   - Authors: `Last, First and Last, First`. Remove DBLP disambiguation numbers.
   - Key: `lastname2024`. Prefer ACL Anthology key if available.
   - Title source priority: DBLP > arXiv > CrossRef. Strip trailing periods.

   **Authoritative sources**: ACL Anthology BibTeX for ACL venues. OpenReview `_bibtex` is useful but verify.

4. Output ONLY the BibTeX entry.
