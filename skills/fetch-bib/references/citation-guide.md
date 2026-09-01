# Academic Citation Infrastructure and BibTeX Best Practices

## 1. The DOI Ecosystem

### 1.1 What is a DOI?

A DOI (Digital Object Identifier) is a persistent identifier assigned to scholarly publications. Unlike URLs, which can change, a DOI permanently resolves to the current location of a resource. DOIs are standardized under ISO 26324.

### 1.2 Three-Layer Architecture

The DOI system consists of three layers.

**Top: International DOI Foundation (IDF)**
A nonprofit foundation that governs the DOI standard itself — its policies, specifications, and governance structure.

**Middle: Registration Agencies (RAs)**
Organizations that issue DOIs and register the associated metadata (title, authors, venue, etc.) and URLs. Multiple RAs exist for different domains:

| RA | Domain |
|---|---|
| CrossRef | Scholarly publications (largest RA) |
| DataCite | Datasets, software, research materials |
| mEDRA | European publications |
| EIDR | Film, TV, entertainment content |
| CNKI | Chinese scholarly content |

**Bottom: doi.org (Resolver)**
When a user enters `https://doi.org/10.1234/abcd` in a browser, this service determines which RA manages that DOI and redirects to the corresponding publisher page. Operated by IDF, it runs on CNRI's Handle System.

**Analogy:** IDF is like ICANN (governs the address system), RAs are like domain registrars (GoDaddy, etc.), and doi.org is like DNS (resolves names to destinations).


## 2. Major Bibliographic Databases

### 2.1 CrossRef

**What it is:** A nonprofit membership organization of publishers, universities, libraries, and government agencies worldwide.

**Role:** Issues DOIs for scholarly publications, stores metadata, and provides it via APIs. Covers all disciplines and geographies.

**How data enters:** Publishers directly deposit their own metadata. Crossref stores and distributes member-submitted metadata; per its own documentation, it does not generally curate or correct this data.

**Quality characteristics:** Metadata accuracy depends entirely on the submitting publisher. Large publishers (Elsevier, Springer) typically submit clean metadata, but smaller publishers and societies frequently have missing page numbers, inconsistent author name formatting, or incomplete dates. CrossRef does not enforce completeness beyond minimal requirements.

**BibTeX implications:** Useful for verifying whether a paper is formally published and confirming its DOI. However, BibTeX exported directly from CrossRef can be rough in formatting, especially for smaller venues.

### 2.2 DBLP

**What it is:** A curated bibliographic database specialized in computer science, started in 1993 by Michael Ley at the University of Trier, Germany. Originally an acronym for "Database systems and Logic Programming."

**Operated by:** Schloss Dagstuhl – Leibniz Center for Informatics (since 2018). Funded by the German federal and state governments, with additional grants from DFG (German Research Foundation).

**How data enters:**

- *Venue selection:* The DBLP Steering Committee defines minimum standards for indexing (CS focus, serious peer review, DOI registration, openly accessible metadata on the web).
- *Paper ingestion:* Once a venue is selected, individual papers are collected semi-automatically from publisher websites and metadata APIs. An editorial team then reviews for quality, correcting errors, filling in missing metadata, and disambiguating authors.

**Quality characteristics:** A small, dedicated editorial team curates CS publications exclusively. Author disambiguation, venue name normalization, and booktitle standardization are handled systematically.

**BibTeX implications:**
- Author names may include disambiguation numbers (e.g., `Wei Wang 0001`) — these must be removed before use.
- Both arXiv and formally published versions may be indexed; ensure you select the correct one.
- Page numbers or DOIs for very recent papers may not yet be reflected.
- Coverage is limited to CS.

### 2.3 Why DBLP Is Needed Despite CrossRef + doi.org

CrossRef stores individual records as deposited by publishers, without further curation. DBLP adds a curation layer on top:

| Function | CrossRef | DBLP |
|---|---|---|
| Author disambiguation | None | Manual separation and maintenance |
| Venue-level organization | Flat collection of records | Browsable by conference and year |
| Metadata normalization | As deposited by publisher | Standardized formatting |
| Researcher profiles | None | Complete publication lists per author |
| Coverage | All disciplines, worldwide | CS only |

### 2.4 Semantic Scholar

Operated by AI2 (Allen Institute for AI). Covers multiple disciplines beyond CS, including medicine and biology. Useful for discovering papers, but has a higher rate of metadata errors than DBLP due to heavy reliance on automated crawling. Common issues include non-standard venue abbreviations, arXiv preprints mislabeled as formally published, and missing page numbers or volume information. BibTeX obtained from Semantic Scholar should always be verified.

### 2.5 Google Scholar

A general-purpose academic search engine with the broadest coverage but the least reliable BibTeX metadata. Booktitles are frequently incorrect or inconsistent, and journal names may be wrong. Coverage is wide but metadata normalization is inconsistent, making it unsuitable as a primary BibTeX source.


## 3. Field-Specific Anthologies and Specialized Databases

