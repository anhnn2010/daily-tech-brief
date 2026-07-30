# Daily Tech Brief

Daily Tech Brief is a personalized technology news pipeline for collecting, filtering, deduplicating, ranking, selecting, rendering, publishing, and automating technology digests from RSS and Atom feeds.

Version **0.7.0** adds EPUB 3 generation, TTS-friendly reading content, direct EPUB downloads from the website, and EPUB publication checks in GitHub Actions.

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
digest.epub
    ↓
Static site builder
    ↓
site/
    ↓
GitHub Actions artifacts
GitHub Pages
```

## Included in v0.7.0

- Everything from v0.6.x
- EPUB 3 renderer
- EPUB navigation document
- NCX fallback navigation
- Chapter-per-category layout
- Unicode-safe XHTML
- TTS-friendly article structure
- Long URLs excluded from spoken text
- Direct **Download EPUB** link in HTML
- EPUB publication at site root
- EPUB publication under `/latest/`
- EPUB publication inside each dated archive
- Same-day EPUB replacement
- Previous archive EPUB preservation
- EPUB workflow verification
- EPUB renderer, pipeline, site, and workflow tests
- No new runtime dependency

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
│   │   ├── epub.py
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
│   ├── test_epub_renderer.py
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

The EPUB renderer uses only the Python standard library, so v0.7.0 does not add a new package dependency.

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
├── digest.html
└── digest.epub
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

A standalone responsive HTML edition with a relative **Download EPUB** link when EPUB rendering is enabled.

### `digest.epub`

An EPUB 3 edition designed for normal reading and text-to-speech use.

## EPUB structure

The generated EPUB contains:

```text
digest.epub
├── mimetype
├── META-INF/
│   └── container.xml
└── EPUB/
    ├── package.opf
    ├── nav.xhtml
    ├── toc.ncx
    ├── styles.css
    ├── title.xhtml
    ├── category-ai.xhtml
    ├── category-linux.xhtml
    └── ...
```

The renderer provides:

- EPUB 3 package metadata;
- EPUB navigation through `nav.xhtml`;
- NCX fallback navigation for older readers;
- one chapter per non-empty category;
- one section per selected article;
- project title, language, creator, identifier, and modified time;
- stable category ordering from `profile.yml`;
- valid Unicode XHTML;
- deterministic binary output for identical input.

The `mimetype` file is stored first and without compression, as required by the EPUB container format.

## TTS-friendly content

Each article is rendered with a compact reading structure:

```text
Article title

Source: Example News.
Published: 2026-07-30 08:00 Asia/Ho_Chi_Minh.
Author: Example Author.

Article summary...

Read the original article.
```

The EPUB intentionally excludes ranking-debug information such as:

- score;
- score reasons;
- matched keywords.

Long article URLs appear only in the link destination:

```html
<a href="https://example.com/very/long/article/url">
  Read the original article
</a>
```

The raw URL is not inserted as visible paragraph text, which prevents many TTS engines from reading the complete URL aloud.

Feed summary whitespace is normalized before it is placed in the EPUB.

## EPUB configuration

EPUB rendering is controlled in:

```text
config/settings.yml
```

Current configuration:

```yaml
project:
  version: 0.7.0

runtime:
  output_dir: output
  site_dir: site
  user_agent: DailyTechBrief/0.7.0

features:
  render_markdown: true
  render_html: true
  render_epub: true
  build_site: true
```

Disable EPUB without disabling the other renderers:

```yaml
features:
  render_epub: false
```

When disabled:

- `output/digest.epub` is not created;
- the HTML page does not show **Download EPUB**;
- the site builder does not create empty EPUB files;
- Markdown, HTML, JSON, and static-site generation continue normally.

Configuration files created before v0.7.0 that do not contain `render_epub` remain compatible and behave as if EPUB rendering is disabled.

## Inspect the EPUB

List files inside the EPUB:

```bash
unzip -l output/digest.epub
```

Read its mimetype:

```bash
unzip -p output/digest.epub mimetype
```

Expected output:

```text
application/epub+zip
```

Check the ZIP container:

```bash
unzip -t output/digest.epub
```

The command should finish with:

```text
No errors detected in compressed data
```

## Reading the EPUB

The generated file is intended for standards-compatible EPUB readers, including desktop, mobile, and e-reader applications.

Typical flow:

```text
Open the Daily Tech Brief website
→ Tap Download EPUB
→ Save or open digest.epub
→ Import it into the preferred EPUB reader
```

For KOReader, copy or download `digest.epub` to a directory visible in its file browser and open it as a normal book.

For Readest or another mobile reader, download the file and import or open it through the application's normal file workflow.

Actual layout and TTS voice behavior can vary by reader and device, so both Readest and KOReader should be checked during the v0.7.0 acceptance test.

## Static site output

The site builder creates:

```text
site/
├── index.html
├── digest.md
├── digest.epub
├── ranked_articles.json
├── source_report.json
├── site.json
├── .nojekyll
│
├── latest/
│   ├── index.html
│   ├── digest.md
│   ├── digest.epub
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
                ├── digest.epub
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
/digest.epub              Latest EPUB edition
/latest/digest.epub       Latest EPUB edition
/ranked_articles.json     Latest ranked JSON
/source_report.json       Latest source report
/site.json                Site metadata
```

Every edition page uses the relative path:

```text
digest.epub
```

Because each HTML page and its EPUB file are stored in the same directory, the same link works at the site root, under `/latest/`, and in every dated archive.

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

Compare generated and published EPUB files:

```bash
cmp output/digest.epub site/digest.epub
cmp output/digest.epub site/latest/digest.epub
cmp output/digest.epub site/archive/*/*/*/digest.epub
```

A successful `cmp` command prints nothing and returns exit code `0`.

## Archive behavior

The archive builder:

- preserves previous archive entries;
- preserves EPUB files from previous dates;
- adds the current local date;
- replaces an existing edition for the same local date;
- replaces the same-day EPUB with the newly generated EPUB;
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
→ Verify EPUB publication
→ Upload data artifact
→ Upload site artifact
→ Deploy GitHub Pages for production
```

