from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = (
    PROJECT_ROOT
    / ".github"
    / "workflows"
    / "generate_digest.yml"
)


def read_workflow() -> str:
    assert WORKFLOW_PATH.exists(), (
        f"Workflow file not found: {WORKFLOW_PATH}"
    )
    return WORKFLOW_PATH.read_text(encoding="utf-8")


def test_digest_workflow_has_manual_and_scheduled_triggers() -> None:
    workflow = read_workflow()

    assert "workflow_dispatch:" in workflow
    assert "schedule:" in workflow
    assert 'cron: "30 23 * * *"' in workflow


def test_digest_workflow_uses_expected_runtime() -> None:
    workflow = read_workflow()

    assert "runs-on: ubuntu-24.04" in workflow
    assert "actions/checkout@v6" in workflow
    assert "actions/setup-python@v6" in workflow
    assert 'python-version: "3.12"' in workflow


def test_digest_workflow_runs_validation_tests_and_generation() -> None:
    workflow = read_workflow()

    assert "python -m src.main --validate-only" in workflow
    assert "python -m pytest -q" in workflow
    assert "python -m src.main" in workflow


def test_digest_workflow_supports_staging_and_production() -> None:
    workflow = read_workflow()

    assert "default: staging" in workflow
    assert "- staging" in workflow
    assert "- production" in workflow
    assert "environment:" in workflow
    assert 'target_environment="production"' in workflow


def test_digest_workflow_uploads_generated_output() -> None:
    workflow = read_workflow()

    assert "actions/upload-artifact@v4" in workflow
    assert "path: output/" in workflow
    assert "if-no-files-found: warn" in workflow
    assert "retention-days: 14" in workflow
