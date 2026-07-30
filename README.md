# Daily Tech Brief

Daily Tech Brief is a personalized technology news pipeline for collecting, filtering, deduplicating, ranking, selecting, and rendering articles from RSS and Atom feeds.

Version **0.4.0** adds readable Markdown and standalone HTML digests on top of the v0.3.0 ranking pipeline.

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
```

## Included in v0.4.0

- Everything from v0.3.x
- Markdown digest rendering
- Standalone HTML digest rendering
- Responsive HTML layout
- Automatic light and dark mode
- Print-friendly HTML styles
- Category navigation
- Category grouping using labels from `profile.yml`
- Local timezone conversion
- Markdown and HTML escaping
- Atomic output writes
- Rendering metadata in `ranked_articles.json`
- Integration tests for the complete rendering pipeline

## Project structure

```text
daily-tech-brief/
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

## Validate configuration

```bash
python -m src.main --validate-only
```

Machine-readable validation summary:

```bash
python -m src.main --validate-only --json
```

The current source registry contains 18 configured sources, with 17 enabled by default.

## Run the pipeline

Fetch and process all enabled sources:

```bash
python -m src.main
```

Run selected sources while debugging:

```bash
python -m src.main --source arch_linux_news
python -m src.main --source arch_linux_news --source planet_kde
```

Write outputs to another directory:

```bash
python -m src.main --output-dir output/debug
```

Print a machine-readable execution summary:

```bash
python -m src.main --json
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

Contains all normalized articles returned by successful RSS and Atom sources.

### `source_report.json`

Contains one report per requested source:

- status: `success`, `warning`, or `failed`;
- request duration;
- HTTP status and final URL;
- retry count and request profile;
- feed title;
- article count;
- parser warning or error details.

### `ranked_articles.json`

Contains the final selected articles and processing statistics:

- time-filter summary;
- deduplication summary;
- ranking summary;
- category quota selection summary;
- rendering summary;
- selected article count;
- per-article score;
- score reasons;
- matched keywords;
- freshness in hours.

### `digest.md`

A portable Markdown edition grouped by category.

Each article contains:

- linked title;
- source;
- publication time;
- ranking score;
- cleaned summary;
- matched interests;
- original article link.

### `digest.html`

A standalone HTML edition that can be:

- opened locally;
- read on desktop or mobile;
- published through GitHub Pages;
- printed or exported to PDF;
- viewed in light or dark mode.

The page does not require JavaScript, external CSS, external fonts, or a CDN.

## Open the generated digest

On Linux:

```bash
xdg-open output/digest.html
```

On macOS:

```bash
open output/digest.html
```

On Windows PowerShell:

```powershell
Start-Process output/digest.html
```

Read Markdown in the terminal:

```bash
less output/digest.md
```

## Inspect selected articles

```bash
python - <<'PY'
import json

with open("output/ranked_articles.json", encoding="utf-8") as file:
    data = json.load(file)

for index, article in enumerate(data["articles"], 1):
    print(
        f"{index:02}. [{article['score']}] "
        f"[{article['category']}] {article['title']}"
    )
PY
```

Inspect category distribution:

```bash
python - <<'PY'
import json
from collections import Counter

with open("output/ranked_articles.json", encoding="utf-8") as file:
    data = json.load(file)

counts = Counter(
    article["category"]
    for article in data["articles"]
)

for category, count in sorted(counts.items()):
    print(f"{category}: {count}")
PY
```

Inspect rendering metadata:

```bash
python - <<'PY'
import json

with open("output/ranked_articles.json", encoding="utf-8") as file:
    data = json.load(file)

print(
    json.dumps(
        data["summary"]["rendering"],
        indent=2,
        ensure_ascii=False,
    )
)
PY
```

## Ranking model

The current scorer is deterministic and explainable.

### Source priority

```text
source_priority × 2
```

### Category weight

```text
category_weight × 2
```

### Freshness bonus

| Article age | Bonus |
|---|---:|
| Up to 6 hours | +10 |
| Up to 12 hours | +8 |
| Up to 24 hours | +6 |
| Up to 36 hours | +4 |
| Up to 48 hours | +2 |
| Older than 48 hours | +0 |

### Keyword scoring

- High-priority keyword in title: `+8`
- High-priority keyword in summary or source tags: `+4`
- Maximum high-priority keyword bonus: `+24`
- Low-priority keyword match: `-6`
- Maximum low-priority keyword penalty: `-12`

The final score never goes below zero.

## Category quotas

The personal profile selects at most 12 articles per run:

| Category | Daily quota |
|---|---:|
| AI | 2 |
| Automation / CI | 2 |
| Python | 1 |
| Linux | 2 |
| Open Source / Engineering | 1 |
| Semiconductor | 2 |
| Test Engineering | 1 |
| Ebook | 1 |
| **Total** | **12** |

The quotas are soft:

1. The first pass respects each category quota.
2. If the digest has unused slots, the highest-ranked remaining articles fill them.
3. A category with `daily_quota: 0` is excluded completely.

Edit these values in:

```text
config/profile.yml
```

## Rendering configuration

Rendering is controlled in `config/settings.yml`:

```yaml
features:
  ranking: true
  render_markdown: true
  render_html: true
```

Disable a renderer without changing code:

```yaml
features:
  render_markdown: false
  render_html: true
```

## Runtime configuration

Important settings:

```yaml
runtime:
  output_dir: output
  lookback_hours: 48
  request_timeout_seconds: 20
  max_articles: 12
  max_summary_chars: 2000
  fail_on_source_error: false
```

## Run tests

```bash
python -m pytest -q
```

The current suite contains **84 offline tests**. Feed parser tests use local RSS and Atom fixtures and do not require internet access.

## Exit codes

- `0`: configuration is valid and at least one requested source succeeded
- `1`: every requested source failed, or source errors are configured as fatal
- `2`: invalid configuration, invalid source selection, or processing error

By default:

```yaml
fail_on_source_error: false
```

A failed feed is recorded in `source_report.json` without stopping successful sources.

## v0.4.0 acceptance criteria

- The v0.3.0 ranking pipeline remains functional.
- `digest.md` is generated when Markdown rendering is enabled.
- `digest.html` is generated when HTML rendering is enabled.
- Empty categories are omitted.
- Article links point to original sources.
- Feed content is safely escaped.
- Times are shown in the configured local timezone.
- HTML is responsive and standalone.
- Rendering metadata is recorded in `ranked_articles.json`.
- All 84 tests pass.

## Next version

**v0.5.0 — GitHub Actions**

Planned work:

- Add a workflow running on `ubuntu-24.04`.
- Use Python 3.12.
- Support manual runs and scheduled runs.
- Validate configuration.
- Run tests.
- Generate all outputs.
- Upload output files as a GitHub Actions artifact.
- Keep publishing disabled until the staging workflow is stable.
