# Daily Tech Brief v0.7.0

## Summary

Version 0.7.0 adds EPUB 3 generation and a TTS-friendly reading flow to Daily Tech Brief.

The complete pipeline is now:

```text
GitHub Actions
    ↓
Configuration validation
    ↓
Offline test suite
    ↓
RSS / Atom collection
    ↓
Time filtering
    ↓
URL normalization and deduplication
    ↓
Rule-based ranking
    ↓
Category quota selection
    ↓
Markdown rendering
HTML rendering
EPUB rendering
    ↓
Static site generation
    ↓
EPUB publication verification
    ↓
Artifacts
GitHub Pages
```

## Added

### EPUB 3 renderer

Added:

```text
src/renderers/epub.py
tests/test_epub_renderer.py
```

The renderer creates:

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
    └── category-*.xhtml
```

Capabilities:

- EPUB 3 package metadata.
- EPUB navigation through `nav.xhtml`.
- NCX fallback navigation.
- One chapter per non-empty category.
- One section per selected article.
- Category ordering from `profile.yml`.
- Unicode-safe XHTML.
- XML escaping for feed-provided content.
- Stable identifiers.
- Deterministic binary output for identical input.
- Collision-safe category filenames.
- Valid empty-digest output.
- Standard-library-only implementation.

The EPUB `mimetype` entry is stored first and without compression.

### TTS-friendly article content

Each article is rendered with a compact structure:

```text
Article title

Source: Example News.
Published: 2026-07-30 08:00 Asia/Ho_Chi_Minh.
Author: Example Author.

Article summary...

Read the original article.
```

The visible reading content excludes:

- ranking scores;
- score reasons;
- matched keywords;
- raw article URLs.

Long URLs remain only in the link destination:

```html
<a href="https://example.com/long/article/url">
  Read the original article
</a>
```

This prevents many TTS engines from reading full URLs aloud.

Whitespace in summaries is normalized before rendering.

### EPUB pipeline integration

Updated:

```text
src/main.py
tests/test_rendering_pipeline.py
```

When enabled, the pipeline writes:

```text
output/digest.epub
```

The execution summary includes:

```json
{
  "epub": {
    "enabled": true,
    "path": "output/digest.epub",
    "article_count": 12,
    "size_bytes": 18432
  }
}
```

The file is written atomically.

When EPUB is disabled, the pipeline does not create `digest.epub`.

Older configuration files without a `render_epub` key remain compatible and behave as if EPUB rendering is disabled.

### EPUB configuration

Updated:

```text
config/settings.yml
```

Changes:

```yaml
project:
  version: 0.7.0
```

```yaml
runtime:
  user_agent: DailyTechBrief/0.7.0
```

```yaml
features:
  render_epub: true
```

The renderer can be disabled independently:

```yaml
features:
  render_epub: false
```

No new runtime dependency was added.

### Direct EPUB download link

Updated:

```text
src/renderers/html.py
tests/test_html_renderer.py
```

When EPUB rendering is enabled, the HTML digest displays:

```text
Download EPUB
```

The generated link uses:

```html
<a class="download-link" href="digest.epub" download>
  Download EPUB
