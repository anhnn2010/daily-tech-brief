# Daily Tech Brief v0.3.0

## Summary

Version 0.3.0 upgrades Daily Tech Brief from a raw RSS/Atom collector into a personalized, explainable article-selection pipeline.

The processing flow is now:

```text
RSS / Atom feeds
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
```

## Added

### Time filtering

Added:

```text
src/filters/time_filter.py
tests/test_time_filter.py
```

Capabilities:

- Filter articles using the configured lookback window.
- Use `published_at` as the primary timestamp.
- Fall back to `updated_at` when needed.
- Treat timezone-less timestamps as UTC.
- Keep articles exactly on the cutoff boundary.
- Allow a small future-time tolerance for clock differences.
- Report old, future, missing-date, and invalid-date articles separately.

### URL deduplication

Added:

```text
src/filters/deduplicate.py
tests/test_deduplicate.py
```

Capabilities:

- Normalize URL scheme and hostname.
- Remove URL fragments.
- Remove trailing slashes where appropriate.
- Remove common tracking parameters:
  - `utm_*`
  - `fbclid`
  - `gclid`
  - `msclkid`
  - `mc_cid`
  - `mc_eid`
- Preserve meaningful query parameters.
- Sort query parameters consistently.
- Detect equivalent URLs.
- Keep the most complete article record.
- Report duplicate groups and invalid URLs.

### Rule-based ranking

Added:

```text
src/ranking/rule_based.py
tests/test_rule_based_ranking.py
```

Ranking signals:

- Source priority.
- Category weight.
- Article freshness.
- High-priority keyword matches.
- Low-priority keyword penalties.

Each ranked article includes:

- total score;
- category weight;
- freshness in hours;
- matched high-priority keywords;
- matched low-priority keywords;
- human-readable score reasons.

### Category quota selection

Added:

```text
src/ranking/selection.py
tests/test_article_selection.py
```

Capabilities:

- Select articles using per-category daily quotas.
- Use soft quotas to improve category balance.
- Fill unused slots with the highest-ranked remaining articles.
- Exclude categories with `daily_quota: 0`.
- Preserve the original ranking order.
- Report selected and deferred article counts.

### Pipeline integration test

Added:

```text
tests/test_main_pipeline.py
```

The integration test covers:

- time filtering;
- duplicate URL detection;
- invalid URL removal;
- best duplicate-record selection;
- ranking;
- category quota selection;
- `ranked_articles.json` generation.

### Generated ranked output

Added:

```text
output/ranked_articles.json
```

The output contains:

- project metadata;
- generation timestamp;
- time-filter summary;
- deduplication summary;
- ranking summary;
- selection summary;
- selected articles and score explanations.

## Changed

### Main pipeline

Updated:

```text
src/main.py
```

The application now processes collected articles through:

```text
Time filter
→ Deduplicate
→ Rank
→ Category selection
```

New console summary fields:

- articles within the lookback window;
- unique articles;
- selected articles;
- selected within quota;
- selected from overflow;
- selected category distribution.

### Runtime configuration

Updated:

```text
config/settings.yml
```

Changes:

- Project version updated to `0.3.0`.
- Ranking enabled by default.
- User-Agent version updated to `0.3.0`.
- Maximum selected articles remains 12.
- Lookback window remains 48 hours.

### Personal profile

Updated:

```text
config/profile.yml
```

The category quotas now total 12:

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

Added or refined keywords for:

- GitHub Actions;
- Jenkins;
- JFrog and Artifactory;
- Arch Linux and KDE;
- Python automation and testing;
- AI coding agents;
- post-silicon validation;
- semiconductor test;
- SerDes and high-speed interconnect;
- PyVISA, SCPI, and LXI;
- KOReader, Calibre, EPUB, OCR, and TTS.

### Documentation

Updated:

```text
README.md
```

The README now documents:

- the v0.3.0 pipeline;
- ranking rules;
- category quotas;
- generated outputs;
- commands for inspecting selected articles;
- runtime configuration;
- acceptance criteria;
- the v0.4.0 rendering plan.

### Git ignore rules

Added:

```text
.gitignore
```

Generated output, virtual environments, caches, IDE files, logs, and local secret files are excluded from Git.

## Fixed

### Source registry test

Updated the configuration test after replacing the blocked Real Python feed with Python Bytes.

Current registry:

```text
Configured sources: 18
Enabled sources:    17
```

### Freshness score boundary

Fixed a boundary issue where an article older than 48 hours by one second could still receive the 48-hour freshness bonus because the value was rounded before scoring.

Freshness scoring now uses exact seconds:

```text
48 hours          → +2
48 hours + 1 sec  → +0
```

## Compatibility notes

- Minimum supported Python version: 3.11.
- Recommended Python version: 3.12.
- Tests do not require internet access.
- Feed collection continues when individual sources fail.
- `output/` is generated locally and is not committed.

## Validation

Run configuration validation:

```bash
python -m src.main --validate-only
```

Run the complete test suite:

```bash
python -m pytest -q
```

Expected result:

```text
60 passed
```

Run the complete pipeline:

```bash
python -m src.main
```

Expected generated files:

```text
output/raw_articles.json
output/source_report.json
output/ranked_articles.json
```

## Acceptance criteria

Version 0.3.0 is complete when:

- configuration validation succeeds;
- all 60 tests pass;
- feeds can be collected successfully;
- articles outside the lookback window are excluded;
- equivalent URLs are deduplicated;
- ranked articles contain explainable score reasons;
- category quotas are applied;
- `ranked_articles.json` is generated;
- selected articles are limited to the configured maximum.

## Suggested commit

```bash
git add CHANGES-v0.3.0.md
git commit -m "Add v0.3.0 changelog"
```

## Suggested tag

After confirming the full pipeline and output:

```bash
git tag -a v0.3.0 -m "Daily Tech Brief v0.3.0"
git push origin main
git push origin v0.3.0
```

## Next version

Version 0.4.0 will add digest rendering:

- `digest.md`;
- `digest.html`;
- category grouping;
- readable daily brief templates;
- original article links;
- renderer unit tests.
