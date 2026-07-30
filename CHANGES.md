# Daily Tech Brief v0.5.0

## Summary

Version 0.5.0 adds GitHub Actions automation to the Daily Tech Brief project.

The project can now run automatically on GitHub using Python 3.12 and Ubuntu 24.04, generate all digest outputs, and upload them as workflow artifacts.

The complete flow is now:

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
Markdown and HTML rendering
    ↓
GitHub Actions artifact
```

## Added

### Unified GitHub Actions workflow

Added:

```text
.github/workflows/generate_digest.yml
```

The workflow supports:

- manual execution;
- staging runs;
- production runs;
- daily scheduled production runs;
- GitHub Environments;
- Python dependency caching;
- configuration validation;
- test execution;
- digest generation;
- artifact upload;
- concurrency control.

### Manual environments

Manual workflow runs support:

```text
staging
production
```

The default environment is:

```text
staging
```

Both environments currently use the same code and configuration.

They are separated now so later versions can publish production output while staging remains artifact-only.

### Scheduled production run

The workflow schedule is:

```yaml
schedule:
  - cron: "30 23 * * *"
```

This corresponds approximately to:

```text
06:30 Asia/Ho_Chi_Minh
```

Scheduled workflow runs always use the `production` environment.

### GitHub-hosted runtime

The workflow uses:

```text
Runner: ubuntu-24.04
Python: 3.12
```

Actions used:

```text
actions/checkout@v6
actions/setup-python@v6
actions/upload-artifact@v4
```

### Artifact upload

A successful workflow uploads the complete generated output directory.

Artifact names follow this format:

```text
daily-tech-brief-staging-<run-number>
daily-tech-brief-production-<run-number>
```

Artifact contents:

```text
raw_articles.json
source_report.json
ranked_articles.json
digest.md
digest.html
```

Artifact retention is:

```text
14 days
```

### Workflow regression tests

Added:

```text
tests/test_github_workflow.py
```

The tests verify that the workflow retains:

- manual trigger;
- scheduled trigger;
- the production schedule;
- `ubuntu-24.04`;
- Python 3.12;
- staging and production options;
- configuration validation;
- test execution;
- digest generation;
- artifact upload;
- artifact retention.

## Changed

### Project version

Updated:

```text
config/settings.yml
```

Changes:

```yaml
project:
  version: 0.5.0
```

The runtime User-Agent is now:

```yaml
runtime:
  user_agent: DailyTechBrief/0.5.0
```

### Workflow structure

The original staging-only workflow was replaced by a unified workflow.

Removed:

```text
.github/workflows/generate_digest_staging.yml
```

Added:

```text
.github/workflows/generate_digest.yml
```

This avoids duplicating staging and production workflow logic.

### Documentation

Updated:

```text
README.md
```

The README now documents:

- local execution;
- GitHub Actions execution;
- staging and production behavior;
- scheduled runs;
- GitHub Environments;
- workflow artifacts;
- artifact download through the GitHub website;
- GitHub Mobile limitations;
- concurrency behavior;
- workflow acceptance criteria.

## GitHub Environments

The repository should contain these environments:

```text
staging
production
```

Create them through:

```text
Repository Settings
→ Environments
→ New environment
```

No secrets are required in v0.5.0.

Future versions may add environment-specific values such as:

```text
AI_API_KEY
PUBLISH_TARGET
RELEASE_CHANNEL
```

## Concurrency behavior

Workflow concurrency is separated by environment.

Only one active run is kept for:

```text
staging
production
```

When a newer run starts for the same environment, an older active run can be cancelled.

This reduces duplicate workflow execution and unnecessary artifacts.

## Current publishing behavior

### Staging

```text
Generate digest
→ Upload artifact
```

### Production

```text
Generate digest
→ Upload artifact
```

GitHub Pages and GitHub Releases are intentionally not enabled yet.

This keeps the first automation version focused on validating workflow reliability.

## Generated outputs

A successful workflow run produces:

```text
output/
├── raw_articles.json
├── source_report.json
├── ranked_articles.json
├── digest.md
└── digest.html
```

## Compatibility notes

- Minimum local Python version: 3.11.
- Recommended local Python version: 3.12.
- GitHub Actions uses Python 3.12.
- GitHub Actions uses `ubuntu-24.04`.
- The test suite is offline.
- Feed collection requires network access.
- Individual feed failures remain isolated.
- Generated output is not committed to Git.
- The repository default branch is `master`.

## Validation

Validate configuration locally:

```bash
python -m src.main --validate-only
```

Run all tests:

```bash
python -m pytest -q
```

Expected result:

```text
89 passed
```

Run the complete local pipeline:

```bash
python -m src.main
```

Push changes to the repository:

```bash
git push origin master
```

Run the workflow manually:

```text
Repository
→ Actions
→ Generate Daily Tech Brief
→ Run workflow
→ staging
```

Confirm that the workflow produces an artifact containing all five output files.

## Acceptance criteria

Version 0.5.0 is complete when:

- local configuration validation succeeds;
- all 89 tests pass;
- the workflow is visible in the GitHub Actions tab;
- a staging workflow run succeeds;
- a production workflow run succeeds;
- the workflow uses Python 3.12;
- the workflow uses `ubuntu-24.04`;
- all five output files are generated;
- the workflow artifact can be downloaded from the web interface;
- the scheduled trigger resolves to production;
- staging and production use the same workflow;
- no GitHub Pages deployment occurs;
- no GitHub Release is created.

## Suggested commit

```bash
git add CHANGES-v0.5.0.md
git commit -m "Add v0.5.0 changelog"
git push origin master
```

## Suggested tag

After confirming both staging and production runs:

```bash
git tag -a v0.5.0 -m "Daily Tech Brief v0.5.0"
git push origin master
git push origin v0.5.0
```

## Next version

Version 0.6.0 will add GitHub Pages publishing:

- prepare a static site directory;
- publish the latest HTML digest;
- maintain dated HTML archives;
- generate a simple archive index;
- deploy only from production;
- keep staging artifact-only;
- add Pages deployment tests.
