# Daily Tech Brief v0.6.0

## Summary

Version 0.6.0 adds static-site generation and GitHub Pages publishing to Daily Tech Brief.

The complete production flow is now:

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
Static site generation
    ↓
Production archive restoration
    ↓
GitHub Pages deployment
```

## Added

### Static site builder

Added:

```text
src/publishing/site_builder.py
tests/test_site_builder.py
```

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

Capabilities:

- Publish the latest digest at the site root.
- Publish the latest digest under `/latest/`.
- Create dated archive editions.
- Calculate archive dates using `Asia/Ho_Chi_Minh`.
- Preserve previous archive entries.
- Replace an existing edition for the same local date.
- Remove stale files from a replaced same-day archive directory.
- Sort archive entries newest first.
- Generate both HTML and JSON archive indexes.
- Generate site metadata.
- Add `.nojekyll`.
- Use atomic file writes.
- Avoid symbolic and hard links.
- Continue when optional Markdown or source-report files are absent.

### Site publishing integration test

Added:

```text
tests/test_site_pipeline.py
```

The test verifies the complete local publishing flow:

```text
Collection result
→ output JSON
→ ranking
→ Markdown
→ HTML
→ site/
→ archive/
```

It confirms:

- all data outputs are created;
- the site root is created;
- the latest edition is created;
- the dated archive is created;
- site metadata is correct;
- archive metadata is correct;
- article counts remain consistent;
- selected article content reaches the Pages-ready site.

### GitHub Pages deployment

Updated:

```text
.github/workflows/generate_digest.yml
```

Production now:

```text
Restore previous production site artifact
→ Generate the current digest
→ Merge the current edition into the archive
→ Upload data artifact
→ Upload site artifact
→ Upload Pages artifact
→ Deploy GitHub Pages
```

GitHub Pages actions:

```text
actions/configure-pages@v6
actions/upload-pages-artifact@v4
actions/deploy-pages@v4
```

The deploy job uses:

```yaml
permissions:
  pages: write
  id-token: write
```

Deployment environment:

```text
github-pages
```

The public site URL is provided through:

```text
steps.deployment.outputs.page_url
```

### Production archive restoration

Before building a production site, the workflow searches for the newest unexpired artifact named like:

```text
daily-tech-brief-site-production-<run-number>-<run-attempt>
```

When found, the artifact is downloaded and extracted into:

```text
site/
```

The site builder then preserves old archive editions and adds or updates the current edition.

The first production run starts with an empty archive when no previous site artifact exists.

### Separate static site artifact

Each run now uploads two regular artifacts.

Data artifact:

```text
daily-tech-brief-<environment>-<run-number>-<run-attempt>
```

Site artifact:

```text
daily-tech-brief-site-<environment>-<run-number>-<run-attempt>
```

The site artifact includes hidden files so `.nojekyll` is retained.

Regular artifacts are retained for 14 days.

The temporary Pages artifact is retained for one day.

## Changed

### Main pipeline

Updated:

```text
src/main.py
```

The pipeline can now build the static site after digest rendering.

New configuration:

```yaml
runtime:
  site_dir: site

features:
  build_site: true
```

The command:

```bash
python -m src.main
```

now creates:

```text
output/
site/
```

The execution summary includes publishing metadata such as:

- site directory;
- root index path;
- archive date;
- archive manifest path;
- article count.

Publishing failures return exit code `2`.

### Project configuration

Updated:

```text
config/settings.yml
```

Changes:

```yaml
project:
  version: 0.6.0
```

```yaml
runtime:
  site_dir: site
  user_agent: DailyTechBrief/0.6.0
```

```yaml
features:
  build_site: true
```

### Git ignore rules

Updated:

```text
.gitignore
```

Generated directories are ignored:

```gitignore
output/
site/
```

### Workflow permissions and action versions

The workflow now separates job permissions.

Generation job:

```yaml
permissions:
  contents: read
  actions: read
```

Deployment job:

```yaml
permissions:
  pages: write
  id-token: write
