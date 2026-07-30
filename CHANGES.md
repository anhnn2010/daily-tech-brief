# Daily Tech Brief v0.4.0

## Summary

Version 0.4.0 adds readable Markdown and standalone HTML rendering to the Daily Tech Brief pipeline.

The complete flow is now:

```text
RSS / Atom feeds
    ↓
Collection
    ↓
Time filtering
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
```

## Added

### Markdown renderer

Added:

```text
src/renderers/markdown.py
tests/test_markdown_renderer.py
```

Capabilities:

- Group selected articles by category.
- Preserve category order from `config/profile.yml`.
- Omit categories with no selected articles.
- Render linked article titles.
- Display source, publication time, score, summary, and matched interests.
- Convert timestamps to the configured local timezone.
- Escape Markdown-sensitive characters.
- Handle missing summaries and invalid article dates.
- Render a readable empty state when no articles are selected.
- Avoid external dependencies.

### HTML renderer

Added:

```text
src/renderers/html.py
tests/test_html_renderer.py
```

Capabilities:

- Generate a complete standalone HTML document.
- Work without JavaScript, external CSS, fonts, images, or CDNs.
- Use responsive layouts for desktop and mobile.
- Support automatic light and dark mode.
- Provide print-friendly styles.
- Group articles by category.
- Add category navigation links.
- Display source, local publication time, score, summary, and matched interests.
- Escape feed content and URLs safely.
- Omit empty categories.
- Render a readable empty state.
- Support future GitHub Pages publishing without another build system.

### Rendering integration test

Added:

```text
tests/test_rendering_pipeline.py
```

The integration test confirms that one pipeline run creates:

```text
ranked_articles.json
digest.md
digest.html
```

It also verifies that:

- the selected article count is consistent;
- Markdown and HTML contain the selected articles;
- category sections are rendered correctly;
- rendering metadata is written to `ranked_articles.json`;
- project metadata reports version `0.4.0`.

## Changed

### Main pipeline

Updated:

```text
src/main.py
```

The pipeline now supports two independent rendering feature flags:

```yaml
features:
  render_markdown: true
  render_html: true
```

Rendering occurs after filtering, deduplication, ranking, and category selection.

The program now writes:

```text
output/digest.md
output/digest.html
```

using atomic file replacement.

### Rendering metadata

`ranked_articles.json` now contains:

```json
{
  "summary": {
    "rendering": {
      "markdown": {
        "enabled": true,
        "path": "output/digest.md",
        "article_count": 12
      },
      "html": {
        "enabled": true,
        "path": "output/digest.html",
        "article_count": 12
      }
    }
  }
}
```

The ranked JSON file is written after rendering metadata has been finalized.

### Runtime configuration

Updated:

```text
config/settings.yml
```

Changes:

- Project version updated to `0.4.0`.
- User-Agent version updated to `0.4.0`.
- Markdown rendering enabled by default.
- HTML rendering enabled by default.

Current rendering configuration:

```yaml
features:
  ranking: true
  render_markdown: true
  render_html: true
  ai_editor: false
  epub: false
```

### Documentation

Updated:

```text
README.md
```

The documentation now includes:

- the complete v0.4.0 pipeline;
- generated Markdown and HTML files;
- renderer directory structure;
- commands for opening the HTML digest;
- rendering feature flags;
- rendering metadata;
- standalone HTML characteristics;
- updated acceptance criteria;
- the GitHub Actions roadmap.

## Generated outputs

A successful run now produces:

```text
output/
├── raw_articles.json
├── source_report.json
├── ranked_articles.json
├── digest.md
└── digest.html
```

### `digest.md`

A portable Markdown digest suitable for:

- terminal viewing;
- GitHub preview;
- note-taking applications;
- later EPUB generation.

### `digest.html`

A responsive standalone page suitable for:

- local browser viewing;
- mobile reading;
- printing or PDF export;
- future GitHub Pages publishing.

## Compatibility notes

- Minimum supported Python version: 3.11.
- Recommended Python version: 3.12.
- No new runtime dependency is required.
- Renderer tests are fully offline.
- Existing JSON outputs remain available.
- Rendering can be disabled independently through feature flags.
- Generated files under `output/` remain excluded from Git.

## Validation

Validate configuration:

```bash
python -m src.main --validate-only
```

Run the complete test suite:

```bash
python -m pytest -q
```

Expected result:

```text
84 passed
```

Run the full pipeline:

```bash
python -m src.main
```

Expected output list:

```text
output/raw_articles.json
output/source_report.json
output/ranked_articles.json
output/digest.md
output/digest.html
```

Open the HTML digest on Linux:

```bash
xdg-open output/digest.html
```

Inspect the Markdown digest:

```bash
less output/digest.md
```

## Acceptance criteria

Version 0.4.0 is complete when:

- configuration validation succeeds;
- all 84 tests pass;
- feed collection completes with per-source error isolation;
- article filtering, deduplication, ranking, and quota selection remain functional;
- `ranked_articles.json` is generated;
- `digest.md` is generated when Markdown rendering is enabled;
- `digest.html` is generated when HTML rendering is enabled;
- empty categories are omitted;
- article content is escaped safely;
- local timezone conversion is correct;
- rendering metadata matches the generated files;
- HTML opens correctly without external assets.

## Suggested commit

```bash
git add CHANGES-v0.4.0.md
git commit -m "Add v0.4.0 changelog"
```

## Suggested tag

After confirming the complete pipeline:

```bash
git tag -a v0.4.0 -m "Daily Tech Brief v0.4.0"
git push origin main
git push origin v0.4.0
```

## Next version

Version 0.5.0 will add GitHub Actions automation:

- run on `ubuntu-24.04`;
- use Python 3.12;
- support manual execution;
- support scheduled execution;
- validate configuration;
- run the offline test suite;
- generate JSON, Markdown, and HTML outputs;
- upload generated files as a workflow artifact;
- keep GitHub Pages and Releases disabled until the staging workflow is stable.
