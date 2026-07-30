# Daily Tech Brief

Daily Tech Brief is a personalized technology news pipeline for collecting, filtering, deduplicating, ranking, selecting, rendering, publishing, and automating technology digests from RSS and Atom feeds.

Version **0.6.0** adds static-site generation and GitHub Pages deployment on top of the v0.5.0 GitHub Actions workflow.

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
Static site builder
    ↓
site/
    ↓
GitHub Actions artifact
GitHub Pages
```

## Included in v0.6.0

- Everything from v0.5.x
- Static-site generation
- Latest digest page
- Dated archive pages
- Archive index in HTML and JSON
- Site metadata
- `.nojekyll`
- Production archive restoration
- Separate site artifact
- Production-only GitHub Pages deployment
- Staging remains artifact-only
- GitHub Pages workflow tests
- End-to-end site publishing integration tests

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
├── site/
├── src/
│   ├── filters/
│   │   ├── deduplicate.py
│   │   └── time_filter.py
│   ├── providers/
│   │   └── feed.py
│   ├── publishing/
│   │   └── site_builder.py
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
│   ├── test_site_builder.py
│   ├── test_site_pipeline.py
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

Fetch, process, render, and build the static site:

```bash
python -m src.main
```

Run selected sources:

```bash
python -m src.main --source arch_linux_news
python -m src.main --source arch_linux_news --source planet_kde
```

Write generated data to another output directory:

```bash
python -m src.main --output-dir output/debug
```

## Generated data output

```text
output/
├── raw_articles.json
├── source_report.json
├── ranked_articles.json
├── digest.md
└── digest.html
```

### `raw_articles.json`

Contains all normalized entries returned by successful feed sources.

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

A standalone responsive HTML edition.

## Static site output

The site builder creates:

```text
site/
├── index.html
├── digest.md
├── ranked_articles.json
├── source_report.json
├── site.json
├── .nojekyll
│
├── latest/
│   ├── index.html
│   ├── digest.md
│   ├── ranked_articles.json
│   └── source_report.json
│
└── archive/
    ├── index.html
    ├── index.json
    └── YYYY/
        └── MM/
            └── DD/
                ├── index.html
                ├── digest.md
                ├── ranked_articles.json
                └── source_report.json
```

The local archive date is calculated using:

```text
Asia/Ho_Chi_Minh
```

## Static site URLs

After GitHub Pages deployment, the site provides:

```text
/                         Latest edition
/latest/                  Latest edition
/archive/                 Archive index
/archive/YYYY/MM/DD/      Dated edition
/digest.md                Latest Markdown edition
/ranked_articles.json     Latest ranked JSON
/source_report.json       Latest source report
/site.json                Site metadata
```

## Open the site locally

Linux:

```bash
xdg-open site/index.html
```

Open the archive:

```bash
xdg-open site/archive/index.html
```

Inspect the archive manifest:

```bash
python -m json.tool site/archive/index.json
```

## Static-site configuration

Static-site generation is controlled in:

```text
config/settings.yml
```

Current configuration:

```yaml
runtime:
  output_dir: output
  site_dir: site

features:
  ranking: true
  render_markdown: true
  render_html: true
  build_site: true
