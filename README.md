# make-bib

**All you need is the final look.**

A [Claude Code](https://docs.anthropic.com/en/docs/claude-code) skill that generates BibTeX from authoritative sources.

```
> /make-bib StreamingLLM

% source: dblp:conf/iclr/XiaoTCHL24 via dblp
@inproceedings{xiao2024streamingllm,
  author    = {Guangxuan Xiao and Yuandong Tian and Beidi Chen
               and Song Han and Mike Lewis},
  title     = {Efficient Streaming Language Models
               with Attention Sinks},
  booktitle = {ICLR},
  year      = {2024},
}
```

Google Scholar and Semantic Scholar would both give you arXiv 2023 for this paper. It's ICLR 2024.

## Two halves of citation

Citation work has a mechanical half and a judgment half.

**Mechanical** — which source to trust, how to fetch metadata, what fields to include, how to format them. These are rule-based and tedious. make-bib handles them entirely:

- Source selection per paper (ACL Anthology > PMLR > DBLP > CrossRef > arXiv)
- Metadata fetching from 6+ authoritative databases
- Entry type, key style, venue abbreviation, field filtering
- Local DBLP database for instant offline lookup (~40 conferences)

**Judgment** — which version to cite, conference vs journal vs preprint, workshop vs main track, what to do when sources disagree. These require human context that no tool can reliably provide. make-bib does not touch them:

- Never decides which version is "correct"
- Never auto-fixes entries
- Never renders a PASS/FAIL verdict
- Asks you when multiple candidates exist or venue is ambiguous

> The boundary is strict. Everything rule-based is automated. Everything that requires judgment is yours.

## Workflow

```
Input: paper ID, title, or abbreviation
         │
         ▼
    ┌─ Resolve ──────────────────────────────┐
    │  Semantic Scholar → external IDs        │
    │  (DOI, DBLP key, ACL ID, arXiv ID)     │
    └────────────────────────┬───────────────┘
                             │  automatic
         ┌─ Verify status ───┤
         │  DBLP / OpenReview / publisher page │
         │  → published or preprint?           │
         └───────────────────┬────────────────┘
                             │  automatic
         ┌─ Fetch BibTeX ────┤
         │  Tier 1: ACL Anthology, PMLR       │
         │  Tier 2: DBLP, CrossRef             │
         │  Tier 3: arXiv (preprint only)      │
         └───────────────────┬────────────────┘
                             │  automatic
         ┌─ Format ──────────┤
         │  Apply bibstyle.toml                │
         │  (key, venue, fields, authors)      │
         └───────────────────┬────────────────┘
                             │
                             ▼
                        You review.
```

When something is ambiguous — multiple candidates, unclear venue, workshop vs main track — make-bib stops and asks.

## Usage

```
> /make-bib arxiv:2106.09685
> /make-bib doi:10.1109/CVPR.2016.90
> /make-bib "Attention Is All You Need"
> /make-bib LoRA
```

## Configuration

Create `bibstyle.toml` in your project root:

```toml
[sources]
verify = ["s2", "dblp", "openreview"]
bibtex = ["acl_anthology", "pmlr", "dblp", "crossref", "arxiv"]

[fields]
conference = ["title", "author", "booktitle", "year"]
journal = ["title", "author", "journal", "year", "volume", "number"]

[venue]
style = "abbreviated"       # or "full"
proceedings_prefix = false   # true → "Proceedings of NeurIPS"

[key]
style = "lastname_year"     # "lastname_year", "lastname_venue_year", "acl"

[arxiv]
entry_type = "article"
journal_format = "arXiv preprint arXiv:{id}"
```

## Local DBLP database

Bundled local database covers ~40 CS conferences (2000–2026) for instant title-based lookup without hitting the DBLP API. Inspired by [rebiber](https://github.com/yuchenlin/rebiber).

```bash
uv run scripts/dblp_local.py sync                    # update all
uv run scripts/dblp_local.py sync -c neurips -y 2024  # specific venue/year
uv run scripts/dblp_local.py stats                    # show coverage
```

## Design rationale

No prominent researcher has published a guide on citation management — because it's a craft skill, not an algorithm. The universal pattern is: copy from an authoritative source, manually verify, apply conventions consistently. make-bib automates steps 1 and 3. Step 2 is yours.

## Related projects

- [**rebiber**](https://github.com/yuchenlin/rebiber) — Normalizes arXiv BibTeX with DBLP/ACL data. make-bib's local database is inspired by rebiber's approach.
- [**SimBiber**](https://github.com/MLNLP-World/SimBiber) — Simplifies BibTeX to minimal fields.
