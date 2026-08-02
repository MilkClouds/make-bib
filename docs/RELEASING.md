# Releasing a refreshed DBLP snapshot

The DBLP database is **not** in the repo. Each fetch-bib Release contains `dblp-data.tar.gz`.
`ensure_data()` downloads it on first use. To publish a refreshed snapshot, never `tar` a hand-typed path: the local data lives under
`DATA_DIR`, which `_resolve_data_dir()` derives from `CLAUDE_PLUGIN_DATA` →
`XDG_DATA_HOME` → `~/.local/share`. If you guess the path, you can package a
directory `sync` never wrote to and ship stale data. The `pack` command archives
the resolved `DATA_DIR` for you, so use it.

Let `S=.claude/skills/fetch-bib/scripts/dblp_local.py`.

1. **Sync** the latest proceedings. `--force` re-fetches the given years and
   merges (never deletes):

   ```bash
   uv run $S sync --force -y 2025,2026
   ```

   On a bulk sync `dblp.org` may rate-limit (HTTP 503). Fall back to a mirror:

   ```bash
   DBLP_BASE=https://dblp.uni-trier.de uv run $S sync --force -y 2025,2026
   ```

2. **Pack** — archives the resolved `DATA_DIR` (the exact dir step 1 wrote to)
   and prints the entry count, size, and **sha256**:

   ```bash
   uv run $S pack --out /tmp/dblp-data.tar.gz
   ```

   `stats` prints the same `data dir:` line — confirm it is the directory you
   expect before packing.

3. **Publish** the release (dated tag `dblp-db-YYYY.MM`):

   ```bash
   gh release create dblp-db-YYYY.MM /tmp/dblp-data.tar.gz \
     --repo MilkClouds/fetch-bib \
     --title "DBLP BibTeX Database — YYYY.MM snapshot"
   ```

   To replace the asset on an existing tag: `gh release upload <tag>
   /tmp/dblp-data.tar.gz --clobber`.

4. **Point the code at it** in `scripts/dblp_local.py`:
   - `DATA_RELEASE_URL` → the new tag's `dblp-data.tar.gz`
   - `DATA_RELEASE_SHA256` → the sha256 from step 2

5. **Verify** a clean download matches the code, end to end:

   ```bash
   curl -fL "$DATA_RELEASE_URL" | sha256sum   # must equal DATA_RELEASE_SHA256
   ```

   Or run a search in a throwaway data dir to exercise `ensure_data`:

   ```bash
   env -u CLAUDE_PLUGIN_DATA XDG_DATA_HOME=/tmp/relcheck \
     uv run $S search "some paper title"
   ```

## Notes

- A year is marked `complete` once its fetch succeeds end to end, regardless of
  whether DBLP has finished importing that venue. For a venue DBLP is still
  ingesting (e.g. a just-closed conference), re-run `sync --force -y <year> -c
  <venue>` in a later snapshot to pick up the rest.
- DBLP's `publ/api` caps results at 100 per request; pagination walks the `f`
  offset in 100s and stops at the first empty page. `MAX_PAGES` bounds it.