</a>
```

The relative path works at:

```text
site/index.html
site/latest/index.html
site/archive/YYYY/MM/DD/index.html
```

The link is:

- omitted when EPUB is disabled;
- touch-friendly on mobile;
- hidden in print output;
- HTML escaped;
- validated before rendering.

### EPUB static-site publishing

Updated:

```text
src/publishing/site_builder.py
tests/test_site_builder.py
tests/test_site_pipeline.py
```

When `output/digest.epub` exists, the site builder publishes:

```text
site/digest.epub
site/latest/digest.epub
site/archive/YYYY/MM/DD/digest.epub
```

Behavior:

- root EPUB always represents the latest edition;
- `/latest/digest.epub` represents the latest edition;
- each dated archive keeps its own EPUB;
- a same-day rerun replaces the same-day EPUB;
- an older archive EPUB remains unchanged;
- EPUB remains optional;
- no empty EPUB is created when rendering is disabled.

The end-to-end site pipeline test confirms the generated EPUB reaches the Pages-ready site.

### EPUB workflow verification

Updated:

```text
.github/workflows/generate_digest.yml
tests/test_github_workflow.py
```

A new workflow step runs after generation:

```text
Verify EPUB publication
```

It checks that these files exist and are non-empty:

```text
output/digest.epub
site/digest.epub
site/latest/digest.epub
```

It finds the current archive EPUB by matching binary content:

```bash
find site/archive   -type f   -path '*/digest.epub'   -exec cmp -s output/digest.epub {} \;   -print   -quit
```

It verifies:

```bash
cmp output/digest.epub site/digest.epub
cmp output/digest.epub site/latest/digest.epub
cmp output/digest.epub "${archive_epub}"
```

It also confirms the website contains:

```text
href="digest.epub"
Download EPUB
```

The verification step runs before:

- data artifact upload;
- static-site artifact upload;
- GitHub Pages artifact upload.

The workflow therefore fails before publishing if EPUB generation or publication is broken.

## Changed

### Generated output

The output directory now contains:

```text
output/
├── raw_articles.json
├── source_report.json
├── ranked_articles.json
├── digest.md
├── digest.html
└── digest.epub
```

### Static site

The site now contains:

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

### Public URLs

The deployed site now provides:

```text
/                         Latest edition
/latest/                  Latest edition
/archive/                 Archive index
/archive/YYYY/MM/DD/      Dated edition
/digest.epub              Latest EPUB
/latest/digest.epub       Latest EPUB
```

Each edition page links to the EPUB in its own directory.

### Workflow artifacts

The data artifact now includes:

```text
digest.epub
```

The site artifact includes:

```text
digest.epub
latest/digest.epub
archive/YYYY/MM/DD/digest.epub
```

The Pages artifact includes the same published EPUB files because it uploads the complete `site/` directory.

### Documentation

Updated:

```text
README.md
```

The documentation now covers:

- EPUB structure;
- TTS-friendly rendering;
- feature configuration;
- local validation;
- static-site URLs;
- Readest and KOReader usage;
- workflow verification;
- artifact contents;
- release acceptance criteria.

## Compatibility notes

- Minimum supported Python version: 3.11.
- Recommended Python version: 3.12.
- GitHub Actions uses Python 3.12.
- GitHub Actions uses `ubuntu-24.04`.
- The repository default branch is `master`.
- The EPUB renderer uses only the Python standard library.
- Existing Markdown and HTML outputs remain available.
- Existing configuration files without `render_epub` remain valid.
- EPUB rendering can be disabled independently.
- The site builder still supports output directories without an EPUB.
- Feed collection requires network access.
- The test suite remains offline.
- Actual layout and TTS behavior may vary between readers and devices.

## Validation

Validate configuration:

```bash
python -m src.main --validate-only
```

Run the complete test suite:

```bash
python -m pytest -q
```

Expected result after all v0.7.0 files are applied:

```text
137 passed
```

The actual local pytest result should be treated as the release source of truth.

Run the complete pipeline:

```bash
python -m src.main
```

Inspect the EPUB:

```bash
unzip -l output/digest.epub
unzip -p output/digest.epub mimetype
unzip -t output/digest.epub
```

Expected mimetype:

```text
application/epub+zip
```

Check the HTML download link:

```bash
grep -n "Download EPUB" output/digest.html
grep -n 'href="digest.epub"' output/digest.html
```

Compare generated and published files:

```bash
cmp output/digest.epub site/digest.epub
cmp output/digest.epub site/latest/digest.epub
```

Find matching archive EPUB:

```bash
find site/archive   -type f   -path '*/digest.epub'   -exec cmp -s output/digest.epub {} \;   -print
```

## Staging verification

Run:

```text
Actions
→ Generate Daily Tech Brief
→ Run workflow
→ Branch: master
→ Environment: staging
```

Confirm:

- configuration validation passes;
- the offline test suite passes;
- generation succeeds;
- `Verify EPUB publication` succeeds;
- the data artifact contains `digest.epub`;
- the site artifact contains root, latest, and archive EPUB files;
- no Pages deployment occurs.

## Production verification

Run:

```text
Actions
→ Generate Daily Tech Brief
→ Run workflow
→ Branch: master
→ Environment: production
```

Confirm:

- the previous production archive is restored when available;
- the current EPUB is added or replaces the same-day EPUB;
- previous archive EPUB files remain present;
- `Verify EPUB publication` succeeds;
- the Pages artifact contains EPUB files;
- GitHub Pages deploys successfully;
- the public **Download EPUB** button works;
- the downloaded EPUB matches the latest edition.

## Device verification

The release should be checked in at least the intended target readers.

### Readest

Confirm:

- the file imports or opens;
- the table of contents is visible;
- category chapters open;
- Unicode text displays correctly;
- TTS reads article titles and summaries;
- TTS does not read the complete raw URL aloud.

### KOReader

Confirm:

- the file opens as a normal EPUB;
- navigation works;
- category chapters are visible;
- Unicode text displays correctly;
- the original-article link is usable when network access is available.

These are acceptance checks, not claims that every reader will render or speak the EPUB identically.

## Acceptance criteria

Version 0.7.0 is complete when:

- configuration validation succeeds;
- the complete local test suite passes;
- the final local test count is recorded;
- `output/digest.epub` is generated;
- the EPUB ZIP container validates;
- the EPUB mimetype is correct;
- EPUB metadata and navigation open correctly;
- Unicode content displays correctly;
- visible text does not include full raw URLs;
- `output/digest.html` contains **Download EPUB**;
- `site/digest.epub` matches the generated EPUB;
- `site/latest/digest.epub` matches the generated EPUB;
- the current dated archive contains the matching EPUB;
- a same-day rerun replaces the same-day EPUB;
- a later-day run preserves older archive EPUB files;
- staging passes EPUB publication verification;
- staging artifacts contain EPUB files;
- production deploys EPUB files through GitHub Pages;
- the public download button works;
- the EPUB opens in Readest;
- the EPUB opens in KOReader;
- basic TTS behavior is checked in at least one target reader.

## Suggested release commands

Run final checks:

```bash
python -m src.main --validate-only
python -m pytest -q
python -m src.main
unzip -t output/digest.epub
grep -n "Download EPUB" output/digest.html
cmp output/digest.epub site/digest.epub
cmp output/digest.epub site/latest/digest.epub
```

Commit the changelog:

```bash
git add CHANGES-v0.7.0.md
git commit -m "Add v0.7.0 changelog"
git push origin master
```

After staging, production, Pages, Readest, and KOReader checks succeed:

```bash
git tag -a v0.7.0 -m "Daily Tech Brief v0.7.0"
git push origin master
git push origin v0.7.0
```

## Next version

Version 0.8.0 is planned to explore an AI-assisted editor:

- concise editorial introductions;
- consistent summary style;
- preserved source attribution;
- unsupported-claim prevention;
- provider-independent interfaces;
- rule-based fallback;
- GitHub Actions secrets;
- token and cost controls;
- deterministic offline tests with mocked providers.