```

The Pages configuration action was updated from:

```text
actions/configure-pages@v5
```

to:

```text
actions/configure-pages@v6
```

This aligns the workflow with the current Node 24 runtime.

### Workflow tests

Updated:

```text
tests/test_github_workflow.py
```

The workflow tests now verify:

- data artifact upload;
- site artifact upload;
- hidden-file inclusion;
- production archive restoration;
- production-only Pages artifact upload;
- production-only deployment;
- required Pages permissions;
- `github-pages` environment;
- current Pages action versions;
- deployment URL output.

### Documentation

Updated:

```text
README.md
```

The documentation now includes:

- site directory structure;
- local site usage;
- latest and archived URLs;
- production archive restoration;
- Pages setup;
- public-repository requirement for GitHub Free;
- mobile access;
- branch `master`;
- acceptance criteria;
- the EPUB and TTS roadmap.

## Staging behavior

Staging performs:

```text
Generate digest
→ Build static site
→ Upload data artifact
→ Upload site artifact
```

Staging does not:

- restore the production archive;
- upload a Pages artifact;
- deploy GitHub Pages;
- replace the public website.

## Production behavior

Production performs:

```text
Restore previous production site artifact
→ Generate digest
→ Build and merge static site
→ Upload data artifact
→ Upload site artifact
→ Upload GitHub Pages artifact
→ Deploy GitHub Pages
```

Scheduled runs always use production.

## GitHub Pages setup

For GitHub Free, the repository must be public.

Configure Pages through:

```text
Repository
→ Settings
→ Pages
→ Build and deployment
→ Source
→ GitHub Actions
```

The default project Pages URL normally follows:

```text
https://<username>.github.io/daily-tech-brief/
```

The site URL is also available from:

```text
Repository
→ Settings
→ Pages
```

and from the successful deployment job.

## Generated URLs

The deployed site provides:

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

## Compatibility notes

- Minimum supported Python version: 3.11.
- Recommended Python version: 3.12.
- GitHub Actions uses Python 3.12.
- GitHub Actions uses `ubuntu-24.04`.
- The repository default branch is `master`.
- The test suite is offline.
- Feed collection requires network access.
- Individual feed failures remain isolated.
- Generated `output/` and `site/` directories are not committed.
- GitHub Pages deployment requires Pages to be enabled once in repository settings.
- The public website is deployed only by production runs.

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
104 passed
```

Run the complete pipeline locally:

```bash
python -m src.main
```

Open the site:

```bash
xdg-open site/index.html
```

Open the archive:

```bash
xdg-open site/archive/index.html
```

Run staging:

```text
Actions
→ Generate Daily Tech Brief
→ Run workflow
→ Branch: master
→ Environment: staging
```

Run production:

```text
Actions
→ Generate Daily Tech Brief
→ Run workflow
→ Branch: master
→ Environment: production
```

## Acceptance criteria

Version 0.6.0 is complete when:

- configuration validation succeeds;
- all 104 tests pass;
- local execution creates `output/` and `site/`;
- the latest site page opens locally;
- the archive page opens locally;
- archive dates use `Asia/Ho_Chi_Minh`;
- staging uploads data and site artifacts;
- staging does not deploy Pages;
- production uploads data and site artifacts;
- production uploads a Pages artifact;
- production deploys through the `github-pages` environment;
- the public Pages URL loads the latest digest;
- a later production run preserves prior archive editions;
- a same-day production rerun replaces that day's edition without duplication.

## Suggested commit

```bash
git add CHANGES-v0.6.0.md
git commit -m "Add v0.6.0 changelog"
git push origin master
```

## Suggested tag

After confirming the public site and archive:

```bash
git tag -a v0.6.0 -m "Daily Tech Brief v0.6.0"
git push origin master
git push origin v0.6.0
```

## Next version

Version 0.7.0 will add EPUB and TTS support:

- generate `digest.epub`;
- add EPUB metadata;
- add EPUB navigation;
- create a TTS-friendly reading structure;
- avoid placing long URLs in spoken content;
- support Readest and KOReader;
- validate EPUB files;
- upload EPUB in workflow artifacts.
