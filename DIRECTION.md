# bibtools: Direction Change Proposal

## Problem Statement

Citation management in ML/DL research is fundamentally a **human judgment task**, not an algorithmic one. No fixed algorithm can determine the "correct" BibTeX entry — researchers apply rules of thumb and common sense.

Current bibtools tries to **automate the judgment** (PASS/FAIL/WARNING), but this creates false confidence: a PASS doesn't mean the entry is actually correct, and a FAIL doesn't always mean it's wrong.

## Evidence: How Researchers Actually Cite

### The Silence of Top Researchers

**No prominent DL researcher (Hinton, LeCun, He, Karpathy, etc.) has published a guide on citation management.** Perplexity and web search confirm: there are no blog posts, interviews, or lab guides from Google DeepMind, OpenAI, Meta FAIR, or BAIR about BibTeX workflows. This silence itself is evidence — citation formatting is considered a craft skill learned by osmosis, not a problem worth formalizing.

The closest we find are:
- **Yann LeCun's publication page** ([yann.lecun.com/exdb/publis](https://yann.lecun.com/exdb/publis/index.html)): Maintains a downloadable BibTeX file but no guidance on how to cite properly.
- **Kaiming He's page** ([people.csail.mit.edu/kaiming](https://people.csail.mit.edu/kaiming/)): Lists publications with venue names (CVPR, ICCV, ECCV, etc.) but no citation advice.

### What CS Professors Actually Teach

The real guidance comes from **writing advice pages by CS faculty** — not ML-specific, but these are the norms ML researchers absorb:

