# Daily Tech Brief

Version **0.2.0** downloads and normalizes the RSS/Atom feeds defined in the source registry.
A failed source is recorded in the source report and does not stop the remaining sources.

## Python version

- Minimum: **Python 3.11**
- Recommended for local development and GitHub Actions: **Python 3.12**

## Included in v0.2.0

- Everything from v0.1.0
- RSS and Atom downloading through `requests`
- Explicit timeout, user agent, redirect handling, and HTTP error handling
- RSS 1.0, RSS 2.0, and Atom parsing with Python XML tools
- HTML cleanup for feed summaries
- Normalized article schema shared by RSS and Atom
- Per-source success, warning, and failure reports
- Atomic JSON output writing
- Source filtering from the command line
- Offline unit tests with bundled RSS and Atom fixtures

## Project structure

```text
daily-tech-brief-v0.2.0/
├── config/
│   ├── profile.yml
│   ├── settings.yml
│   └── sources.yml
├── output/
├── src/
│   ├── providers/
│   │   └── feed.py
│   ├── collector.py
│   ├── config_loader.py
│   ├── main.py
│   └── models.py
├── tests/
│   ├── fixtures/
│   │   ├── sample_atom.xml
│   │   └── sample_rss.xml
│   ├── test_collector.py
│   └── test_config.py
├── pyproject.toml
├── requirements.txt
└── README.md
```

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

On Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## Validate configuration only

```bash
python -m src.main --validate-only
```

JSON validation summary:

```bash
python -m src.main --validate-only --json
```

## Fetch all enabled feeds

```bash
python -m src.main
```

The collector writes:

```text
output/raw_articles.json
output/source_report.json
```

Fetch only one or more sources while debugging:

```bash
python -m src.main --source arch_linux_news
python -m src.main --source arch_linux_news --source planet_kde
```

Write outputs to another directory:

```bash
python -m src.main --output-dir output/debug
```

Machine-readable execution summary:

```bash
python -m src.main --json
```

## Run tests

```bash
python -m pytest -q
```

The tests do not access the internet. They use local RSS and Atom fixtures.

## Exit codes

- `0`: configuration is valid and at least one selected source succeeded
- `1`: all selected sources failed, or `fail_on_source_error` is enabled and any source failed
- `2`: invalid configuration or command-line source selection

By default, `fail_on_source_error` is `false`, so individual feed failures do not fail the complete run.

## Output schemas

### `raw_articles.json`

Each normalized article contains:

- source ID, name, category, priority, and tags
- title and canonical entry URL
- external feed ID
- publication and update times when available
- cleaned summary
- author when available
- fetch time

### `source_report.json`

Each source report contains:

- status: `success`, `warning`, or `failed`
- request duration
- HTTP status and final URL when available
- feed title
- article count
- parser warning or error information

## v0.2.0 acceptance criteria

- One failed source does not stop other sources.
- RSS and Atom entries use the same normalized schema.
- Network requests use an explicit timeout and user agent.
- HTML is removed from summaries.
- `raw_articles.json` and `source_report.json` are written atomically.
- Unit tests run without network access.

## Next version

**v0.3.0 — Filtering and Ranking**

- Filter by publication time.
- Normalize URLs.
- Remove duplicate articles.
- Add rule-based scores and score reasons.
- Apply category quotas.
