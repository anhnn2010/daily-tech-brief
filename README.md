# Daily Tech Brief

Version **0.1.0** establishes the project configuration and validates the first source registry.
It intentionally does not fetch feeds yet. Feed collection starts in v0.2.0.

## Included in v0.1.0

- Project structure
- `sources.yml` with 17 official sources
- Personal category weights and keyword interests
- Runtime settings and feature flags
- Configuration loader and validation
- Human-readable and JSON summaries
- Unit tests

## Project structure

```text
daily-tech-brief-v0.1.0/
├── config/
│   ├── profile.yml
│   ├── settings.yml
│   └── sources.yml
├── output/
├── src/
│   ├── __init__.py
│   ├── config_loader.py
│   ├── main.py
│   └── models.py
├── tests/
│   └── test_config.py
├── .gitignore
├── README.md
└── requirements.txt
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

## Validate the configuration

```bash
python -m src.main
```

JSON output:

```bash
python -m src.main --json
```

## Run tests

```bash
pytest -q
```

## v0.1.0 acceptance criteria

- All three YAML files load successfully.
- Every source has the required fields.
- Source IDs are unique.
- URLs have valid HTTP or HTTPS structure.
- Priorities are between 1 and 10.
- Every source category exists in `profile.yml`.
- The project prints a source summary without fetching the network.

## Next version

**v0.2.0 — RSS/Atom Collector**

- Fetch feeds with timeouts and a user agent.
- Normalize RSS and Atom entries.
- Continue when an individual source fails.
- Write `raw_articles.json` and `source_report.json`.
