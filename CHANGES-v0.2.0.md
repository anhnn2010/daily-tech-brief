# Changes in v0.2.0

## Added

- RSS 2.0, RSS 1.0, and Atom collector
- Shared normalized `Article` model
- Per-source `SourceReport`
- Request timeout and custom user agent
- Source-level failure isolation
- HTML cleanup and summary length limit
- Atomic `raw_articles.json` and `source_report.json` output
- `--source`, `--output-dir`, `--validate-only`, and `--json` CLI options
- Offline RSS and Atom fixtures
- Collector tests

## Changed

- Project version updated from 0.1.0 to 0.2.0
- `features.fetch_feeds` enabled
- Python minimum version documented as 3.11
- Python 3.12 recommended for local development and CI

## Not included yet

- Publication-time filtering
- URL normalization
- Duplicate removal
- Ranking
- Category quotas
- Markdown or HTML digest rendering
