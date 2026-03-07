# make-bib: All you need is the final look

A [Claude Code skill](https://code.claude.com/docs/en/skills) that generates BibTeX from authoritative sources.

**It does:** Fetches BibTeX from the publisher first (ACL Anthology, PMLR, arXiv), falls back to curated databases (DBLP), formats the entry, and always shows exactly where each entry came from. The mechanical half of citation, handled.

**It does not:**
- **Guess.** The first rule is **When in doubt, ask.** Multiple candidates, ambiguous venue, workshop vs main track — it stops and asks you.
- **Generate.** Every field comes from an [authoritative source](#sources) — not from an LLM filling in blanks.


**Demo.**

```
> /make-bib StreamingLLM

% source: dblp:conf/iclr/XiaoTCHL24 via dblp (https://dblp.org/rec/conf/iclr/XiaoTCHL24.bib)
@inproceedings{xiao2024efficient,
  author    = {Guangxuan Xiao and Yuandong Tian and Beidi Chen
               and Song Han and Mike Lewis},
  title     = {Efficient Streaming Language Models
               with Attention Sinks},
  booktitle = {{ICLR}},
  year      = {2024},
}
```

Google Scholar would give you arXiv 2023 for this paper. It's ICLR 2024.

When something is ambiguous, it stops and asks — then goes deep to find the right source:

```
> /make-bib Scaling Laws

? Which "Scaling Laws" paper do you mean?
  1. Kaplan et al. 2020 — Scaling Laws for Neural Language Models (arXiv:2001.08361)
  2. Hoffmann et al. 2022 — Training Compute-Optimal Large Language Models (Chinchilla, arXiv:2203.15556)
  3. Henighan et al. 2020 — Scaling Laws for Autoregressive Generative Modeling (arXiv:2010.14701)

> 2

  Step 1: arxiv:2203.15556, DOI 10.52202/068431-2176
  Step 2: S2 says NeurIPS 2022. DBLP search by title — miss (different title).
          DBLP search by DOI — miss. Trying NeurIPS proceedings directly...
          Found. Published title: "An empirical analysis of compute-optimal
          large language model training"
  Step 3: Tier 1 — fetching BibTeX from proceedings.neurips.cc

% source: neurips:NEURIPS2022_c1e2faff via neurips (https://proceedings.neurips.cc/paper_files/paper/19447-/bibtex)
@inproceedings{hoffmann2022training,
  title     = {An empirical analysis of compute-optimal
               large language model training},
  author    = {Hoffmann, Jordan and Borgeaud, Sebastian
               and Mensch, Arthur and ...},
  booktitle = {NeurIPS},
  year      = {2022},
}
```

DBLP indexes this paper under its arXiv title ("Training Compute-Optimal Large Language Models"), but NeurIPS published it under a **different title** ("An empirical analysis of compute-optimal large language model training"). Opus 4.6 with make-bib exhausts DBLP lookups, falls through to the NeurIPS proceedings page, and uses the published title.

## Why this exists (and its limitations)

LLMs hallucinate citations. This is not hypothetical — it is happening at scale in published research:

- **NeurIPS 2025**: [100+ hallucinated citations found across 53 accepted papers](https://fortune.com/2026/01/21/neurips-ai-conferences-research-papers-hallucinations/) that passed 3+ peer reviewers. Fabricated authors, fake venues, dead URLs.
- **ACL/EMNLP 2025**: [~300 papers with hallucinated references](https://arxiv.org/abs/2601.18724), with EMNLP 2025 alone accounting for 154. The number jumped sharply from 20 in 2024 to 275 in 2025.
- **arXiv trend**: [Analysis of 2.2M citations](https://spylab.ai/blog/hallucinations/) shows hallucinated references accelerating from early 2025, with LLMs blending real papers into chimeric non-existent entries.

The root cause: LLMs generate plausible-looking citations from statistical patterns, not from actual sources. make-bib avoids this by never generating metadata — every field comes from a publisher, curated database, or API response, with the source URL attached.

That said, make-bib is still an LLM skill. It can pick the wrong source, misformat fields, or fail under edge cases. Always review the output before citing. Designed for and tested with Claude Opus 4.6 — correct behavior with lower-tier models is not guaranteed.

## Sources

**Tier 1 — Publisher / Anthology** (authoritative metadata direct from publisher):

| Source | Scope |
|---|---|
| ACL Anthology | ACL, EMNLP, NAACL, and NLP workshops |
| PMLR | ICML, AISTATS, COLT, UAI, CoRL, ALT |
| arXiv | Preprints (when no formal venue is confirmed) |
| Other publishers | NeurIPS proceedings, ACM DL, IEEE Xplore, Springer, etc. |

**Tier 2 — Curated DB** (normalized, reliable):

| Source | Scope |
|---|---|
| DBLP | ~40 CS conferences via local database (includes IEEE, ACM venues) |
| Others by field | INSPIRE-HEP (physics), ADS (astronomy), PubMed (medicine) |

**Tier 3 — Fallback** (requires `⚠ UNVERIFIED` annotation):

| Source | Scope |
|---|---|
| CrossRef | Any paper with a DOI, when higher tiers unavailable |
| OpenReview | Recent acceptances or workshops not yet in Tier 1–2 |

Entries from Tier 3 sources are labeled `⚠ UNVERIFIED` in the output. If you see this marker, verify the venue name, author list, and year yourself before using the entry.

## Workflow

```
Input: paper ID, title, or abbreviation
         │
         ▼
    ┌─ bibstyle.toml ───────────────────────┐
    │  Found → apply. Not found → ask you   │
    │  (defaults or customize), create file │
    └────────────────────────┬──────────────┘
                             │
    ┌─ Resolve ──────────────┤               ambiguous?
    │  Semantic Scholar → external IDs    ──────→ asks you
    │  (DOI, DBLP key, ACL ID, arXiv ID)     (multiple candidates,
    └────────────────────────┬──────────────┘  workshop vs main,
                             │                 venue unclear)
    ┌─ Verify status ────────┤
    │  DBLP (title/key/DOI) / OpenReview /  │
    │  publisher page → published or preprint│
    └────────────────────────┬──────────────┘
                             │
    ┌─ Fetch BibTeX ─────────┤
    │  Tier 1 → 2 → 3, exhaust each tier   │
    │  before falling back                  │
    └────────────────────────┬──────────────┘
                             │
    ┌─ Validate & format ────┤
    │  Apply bibstyle.toml, run checklist   │
    │  (type, venue, fields, key, source)   │
    └────────────────────────┬──────────────┘
                             │
                             ▼
                        You review.
```

## Prerequisites

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) — Anthropic's CLI for Claude. This skill runs inside Claude Code, not as a standalone tool.
- Python 3.10+ and [uv](https://docs.astral.sh/uv/) (for the bundled DBLP local database scripts)

## Installation

This repo is a [Claude Code skill](https://code.claude.com/docs/en/skills) — a set of instructions and scripts that Claude Code loads when you type `/make-bib`.

```bash
npx skills add MilkClouds/make-bib -a claude-code
```

Or manually: clone this repo into `.claude/skills/make-bib` (project-level) or `~/.claude/skills/make-bib` (global).

After installation, open Claude Code and type `/make-bib` — it will be recognized automatically.

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

## Related projects

- [**rebiber**](https://github.com/yuchenlin/rebiber) — Normalizes arXiv BibTeX with DBLP/ACL data. make-bib's local database is inspired by rebiber's approach.
- [**SimBiber**](https://github.com/MLNLP-World/SimBiber) — Simplifies BibTeX to minimal fields.
- [**bibtex-dblp**](https://github.com/volkm/bibtex-dblp) — Python tool to retrieve BibTeX entries from DBLP.
- [**Generating BibTeX from DOIs via DBLP**](https://www.joachim-breitner.de/blog/806-Generating_bibtex_bibliographies_from_DOIs_via_DBLP) — Blog post on using DBLP as a DOI-to-BibTeX resolver.