Several academic communities maintain their own authoritative bibliographic systems. These often provide cleaner, more standardized BibTeX than general-purpose databases.

### 3.1 CS / NLP / ML

**ACL Anthology**
Operated by the Association for Computational Linguistics. Archives all papers from *CL conferences (ACL, EMNLP, NAACL, etc.) and associated workshops. Every paper page provides ready-to-use BibTeX. The primary source for citing NLP publications.

**PMLR (Proceedings of Machine Learning Research)**
Hosts proceedings for ICML, AISTATS, COLT, and other ML conferences. Functions more as a publishing platform than an anthology, but serves a similar role for BibTeX retrieval.

### 3.2 Physics

**INSPIRE-HEP**
The standard bibliographic system for high-energy physics, jointly operated by CERN, DESY, Fermilab, IHEP, IN2P3, and SLAC. Provides BibTeX directly; most physicists use INSPIRE-HEP citation keys and BibTeX as-is. Also offers a tool that generates a complete bibliography from a TeX file containing `\cite{}` commands.

### 3.3 Astronomy

**NASA ADS (Astrophysics Data System)**
The standard bibliographic system for astronomy, planetary science, and astrophysics. BibTeX generated by ADS is designed to be directly compatible with major astronomy journal LaTeX packages (AASTeX, MNRAS, A&A). Tools like `adstex` can automatically generate BibTeX files from citation keys in TeX source files.

### 3.4 Mathematics

**MathSciNet:** Operated by the AMS (American Mathematical Society). Subscription-based.
**zbMATH:** European-based mathematics bibliographic database.

### 3.5 Medicine / Life Sciences

**PubMed:** Operated by NLM (National Library of Medicine). Based on MEDLINE, with rigorous curation. The dominant bibliographic resource in medicine and life sciences.

### 3.6 Social Sciences

Commonly used databases include SSRN (preprints), JSTOR, Web of Science, and Scopus.


## 4. OpenReview

### 4.1 What It Is

OpenReview is a peer review platform used by major ML conferences including ICLR and NeurIPS. It is a review management system, not a publishing platform or bibliographic database.

### 4.2 What Is Reliable

The accept/reject status of papers is determined directly through the review process, making OpenReview the most authoritative source for confirming whether a paper was accepted at a given venue.

### 4.3 What Requires Caution

BibTeX entries on OpenReview are programmatically auto-generated and may have issues:

- Venue full names, page numbers, or DOIs may be missing or inaccurate.
- The BibTeX may reference the OpenReview URL rather than the formal proceedings publisher (e.g., Springer, PMLR).
- BibTeX entries may not be updated after formal proceedings are published.

### 4.4 Practical Use

OpenReview serves two roles:

- **Verification**: the most authoritative source for confirming acceptance status at venues that use the platform (ICLR, NeurIPS, COLM).
- **Fallback BibTeX**: for recent acceptances or workshop papers not yet indexed by higher-tier sources (DBLP, publisher pages), OpenReview BibTeX can be used as a starting point. Because it is auto-generated, entries obtained this way should be annotated as unverified and the venue name and fields checked manually.

When higher-tier sources are available (publisher page, DBLP), prefer those.


## 5. Citing Workshop Papers

Indicating that a cited paper is a workshop paper — rather than a main conference paper — is a strong norm in the CS community. Workshop papers and main conference papers differ in review rigor and academic standing; failing to distinguish them can mislead readers about the reliability of a source.

**Recommended practice:**

- Specify the workshop name in `booktitle`: e.g., `Workshop on Efficient Natural Language and Speech Processing (ENLSP) at NeurIPS 2024`
- At minimum, include the word "Workshop": e.g., `NeurIPS 2024 Workshop`

Omitting the workshop designation and listing only the main conference name can be perceived as misrepresentation.


## 6. Verifying Acceptance Status

Confirming which venue a paper was accepted at is a separate concern from obtaining correct BibTeX. The two tasks have different optimal sources. In practice, verification follows a quick-to-thorough progression:

### Step 1: Quick Lookup via Aggregators

Start with Semantic Scholar or Google Scholar. These platforms often display venue information on the paper's page, and checking takes seconds. This is sufficient for a rough initial assessment, but metadata errors are common — venue names may be wrong, missing, or point to arXiv rather than the actual proceedings. Treat this as a preliminary signal, not confirmation.

### Step 2: Confirm via Authoritative Sources

If the venue information from Step 1 looks plausible but needs confirmation, or if no venue is shown, check the following depending on the conference:

| Source | Scope | Notes |
|---|---|---|
| OpenReview | ICLR, NeurIPS, COLM, and other venues using the platform | For conferences that use OpenReview as their official review system, accept/reject decisions are recorded directly in the review process, making it the most direct source for acceptance status. |
| Conference website | Any conference | Official accepted paper lists posted by program chairs. Authoritative but sometimes taken down after the event. |
| DBLP | CS | If a paper appears under a venue's proceedings/journal issue in DBLP, it is generally safe to treat it as an official publication record for that venue. Reliable but may lag behind by weeks or months after the conference. |
| ACL Anthology / PMLR | NLP / ML | Presence in these archives confirms acceptance. |

