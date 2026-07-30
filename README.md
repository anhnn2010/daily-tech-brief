# Daily Tech Brief

Daily Tech Brief is a personalized technology news pipeline for collecting, filtering, deduplicating, ranking, selecting, rendering, and automating technology digests from RSS and Atom feeds.

Version **0.5.0** adds GitHub Actions automation on top of the v0.4.0 Markdown and HTML rendering pipeline.

## Python version

- Minimum: **Python 3.11**
- Recommended for local development and GitHub Actions: **Python 3.12**

## Current pipeline

```text
RSS / Atom feeds
    ↓
Collector
    ↓
48-hour time filter
    ↓
URL normalization and deduplication
    ↓
Rule-based ranking
    ↓
Category quota selection
    ↓
ranked_articles.json
    ↓
digest.md
digest.html
    ↓
GitHub Actions artifact
```

## Included in v0.5.0

- Everything from v0.4.x
- GitHub Actions workflow
- Manual staging and production runs
- Daily production schedule
- GitHub Environments support
- Python 3.12 on `ubuntu-24.04`
- Configuration validation in CI
- Offline test execution in CI
- Digest generation in CI
- Artifact upload
- 14-day artifact retention
- Workflow regression tests

## Project structure

```text
daily-tech-brief/
├── .github/
│   └── workflows/
│       └── generate_digest.yml
├── config/
│   ├── profile.yml
│   ├── settings.yml
│   └── sources.yml
├── output/
├── src/
│   ├── filters/
│   │   ├── deduplicate.py
│   │   └── time_filter.py
│   ├── providers/
│   │   └── feed.py
│   ├── ranking/
│   │   ├── rule_based.py
│   │   └── selection.py
│   ├── renderers/
│   │   ├── html.py
│   │   └── markdown.py
│   ├── collector.py
│   ├── config_loader.py
│   ├── main.py
│   └── models.py
├── tests/
│   ├── fixtures/
│   │   ├── sample_atom.xml
│   │   └── sample_rss.xml
│   ├── test_article_selection.py
│   ├── test_collector.py
│   ├── test_config.py
│   ├── test_deduplicate.py
│   ├── test_github_workflow.py
│   ├── test_html_renderer.py
│   ├── test_main_pipeline.py
│   ├── test_markdown_renderer.py
│   ├── test_rendering_pipeline.py
│   ├── test_rule_based_ranking.py
│   └── test_time_filter.py
├── .gitignore
├── pyproject.toml
├── requirements.txt
└── README.md
```

## Local setup

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

## Validate configuration

```bash
python -m src.main --validate-only
```

Machine-readable validation summary:

```bash
python -m src.main --validate-only --json
```

## Run locally

Fetch and process all enabled sources:

```bash
python -m src.main
```

Run selected sources:

```bash
python -m src.main --source arch_linux_news
python -m src.main --source arch_linux_news --source planet_kde
```

Write outputs to another directory:

```bash
python -m src.main --output-dir output/debug
```

## Generated outputs

```text
output/
├── raw_articles.json
├── source_report.json
├── ranked_articles.json
├── digest.md
└── digest.html
```

### `raw_articles.json`

Contains all normalized feed entries returned by successful sources.

### `source_report.json`

Contains one report per requested source:

- status;
- request duration;
- HTTP status;
- retry count;
- request profile;
- article count;
- parser warning or error.

### `ranked_articles.json`

Contains:

- filtering summary;
- deduplication summary;
- ranking summary;
- category selection summary;
- rendering summary;
- selected articles;
- score reasons;
- matched keywords.

### `digest.md`

A portable Markdown edition grouped by category.

### `digest.html`

A standalone responsive HTML edition that can be opened locally or published later through GitHub Pages.

## Open the digest

Linux:

```bash
xdg-open output/digest.html
```

macOS:

```bash
open output/digest.html
```

Windows PowerShell:

```powershell
Start-Process output/digest.html
```

## GitHub Actions workflow

The workflow is stored at:

```text
.github/workflows/generate_digest.yml
```

