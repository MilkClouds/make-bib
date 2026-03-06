# make-bib: Generate clean BibTeX for a paper

Given a paper identifier, fetch metadata from multiple sources and generate a clean BibTeX entry.

## Input

$ARGUMENTS — paper ID in `{type}:{value}` format (e.g. `arxiv:2010.11929`, `doi:10.18653/v1/N19-1423`, `openreview:1SIBN5Xyw7`) or title in quotes

## Steps

1. Run `uv run paper_sources.py fetch --json <paper_id>` and read the JSON output.
   - If the input looks like a title (not `type:value` format), first run `uv run paper_sources.py search s2 -t "<title>" --json` to find the paper, then fetch by the best matching ID.

2. Analyze the JSON output from all sources (S2, DBLP, CrossRef, OpenReview, ACL Anthology, arXiv). Each source may have different or missing data.

3. **When ambiguity exists, use the `AskUserQuestion` tool to let the user choose.**

   ### How to use `AskUserQuestion`
   - Provide 2–4 concrete options with `label` and `description`.
   - `label`: short choice text (e.g. "NeurIPS 2017"). `description`: why this option (e.g. "Conference version, @inproceedings").
   - Do NOT guess or silently pick one — always ask.

   ### When to ask
   - **Venue ambiguity**: workshop AND main conference both exist.
   - **Multiple published versions**: arXiv preprint vs. conference vs. journal.
   - **Conflicting venue names**: sources disagree on the venue.
   - **Unclear venue type**: can't tell if workshop or main conference.
   - **Title discrepancy**: sources have meaningfully different titles (not just capitalization).
   - **Year discrepancy**: arXiv year vs. publication year differ.

4. Generate a BibTeX entry following these rules:

### Venue Precedence (default, when user doesn't override)
1. Journal
2. Conference
3. Workshop / Symposium
4. arXiv / preprint

### Entry Type
- Conference → `@inproceedings`
  - Required fields: `title`, `author`, `booktitle`, `year`
  - Do NOT include: pages, editors, publishers, address, month, doi
- Journal / arXiv → `@article`
  - Required fields: `title`, `author`, `journal`, `year`, `volume`, `number`
  - For arXiv preprints: `journal={arXiv preprint arXiv:XXXX.XXXXX}`

### Venue Names
- Use standard abbreviations for well-known ML venues:
  - "Advances in Neural Information Processing Systems" → `NeurIPS`
  - "International Conference on Machine Learning" → `ICML`
  - "International Conference on Learning Representations" → `ICLR`
  - "IEEE/CVF Conference on Computer Vision and Pattern Recognition" → `CVPR`
  - etc.
- For less common venues, use the full name from the most authoritative source.
- **If unsure about the correct abbreviation, ask the user.**

### Title Capitalization
- Protect proper nouns and acronyms with braces so BibTeX doesn't lowercase them:
  - `{B}ayesian`, `{GPU}`, `{BERT}`, `{ImageNet}`, `{T}ransformer`
  - Only protect words that NEED it — don't over-brace.

### Author Format
- `Last, First and Last, First` format
- Use the author list from the most complete source (usually DBLP or ACL Anthology)
- DBLP sometimes includes disambiguation numbers (e.g., "Alexander Kolesnikov 0003") — remove these.

### BibTeX Key
- Default: first author's last name (lowercase) + year (e.g., `vaswani2017`)
- If ACL Anthology provides a key (e.g., `devlin-etal-2019-bert`), prefer that.

### Special Cases
- **ACL Anthology available**: Use its BibTeX directly — it's authoritative for ACL/EMNLP/NAACL venues. Only fix capitalization protection if needed.
- **OpenReview has `_bibtex`**: Consider using it, but verify venue name and field completeness.
- **Conflicting titles**: Prefer DBLP > arXiv > CrossRef. Remove trailing periods from DBLP titles.

5. Output ONLY the BibTeX entry. No explanation unless asked. But **always ask before making a choice when data is ambiguous** — don't silently pick one option.