**Jennifer Widom (Stanford)**
> "Spend the effort to make all citations complete and consistent. Do *not* just copy random inconsistent BibTex (or other) entries from the web and call it a day. Check over your final bibliography carefully and make sure every entry looks right."
>
> — [Tips for Writing Technical Papers](https://cs.stanford.edu/people/widom/paper-writing.html)

**Jonathan Aldrich (CMU)**
> References must be **correct, complete, and consistent**.
> - Correct: none of the information is wrong
> - Complete: minimum necessary information (conferences: author, title, conference, year; journals: + volume, number, pages)
> - Consistent: every reference of the same type has the same information in the same form
>
> "Prefer citing the journal version of something over the conference version unless you have a good reason."
>
> — [How to Format References Properly](https://www.cs.cmu.edu/~aldrich/advice/reference-formatting.txt)

**Adam Chlipala (MIT)**
> "Many common BibTeX styles will lowercase all words of paper titles unless you override the behavior, by putting relevant words inside curly braces. Check the rendered entries for your bibliographic references and be sure capitalization is correct everywhere."
>
> "**Always choose the proceedings** [over SIGPLAN Notices]! It just conveys so much more useful information to be clear about which conference a paper appeared in."
>
> — [Paper-Writing Advice](http://adam.chlipala.net/writing.html)

**CMU Computational Imaging Lab** ([github.com/cmu-ci-lab/writing](https://github.com/cmu-ci-lab/writing))
> Detailed writing guide covering capitalization, consistent terminology, and reference formatting norms. Notes directly inspired by Wojciech Jarosz's (Dartmouth) common mistakes guide.

### Lab-Level Practices (Concrete Evidence)

Some labs maintain **shared BibTeX repositories** with explicit conventions:

**Tamaki Lab (Japan)** ([github.com/tamaki-lab/lab-bibtex](https://github.com/tamaki-lab/lab-bibtex)):
- Shared `.bib` repo with per-venue sourcing rules
- Key format: `{author}_{venue}{year}_{keyword}` (e.g., `he_CVPR2016_resnet`)
- Explicit instructions per venue: "For arXiv, do NOT use 'Export BibTeX Citation' — go to DBLP instead"
- "For CVPR/ICCV/WACV: use CVF Open Access bibtex link"
- "For IEEE papers: use IEEE Xplore 'cite this'"
- "For Springer (IJCV, ECCV): use DBLP or import via Mendeley"

**IAI Group (University of Stavanger)** ([github.com/iai-group/guidelines](https://github.com/iai-group/guidelines/blob/main/writing/BibTeX.md)):
- Detailed per-type formatting rules
- Conference: `@inproceedings` with author, title, booktitle (`ACR 'YY` format), pages, year
- Journal: `@article` with full journal name (or ISO 4 abbreviation), volume, number, pages
- "Always use natbib!"

**NTHU AIINS Lab (Taiwan)** ([aiins.cs.nthu.edu.tw/orientations](https://aiins.cs.nthu.edu.tw/orientations-old/)):
- Orientation materials include bib writing tutorial
- "verify the information via Google Scholar or the conference page"
- Key format: first letter of each author's last name + year

**Vector Institute** maintains a centralized BibTeX repository with a `flatten.sh` script compiling individual `.bib` files into `all.bib`.

### The Emerging Pattern

Across all sources, the pattern is:

1. **Copy from an authoritative source** (DBLP, publisher site, conference proceedings — NOT Google Scholar blindly)
2. **Manually verify and clean** (capitalization, venue name, field completeness)
3. **Apply conventions consistently** (same fields for same entry types, same abbreviation style)
4. **Use human judgment** for edge cases (venue precedence, which version to cite)

No one automates step 4. Steps 1-3 are partially automatable but **no existing tool covers all three well**.

### Venue Style Guides

- **NeurIPS/ICLR**: "any style is acceptable as long as it is used consistently"
- **ICML 2024**: "please put some effort into making references complete, presentable, and consistent. Please protect capital letters of names and abbreviations in titles."
- **JMLR**: Most prescriptive — requires correct citation syntax (`\citet` vs `\citep`), published versions over preprints, consistent author name format

### Universal Rules of Thumb

These conventions are consistent across all sources surveyed:

1. **Venue precedence**: Journal > Conference > Workshop > arXiv/preprint
2. **Entry types**: `@inproceedings` for conferences, `@article` for journals/arXiv
3. **Minimal fields for conferences**: title, author, booktitle, year
4. **Additional fields for journals**: + volume, number, pages
5. **Title capitalization**: Protect proper nouns/acronyms with braces (`{B}ayesian`, `{GPU}`)
6. **Venue abbreviation**: Use short forms for well-known venues (`NeurIPS`, not the full name)
7. **Source hierarchy**: Publisher site / proceedings > DBLP > arXiv export > Google Scholar
8. **Consistency**: Every reference of the same type must look the same

### Existing Tools and Their Gaps

| Tool | What it does | Gap |
|------|-------------|-----|
| **rebiber** (2.8k stars) | arXiv → published version via DBLP/ACL | Limited venue coverage, over-normalizes capitalization |
| **SimBiber** | Strips to minimal fields | No accuracy guarantee |
| **bibtools** (current) | Fetches + judges PASS/FAIL | Judgment is unreliable; false confidence |
| **RefChecker** | Validates references exist | Doesn't help with formatting/correctness |
| **Zotero + Better BibTeX** | Reference manager with auto-sync | Good for collection, weak on ML-specific conventions |

**Gap**: No tool simply **aggregates data from multiple authoritative sources and presents it for human decision**. The judgment step is always left to humans in practice — tools should support that, not replace it.

## Proposed Direction

### Core Principle

> **The tool fetches and presents. It never judges.**

bibtools should be a **data aggregation and presentation layer** — the "competent grad student who gathers all the information and lays it out for the professor to decide."

### New Role

```
BEFORE:  fetch → compare → judge (PASS/FAIL) → output verdict
AFTER:   fetch → aggregate → present (structured data) → human/AI decides
```

### What the Tool Does

For a given paper (by ID, title, or existing BibTeX entry):

1. **Fetch from all available sources** — CrossRef, DBLP, arXiv, Semantic Scholar
2. **Normalize and structure** — Parse into consistent fields
3. **Present side-by-side** — Show what each source says, highlighting differences
4. **Apply mechanical rules only** — Things that are objectively correct:
   - `@inproceedings` vs `@article` based on venue type
   - Strip unnecessary fields (pages, editors, publishers, etc.)
   - Venue abbreviation (from known alias table)
   - Title capitalization protection for known proper nouns

### What the Tool Does NOT Do

- Decide which source is "correct"
- Judge PASS/FAIL/WARNING
- Auto-fix entries without human confirmation
- Claim an entry is "verified"

### Target Workflows

**Workflow 1: Single paper fetch**
```bash
bibtools fetch 2106.09685
# Shows: CrossRef says X, DBLP says Y, arXiv says Z
# Outputs: suggested BibTeX (from best available source by venue precedence)
```

**Workflow 2: Bulk review (.bib file)**
```bash
bibtools review main.bib
# For each entry: shows source comparison
# Human picks what to keep/change
```

**Workflow 3: AI agent integration**
```
bibtools fetch --json 2106.09685 | ai-agent --rules rules.yaml
# Tool outputs structured data
# AI agent applies rules of thumb + common sense
# Human reviews AI's decisions
```

### Architecture Impact

| Module | Keep | Remove | Change |
|--------|------|--------|--------|
| fetcher.py (CrossRef/DBLP/arXiv clients) | ✓ | | |
| semantic_scholar.py (S2 client) | ✓ | | |
| parser.py (BibTeX parsing) | ✓ | | |
| rate_limiter.py | ✓ | | |
| models.py | | | Simplify: remove VerificationStatus, FieldMismatch |
| verifier.py | | ✓ | Replace with presentation logic |
| utils.py (comparison functions) | | Mostly | Keep formatting utils only |
| venue_aliases.py | ✓ | | Used for abbreviation, not judgment |
| fixer.py | | | Simplify |
| cli.py | | | Redesign commands |

## Open Questions

1. **Output format**: Table? JSON? Markdown? Interactive TUI?
2. **AI agent interface**: JSON output for piping? MCP server? Python API?
3. **Scope of "mechanical rules"**: Where is the line between "objectively correct normalization" and "judgment"?
4. **Migration**: Deprecate current verify/review commands or keep them as legacy?
