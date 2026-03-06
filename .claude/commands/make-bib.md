# make-bib: Generate clean BibTeX for a paper

Given a paper identifier (arXiv ID, DOI, or title), fetch metadata from multiple sources and generate a clean BibTeX entry.

## Input

$ARGUMENTS — paper ID (e.g. `2010.11929`, `10.18653/v1/N19-1423`) or title in quotes

## Steps

1. Run `uv run paper_sources.py fetch --json <paper_id>` and read the JSON output.
   - If the input looks like a title (not an ID), first run `uv run paper_sources.py search s2 -t "<title>" --json` to find the paper, then fetch by the best matching ID.

2. Analyze the JSON output from all sources (S2, DBLP, CrossRef, OpenReview, ACL Anthology, arXiv). Each source may have different or missing data — use your judgment to resolve conflicts.

3. Generate a BibTeX entry following these rules:

### Venue Precedence (highest priority first)
1. Journal
2. Conference
3. Workshop / Symposium
4. arXiv / preprint

If a paper appears in both arXiv and a conference (e.g., DBLP says CoRR but S2 says NeurIPS), **use the conference version**.

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

4. Output ONLY the BibTeX entry. No explanation unless there's an ambiguity that needs human decision (e.g., paper exists in both a workshop and a conference — ask which one to use).
