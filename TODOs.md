# TODOs

## Agent support

- Provide first-party citation workflows for both Claude Code and Codex from this repository.
- Use the `paperstack` CLI for paper discovery, source-backed metadata, local DBLP lookup, and paper content instead of duplicating those mechanisms in agent-specific scripts.
- Keep source selection, publication-status resolution, ambiguity handling, and bibliography edits human-reviewed in fetch-bib.
- Define installation and compatibility checks for the required `paperstack` version before removing superseded fetch-bib helpers.
- Test the same citation cases and safety gates on both agent implementations.