### Step 3: Fallback Indicators

If the above sources are inconclusive (e.g., a very recent paper not yet indexed anywhere), the following can provide indirect evidence:

| Source | Notes |
|---|---|
| CrossRef / DOI | A DOI issued by the proceedings publisher confirms formal publication, but does not distinguish main track from workshop. |
| The paper's own PDF | Authors sometimes add venue information to the header or footnote of camera-ready versions. Useful as a hint, not as definitive proof. |


## 7. BibTeX Source Priority

### 7.1 Tier 1: Publisher / Anthology

Authoritative metadata direct from the publisher. The most accurate BibTeX sources.

| Source | Scope |
|---|---|
| ACL Anthology | *CL conferences (ACL, EMNLP, NAACL, etc.) and NLP workshops |
| PMLR | ICML, AISTATS, COLT, and other ML conference proceedings |
| arXiv | Preprints — when no formal venue is confirmed. arXiv is the publisher for preprints |
| ACM Digital Library | ACM-published conferences (KDD, CHI, SIGIR, etc.) |
| IEEE Xplore | IEEE-published conferences (CVPR, ICCV, etc.) |
| Springer Link | Springer-published conferences (ECCV, ECML, etc.) |
| Other publishers | Any venue with official proceedings page |

### 7.2 Tier 2: Curated Databases

Normalized, reliable metadata. Use when Tier 1 sources are inconvenient or for bulk processing.

| Source | Scope |
|---|---|
| DBLP | CS — the most reliable Tier 2 source. BibTeX is usable as-is in most cases. Always check for disambiguation number suffixes in author names |
| INSPIRE-HEP | High-energy physics |
| NASA ADS | Astronomy, planetary science |
| PubMed | Medicine, life sciences |
| MathSciNet / zbMATH | Mathematics |

### 7.3 Tier 3: Fallback

Constructed from API data. BibTeX obtained from these sources requires verification and should be annotated as unverified.

| Source | Characteristics |
|---|---|
| CrossRef | DOI exists but no higher-tier source available. Metadata completeness depends on what publishers deposit — large publishers typically submit clean records, but smaller ones may have gaps (missing pages, incomplete dates) |
| OpenReview | Recent acceptances or workshop papers not yet in Tier 1–2. Auto-generated BibTeX — verify venue name and fields (see Section 4) |

Discovery platforms (Semantic Scholar, Google Scholar) are not BibTeX sources — they are useful for finding papers but their metadata is unreliable and should never be used directly in BibTeX entries.

### 7.4 Unpublished Papers

For papers not yet formally published, use arXiv metadata (Tier 1 for preprints) with `journal={arXiv preprint arXiv:XXXX.XXXXX}`. Do not present unpublished papers as conference publications.

### 7.5 DOI Does Not Guarantee Complete Metadata

A DOI confirms formal publication, but not metadata completeness. Crossref defines required, recommended, and optional fields per record type — page numbers, funding info, ORCID, and event metadata may all be absent even when a valid DOI exists. Always verify key fields regardless of DOI presence.


## 8. Practical Workflow

Publication status verification and BibTeX retrieval are separate tasks with different optimal sources. The workflow below addresses both in sequence.

### 8.1 Process

1. Determine whether the paper has a formal publication. Check the field's authoritative source first (e.g., ACL Anthology for NLP, PMLR for ML, ACM DL for ACM venues). For conferences using OpenReview (ICLR, NeurIPS, COLM), check acceptance status there. Fall back to DBLP, then CrossRef/DOI.
2. If formally published: obtain BibTeX from the publisher page or field-specific anthology (Tier 1).
3. If Tier 1 is impractical: use DBLP (CS) or CrossRef (other fields) as a metadata fallback.
4. If unpublished: use arXiv BibTeX and explicitly mark it as a preprint.
5. Run a final manual review before submission (see checklist below).

### 8.2 Pre-Submission Checklist

Regardless of where BibTeX was obtained, verify the following before submitting. Note that correct metadata and correct citation style are separate concerns — even accurate metadata may need formatting adjustments (title capitalization, proceedings title abbreviation, BibTeX key naming) to match the target venue's style requirements.

- No DBLP disambiguation numbers remain in author names
- Venue names are correct (workshop papers marked as workshops)
- Publication year is accurate
- Page numbers, volume, and DOI are present where applicable
- No arXiv-cited papers have since been formally published
- Title capitalization and proceedings name formatting match target venue style

### 8.3 Automation: Rebiber

Rebiber (`github.com/yuchenlin/rebiber`) normalizes BibTeX entries using DBLP and ACL Anthology data. It is actively used in the NLP/ML community as a pre-submission sanity check (3,000+ GitHub stars). Its primary function is updating arXiv preprint citations to their formal publication information.

Limitations: supports a fixed set of conferences, depends on periodic DBLP snapshots (latest conferences may not be immediately available), and does not eliminate the need for manual review.