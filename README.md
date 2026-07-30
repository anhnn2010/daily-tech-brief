# Daily Tech Brief

Daily Tech Brief is a personalized technology news pipeline for collecting, filtering, deduplicating, ranking, and selecting articles from RSS and Atom feeds.

Version **0.3.0** turns the raw feed collector into a rule-based daily digest pipeline. It keeps recent articles, removes duplicate URLs, scores articles against a personal interest profile, and selects a balanced top list using per-category quotas.

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
```

## Included in v0.3.0

- Everything from v0.2.x
- Publication-time filtering with timezone support
- Fallback from `published_at` to `updated_at`
- Separate reporting for old, future, missing-date, and invalid-date articles
- Canonical URL normalization
- Removal of common tracking parameters
- Duplicate grouping and best-record selection
- Rule-based scoring with explainable score reasons
- Source priority, category weight, freshness, and keyword scoring
- High-priority keyword bonus and low-priority keyword penalty
- Soft per-category daily quotas
- Overflow filling when some categories do not have enough articles
- End-to-end `ranked_articles.json` generation
- Integration tests for the complete processing pipeline

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
│   ├── test_main_pipeline.py
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
└── ranked_articles.json
```

### `raw_articles.json`

Contains all normalized articles returned by successful RSS and Atom sources.

Each article includes:

- source ID, source name, category, priority, and tags
- title and entry URL
- feed entry ID
- publication and update times when available
- cleaned summary
- author when available
- fetch time

### `source_report.json`

Contains one report per requested source:

- status: `success`, `warning`, or `failed`
- request duration
- HTTP status and final URL
- retry count and request profile
- feed title
- article count
- parser warning or error details

### `ranked_articles.json`

Contains the final selected articles and full processing statistics:

- time-filter summary
- deduplication summary
- ranking summary
- category quota selection summary
- selected article count
- per-article score
- score reasons
- matched high-priority keywords
- matched low-priority keywords
- freshness in hours

## Inspect the selected articles

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

Inspect the category distribution:

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

The current personal profile selects at most 12 articles per run:

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
2. If the digest still has unused slots, the highest-ranked remaining articles fill them.
3. A category with `daily_quota: 0` is excluded completely.

Edit these values in:

```text
config/profile.yml
```

## Runtime configuration

Important settings in `config/settings.yml`:

```yaml
runtime:
  output_dir: output
  lookback_hours: 48
  request_timeout_seconds: 20
  max_articles: 12
  max_summary_chars: 2000
  fail_on_source_error: false
```

Ranking is enabled through:

```yaml
features:
  ranking: true
```

## Run tests

```bash
python -m pytest -q
```

The current suite contains 60 offline tests. Feed parser tests use local RSS and Atom fixtures and do not require internet access.

## Exit codes

- `0`: configuration is valid and at least one requested source succeeded
- `1`: every requested source failed, or source errors are configured as fatal
- `2`: invalid configuration, invalid source selection, or processing error

By default:

```yaml
fail_on_source_error: false
```

A failed feed is therefore recorded in `source_report.json` without stopping successful sources.

## v0.3.0 acceptance criteria

- Articles outside the configured lookback window are excluded.
- Missing and invalid dates are reported separately.
- Equivalent URLs are deduplicated.
- Tracking parameters do not create false duplicates.
- Ranking is deterministic and explainable.
- Category quotas prevent a single topic from dominating the digest.
- Unused category slots can be filled by the best remaining articles.
- `ranked_articles.json` is written atomically.
- The complete processing pipeline is covered by integration tests.

## Next version

**v0.4.0 — Digest Rendering**

Planned work:

- Generate `digest.md`
- Generate `digest.html`
- Group selected articles by category
- Add a clean daily brief layout
- Keep links to original sources
- Skip empty categories
- Add renderer unit tests