```

Generated directories are ignored by Git:

```gitignore
output/
site/
```

## GitHub Actions workflow

The workflow is stored at:

```text
.github/workflows/generate_digest.yml
```

Runtime:

```text
Runner: ubuntu-24.04
Python: 3.12
Branch: master
```

The workflow runs:

```text
Checkout
→ Set up Python
→ Install dependencies
→ Validate configuration
→ Run tests
→ Restore production archive when available
→ Generate digest and static site
→ Upload data artifact
→ Upload site artifact
→ Deploy GitHub Pages for production
```

## Manual workflow runs

Open the repository on GitHub:

```text
Actions
→ Generate Daily Tech Brief
→ Run workflow
```

Choose:

```text
staging
production
```

The default is:

```text
staging
```

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

Scheduled runs always resolve to:

```text
production
```

GitHub Actions schedules use UTC and may start slightly later during periods of high load.

## Staging behavior

Staging performs:

```text
Generate digest
→ Build site
→ Upload output artifact
→ Upload site artifact
```

Staging does **not**:

- upload a GitHub Pages artifact;
- deploy GitHub Pages;
- replace the public website.

Use staging for checking:

- sources;
- ranking;
- layout;
- archive structure;
- workflow changes.

## Production behavior

Production performs:

```text
Restore previous production site artifact
→ Generate current digest
→ Merge current edition into archive
→ Upload output artifact
→ Upload site artifact
→ Upload Pages artifact
→ Deploy GitHub Pages
```

The production workflow restores the most recent unexpired site artifact named like:

```text
daily-tech-brief-site-production-<run-number>-<run-attempt>
```

This preserves dated archive editions between workflow runs.

If no previous production artifact exists, the workflow starts a new archive.

## Workflow artifacts

Each workflow run uploads two regular artifacts.

### Data artifact

Example:

```text
daily-tech-brief-staging-12-1
daily-tech-brief-production-13-1
```

Contains:

```text
raw_articles.json
source_report.json
ranked_articles.json
digest.md
digest.html
```

### Site artifact

Example:

```text
daily-tech-brief-site-staging-12-1
daily-tech-brief-site-production-13-1
```

Contains the complete `site/` directory.

Regular artifacts are retained for:

```text
14 days
```

The Pages artifact is temporary and retained for one day.

## GitHub Pages setup

The repository must be public when using GitHub Pages on a GitHub Free account.

Configure the publishing source:

```text
Repository
→ Settings
→ Pages
→ Build and deployment
→ Source
→ GitHub Actions
```

The deploy job uses:

```yaml
permissions:
  pages: write
  id-token: write
```

And the environment:

```text
github-pages
```

## GitHub Pages URL

For a repository named:

```text
daily-tech-brief
```

the default URL normally follows:

```text
https://<username>.github.io/daily-tech-brief/
```

On mobile, open the URL once and save it as a browser bookmark.

The Pages URL is also available from:

```text
Repository
→ Settings
→ Pages
```

or from the successful:

```text
Deploy GitHub Pages
```

job.

## Archive behavior

The archive builder:

- preserves previous archive entries;
- adds the current local date;
- replaces an existing edition for the same local date;
- removes stale files from the replaced same-day directory;
- sorts editions newest first;
- writes both HTML and JSON indexes.

Archive manifest:

```text
site/archive/index.json
```

Example:

```json
{
  "schema_version": 1,
  "timezone": "Asia/Ho_Chi_Minh",
  "latest_date": "2026-07-30",
  "edition_count": 2,
  "editions": [
    {
      "date": "2026-07-30",
      "generated_at": "2026-07-29T23:30:00Z",
      "article_count": 12,
      "path": "2026/07/30/",
      "title": "Daily Tech Brief"
    }
  ]
}
```

## Run tests

```bash
python -m pytest -q
```

The current suite contains **104 offline tests**.

The v0.6.0 tests cover:

- static-site directory generation;
- latest edition;
- archive creation;
- local date conversion;
- archive preservation;
- same-day replacement;
- optional files;
- invalid metadata;
- Pages workflow permissions;
- production-only deployment;
- Pages action versions;
- end-to-end site publishing.

## Exit codes

- `0`: configuration is valid and at least one requested source succeeded
- `1`: every requested source failed, or source errors are fatal
- `2`: invalid configuration, invalid source selection, rendering error, or publishing error

By default:

```yaml
fail_on_source_error: false
```

Individual source failures remain isolated.

## v0.6.0 acceptance criteria

- Local configuration validation succeeds.
- All 104 tests pass.
- Local execution creates both `output/` and `site/`.
- `site/index.html` opens correctly.
- `site/archive/index.html` opens correctly.
- Archive dates use `Asia/Ho_Chi_Minh`.
- A staging workflow run uploads two regular artifacts.
- Staging does not deploy Pages.
- A production workflow run restores the prior site artifact when available.
- Production uploads a Pages artifact.
- Production deploys through the `github-pages` environment.
- The public Pages URL loads the latest digest.
- A second production run preserves the previous archive edition.

## Next version

**v0.7.0 — EPUB and TTS**

Planned work:

- Generate `digest.epub`.
- Add EPUB metadata and navigation.
- Create a TTS-friendly reading structure.
- Avoid reading long URLs aloud.
- Support Readest and KOReader.
- Add EPUB validation and renderer tests.
- Upload EPUB in workflow artifacts.