It uses:

```text
Runner:  ubuntu-24.04
Python:  3.12
```

The workflow runs:

```text
Checkout
→ Set up Python
→ Install dependencies
→ Validate configuration
→ Run tests
→ Generate digest
→ Upload artifact
```

## Manual workflow runs

Open the repository on GitHub:

```text
Actions
→ Generate Daily Tech Brief
→ Run workflow
```

Choose one environment:

```text
staging
production
```

The default is:

```text
staging
```

Both environments currently run the same code and generate the same files. They are separated now so later versions can publish production output while staging remains artifact-only.

## Scheduled workflow

The workflow contains:

```yaml
schedule:
  - cron: "30 23 * * *"
```

This runs at approximately:

```text
06:30 Asia/Ho_Chi_Minh
```

Scheduled runs always use the `production` environment.

GitHub Actions schedules use UTC and may start a little later during periods of high GitHub Actions load.

## GitHub Environments

Create the following repository environments:

```text
Settings
→ Environments
```

Environment names:

```text
staging
production
```

No secrets are required in v0.5.0.

Later versions may store environment-specific values such as:

```text
AI_API_KEY
PUBLISH_TARGET
RELEASE_CHANNEL
```

## Workflow artifacts

A successful run uploads an artifact named like:

```text
daily-tech-brief-staging-12
daily-tech-brief-production-13
```

The artifact contains:

```text
raw_articles.json
source_report.json
ranked_articles.json
digest.md
digest.html
```

Artifact retention:

```text
14 days
```

### Download through the GitHub website

```text
Repository
→ Actions
→ Select a workflow run
→ Artifacts
→ Select the artifact
```

GitHub downloads the artifact as a ZIP file.

GitHub Mobile may show workflow runs and logs without exposing the artifact download clearly. On a phone, open the workflow run in a web browser to download the artifact.

## Staging and production behavior

### Staging

Use staging for:

- testing source changes;
- testing ranking changes;
- checking layout changes;
- checking workflow changes;
- reviewing artifact output.

Current behavior:

```text
Generate
→ Upload artifact
```

### Production

Production is used by scheduled runs and can also be selected manually.

Current behavior:

```text
Generate
→ Upload artifact
```

Future behavior:

```text
Generate
→ Upload artifact
→ Publish GitHub Pages
→ Create or update Release
```

Publishing is intentionally postponed until the workflow is stable.

## Workflow concurrency

Only one run per environment is kept active:

```text
staging
production
```

When a newer run starts for the same environment, the older active run is cancelled.

This avoids duplicate daily runs and unnecessary artifact generation.

## Run tests

```bash
python -m pytest -q
```

The current suite contains **89 offline tests**.

The GitHub workflow tests verify that the workflow retains:

- manual trigger;
- scheduled trigger;
- `ubuntu-24.04`;
- Python 3.12;
- staging and production;
- validation;
- test execution;
- digest generation;
- artifact upload.

## Exit codes

- `0`: configuration is valid and at least one requested source succeeded
- `1`: every requested source failed, or source errors are fatal
- `2`: invalid configuration, invalid source selection, or processing error

By default:

```yaml
fail_on_source_error: false
```

A failed source is recorded without stopping successful sources.

## v0.5.0 acceptance criteria

- Local configuration validation succeeds.
- All 89 tests pass.
- The workflow appears in the GitHub Actions tab.
- A manual staging run completes successfully.
- A manual production run completes successfully.
- The workflow uses Python 3.12 on `ubuntu-24.04`.
- The workflow creates all five output files.
- The artifact can be downloaded from the workflow run page.
- Scheduled runs resolve to the production environment.
- Staging and production use the same workflow and source code.
- No GitHub Pages or Release publishing occurs yet.

## Next version

**v0.6.0 — GitHub Pages Publishing**

Planned work:

- Prepare a static site directory.
- Publish `digest.html` as the latest edition.
- Keep dated HTML archives.
- Add a simple archive index.
- Publish only from production.
- Keep staging artifact-only.
- Add Pages deployment tests.