## EPUB workflow verification

Before any artifact is uploaded, the workflow checks that these files exist and are non-empty:

```text
output/digest.epub
site/digest.epub
site/latest/digest.epub
```

It then finds the current archive EPUB by comparing binary content rather than selecting an arbitrary archived date.

The workflow verifies:

```bash
cmp output/digest.epub site/digest.epub
cmp output/digest.epub site/latest/digest.epub
cmp output/digest.epub "${archive_epub}"
```

It also verifies the website link:

```bash
grep -q 'href="digest.epub"' site/index.html
grep -q 'Download EPUB' site/index.html
```

This step runs before:

- data artifact upload;
- static-site artifact upload;
- Pages artifact upload.

A workflow run therefore fails before publishing if the EPUB is missing, empty, incorrectly copied, or no longer linked from the page.

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
→ Verify EPUB publication
→ Upload output artifact
→ Upload site artifact
```

Staging does **not**:

- restore the production archive;
- upload a GitHub Pages artifact;
- deploy GitHub Pages;
- replace the public website.

Use staging for checking:

- source collection;
- ranking;
- HTML layout;
- EPUB structure;
- EPUB download link;
- archive structure;
- workflow changes.

## Production behavior

Production performs:

```text
Restore previous production site artifact
→ Generate current digest
→ Merge current edition into archive
→ Verify EPUB publication
→ Upload output artifact
→ Upload site artifact
→ Upload Pages artifact
→ Deploy GitHub Pages
```

The production workflow restores the most recent unexpired site artifact named like:

```text
daily-tech-brief-site-production-<run-number>-<run-attempt>
```

This preserves dated HTML, Markdown, JSON, and EPUB editions between workflow runs.

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
digest.epub
```

### Site artifact

Example:

```text
daily-tech-brief-site-staging-12-1
daily-tech-brief-site-production-13-1
```

Contains the complete `site/` directory, including the latest EPUB and archived EPUB editions.

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

## Run tests

```bash
python -m pytest -q
```

After all v0.7.0 files are applied, the expected project suite contains:

```text
128 offline tests
```

The v0.7.0 tests cover:

- EPUB ZIP structure;
- uncompressed and first-position mimetype;
- package metadata;
- navigation document;
- NCX fallback;
- category chapters;
- category slug collisions;
- empty digests;
- Unicode content;
- XML escaping;
- deterministic output;
- TTS-friendly visible text;
- hidden raw URLs;
- EPUB feature flag behavior;
- HTML download-link behavior;
- EPUB pipeline summary;
- root, latest, and archive publishing;
- same-day EPUB replacement;
- previous archive EPUB preservation;
- production workflow verification;
- verification ordering before artifact upload;
- end-to-end Pages-ready EPUB publication.

## Exit codes

- `0`: configuration is valid and at least one requested source succeeded
- `1`: every requested source failed, or source errors are fatal
- `2`: invalid configuration, invalid source selection, rendering error, or publishing error

By default:

```yaml
fail_on_source_error: false
```

Individual source failures remain isolated.

## v0.7.0 acceptance criteria

- Local configuration validation succeeds.
- The complete offline test suite passes.
- The final test count is confirmed in the local repository.
- Local execution creates `output/digest.epub`.
- `unzip -t output/digest.epub` reports no compressed-data errors.
- EPUB metadata and navigation open correctly in an EPUB reader.
- Vietnamese and English Unicode text display correctly.
- TTS does not read full article URLs as visible text.
- `output/digest.html` contains the **Download EPUB** link.
- `site/digest.epub` matches the generated EPUB.
- `site/latest/digest.epub` matches the generated EPUB.
- The current dated archive contains the matching EPUB.
- A same-day rerun replaces that day's EPUB without duplicating the edition.
- A later-day run preserves EPUB files from earlier archive dates.
- A staging workflow passes **Verify EPUB publication**.
- The staging data artifact contains `digest.epub`.
- The staging site artifact contains root, latest, and archive EPUB files.
- A production workflow deploys the EPUB through GitHub Pages.
- The public **Download EPUB** button downloads the latest EPUB.
- The EPUB can be imported and opened in Readest.
- The EPUB can be opened in KOReader.
- Basic TTS reading is checked in at least one target reader.

## Suggested v0.7.0 release check

```bash
python -m src.main --validate-only
python -m pytest -q
python -m src.main
unzip -t output/digest.epub
grep -n "Download EPUB" output/digest.html
cmp output/digest.epub site/digest.epub
cmp output/digest.epub site/latest/digest.epub
```

Then run a GitHub Actions staging build:

```text
Actions
→ Generate Daily Tech Brief
→ Run workflow
→ Branch: master
→ Environment: staging
```

Download and inspect both artifacts before running production.

## Next version

**v0.8.0 — AI-assisted editor**

Candidate work:

- generate a concise editorial introduction;
- rewrite feed summaries into a consistent style;
- preserve source attribution;
- prevent unsupported claims;
- keep the original rule-based pipeline as fallback;
- add provider-independent editor interfaces;
- keep API keys in GitHub Actions secrets;
- add cost and token controls;
- add deterministic offline tests with mocked providers.
