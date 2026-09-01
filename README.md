# fetch-bib

[![CI](https://github.com/MilkClouds/fetch-bib/actions/workflows/ci.yml/badge.svg)](https://github.com/MilkClouds/fetch-bib/actions/workflows/ci.yml)
[![skills.sh](https://skills.sh/b/MilkClouds/fetch-bib)](https://skills.sh/MilkClouds/fetch-bib)

A universal agent skill for source-backed BibTeX.

fetch-bib uses [Paperstack](https://github.com/MilkClouds/paperstack) for paper discovery, external identifiers, metadata records, and its optional DBLP index. The skill keeps the editorial decisions that a metadata tool should not make: which version is citable, whether a work is formally published, which source is authoritative, and how an entry should be written into a bibliography.

It never invents missing metadata. Ambiguous works, conflicting venues, and workshop/main-track uncertainty are shown to the user instead of guessed.

## Recorded examples

**Published version resolution.** A naive lookup may return the 2023 arXiv preprint for StreamingLLM. fetch-bib resolves the ICLR 2024 publication:

<p align="center">
  <img src="docs/demos/demo-streamingllm.svg" alt="fetch-bib StreamingLLM publication-resolution demo" width="720">
</p>

**Bulk verification.** In this recorded test, 14 of 48 generated bibliography entries contained metadata errors: fabricated or incorrect author names, wrong venues, missing co-authors, incorrect pages, or preprints cited instead of formal publications.

<p align="center">
  <img src="docs/demos/demo-verify.svg" alt="fetch-bib bulk bibliography verification demo" width="720">
</p>

The complete bibliography fixtures are retained as [before](docs/demos/references-before.bib) and [after](docs/demos/references-after.bib) files.

## Install

Prerequisites:

- Python 3.11 or newer
- [uv](https://docs.astral.sh/uv/)
- Node.js and `npx` for skill installation

Install the Paperstack CLI:

```bash
uv tool install 'paperstack-cli>=0.3.2'
```

Install fetch-bib globally for detected agents:

```bash
npx skills add MilkClouds/fetch-bib --skill fetch-bib -g
```

Target particular agents when needed:

```bash
npx skills add MilkClouds/fetch-bib --skill fetch-bib -g -a codex -a claude-code
```

Omit `-g` for a project-local installation. Update later with:

```bash
npx skills update fetch-bib -g
```

The skill is stored once in `skills/fetch-bib` and follows the open [Agent Skills specification](https://agentskills.io/specification). It does not require the separate Paperstack agent skill or a configured Paperstack review corpus.

## Use

Ask your agent naturally:

```text
Get the BibTeX for arxiv:2106.09685.
Add doi:10.1109/CVPR.2016.90 to references.bib.
Verify every entry in references.bib.
Where was "Attention Is All You Need" published?
```

Supported identifiers include `arxiv:`, `doi:`, `dblp:`, and `openreview:`. Titles and common paper abbreviations are also accepted.

The core workflow is:

1. Resolve the work and collect stable identifiers with Paperstack.
2. Determine whether the citable version is a conference paper, workshop paper, journal article, or preprint.
3. Select one authoritative source for the complete entry.
4. Apply `bibstyle.toml`, add provenance, and check the result.
5. Return the entry or make the explicitly requested bibliography edit.

Every entry includes its actual source:

```bibtex
% source: dblp:conf/cvpr/HeZRS16 via paperstack/dblp (https://dblp.org/rec/conf/cvpr/HeZRS16.html)
@inproceedings{he2016deep,
  title     = {Deep Residual Learning for Image Recognition},
  author    = {He, Kaiming and Zhang, Xiangyu and Ren, Shaoqing and Sun, Jian},
  booktitle = {CVPR},
  year      = {2016},
}
```

Crossref and OpenReview are last-resort records and receive an `UNVERIFIED` warning.

## Configure

### BibTeX style

On first use in a project, fetch-bib asks whether to create the default `bibstyle.toml` or customize it:

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

### Semantic Scholar

Semantic Scholar is used for discovery, not as a citation source. Its API key is optional but improves reliability.

```bash
paperstack config status
paperstack config set semantic-scholar.api-key
```

`config set` prompts without echoing the secret and stores it in Paperstack's user credential store. fetch-bib never asks for the key in chat and never writes it to a project `.env`.

### DBLP

Paperstack owns the selected-venue DBLP index and its release lifecycle:

```bash
paperstack index dblp status
paperstack index dblp install
paperstack index dblp update
```

The index is optional. Without it, Paperstack can use online DBLP lookup. An index miss is not proof that a paper is unpublished because coverage is intentionally limited to selected CS venues.

## Source policy

**Tier 1 — Publisher / Anthology.** Prefer authoritative metadata from the official publisher or anthology: ACL Anthology, PMLR, ACM DL, IEEE Xplore, Springer, and arXiv for confirmed preprints only.

**Tier 2 — Curated databases.** Use DBLP for published CS papers when a Tier 1 export is unavailable. Use the corresponding official field-specific database for non-CS work.

**Tier 3 — Fallback.** Use Crossref or OpenReview only after exhausting Tier 1 and Tier 2, and mark the entry `UNVERIFIED`.

Paperstack exposes ACL Anthology, arXiv, DBLP, Crossref, and OpenReview records. For unsupported publishers such as PMLR, ACM, IEEE, or Springer, the skill may use the official publisher export directly. Each entry still uses one source; no source adapter is maintained in this repository.

## Existing Claude Code installations

The Claude marketplace manifest remains as a compatibility shim for existing users and points to the same universal skill. Existing marketplace installations continue to receive updates; there is no second Claude-specific copy to drift.

New installations should use `npx skills`. The old bundled DBLP downloader and fetch-bib DBLP releases are no longer used.

## Development

```bash
uvx --from git+https://github.com/agentskills/agentskills.git#subdirectory=skills-ref \
  skills-ref validate skills/fetch-bib
npx skills add . --list
```

## License

[MIT](LICENSE)
