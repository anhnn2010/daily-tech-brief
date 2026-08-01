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
    assert "Generate digest and static site" in workflow
    assert "run: python -m src.main" in workflow


def test_digest_workflow_supports_staging_and_production() -> None:
    workflow = read_workflow()

    assert "default: staging" in workflow
    assert "- staging" in workflow
    assert "- production" in workflow
    assert "environment:" in workflow
    assert 'target_environment="production"' in workflow
    assert "TARGET_ENVIRONMENT=${target_environment}" in workflow


def test_digest_workflow_uploads_output_and_site_artifacts() -> None:
    workflow = read_workflow()

    assert workflow.count("actions/upload-artifact@v4") == 2
    assert "path: output/" in workflow
    assert "path: site/" in workflow
    assert "daily-tech-brief-site-" in workflow
    assert "include-hidden-files: true" in workflow
    assert "retention-days: 14" in workflow


def test_production_restores_previous_site_archive() -> None:
    workflow = read_workflow()

    assert "Restore previous production site" in workflow
    assert "env.TARGET_ENVIRONMENT == 'production'" in workflow
    assert "daily-tech-brief-site-production-" in workflow
    assert "/actions/artifacts?per_page=100" in workflow
    assert "unzip -q" in workflow
    assert "find site/archive" in workflow


def test_workflow_verifies_epub_publication() -> None:
    workflow = read_workflow()

    assert "name: Verify EPUB publication" in workflow
    assert "test -s output/digest.epub" in workflow
    assert "test -s site/digest.epub" in workflow
    assert "test -s site/latest/digest.epub" in workflow
    assert "-path '*/digest.epub'" in workflow
    assert "-exec cmp -s output/digest.epub {} \\;" in workflow
    assert "cmp output/digest.epub site/digest.epub" in workflow
    assert "cmp output/digest.epub site/latest/digest.epub" in workflow
    assert 'grep -q \'href="digest.epub"\' site/index.html' in workflow
    assert "grep -q 'Download EPUB' site/index.html" in workflow


def test_epub_verification_runs_before_artifact_uploads() -> None:
    workflow = read_workflow()

    verify_position = workflow.index("- name: Verify EPUB publication")
    output_upload_position = workflow.index(
        "- name: Upload digest output artifact"
    )
    site_upload_position = workflow.index(
        "- name: Upload static site artifact"
    )
    pages_upload_position = workflow.index(
        "- name: Upload GitHub Pages artifact"
    )

    assert verify_position < output_upload_position
    assert verify_position < site_upload_position
    assert verify_position < pages_upload_position


def test_workflow_verifies_technical_learning_output() -> None:
    workflow = read_workflow()

    assert "name: Verify Technical Learning output" in workflow
    assert (
        "python scripts/verify_technical_learning.py"
        in workflow
    )
    assert "--expected-total 12" in workflow
    assert "--expected-learning 1" in workflow


def test_technical_learning_verification_runs_before_uploads() -> None:
    workflow = read_workflow()

    epub_verify_position = workflow.index(
        "- name: Verify EPUB publication"
    )
    learning_verify_position = workflow.index(
        "- name: Verify Technical Learning output"
    )
    output_upload_position = workflow.index(
        "- name: Upload digest output artifact"
    )
    site_upload_position = workflow.index(
        "- name: Upload static site artifact"
    )
    pages_upload_position = workflow.index(
        "- name: Upload GitHub Pages artifact"
    )
    deploy_job_position = workflow.index(
        "name: Deploy GitHub Pages"
    )

    assert epub_verify_position < learning_verify_position
    assert learning_verify_position < output_upload_position
    assert learning_verify_position < site_upload_position
    assert learning_verify_position < pages_upload_position
    assert learning_verify_position < deploy_job_position


def test_workflow_publishes_full_content_job_summary() -> None:
    workflow = read_workflow()

    assert "name: Publish full-content report" in workflow
    assert "if: always()" in workflow
    assert "output/ranked_articles.json" in workflow
    assert "python scripts/report_content_enrichment.py" in workflow
    assert "--markdown" in workflow
    assert "--problems-only" in workflow
    assert '>> "${GITHUB_STEP_SUMMARY}"' in workflow


def test_full_content_summary_runs_after_verification_before_uploads() -> None:
    workflow = read_workflow()

    learning_verify_position = workflow.index(
        "- name: Verify Technical Learning output"
    )
    report_position = workflow.index(
        "- name: Publish full-content report"
    )
    output_upload_position = workflow.index(
        "- name: Upload digest output artifact"
    )
    site_upload_position = workflow.index(
        "- name: Upload static site artifact"
    )
    pages_upload_position = workflow.index(
        "- name: Upload GitHub Pages artifact"
    )

    assert learning_verify_position < report_position
    assert report_position < output_upload_position
    assert report_position < site_upload_position
    assert report_position < pages_upload_position


def test_full_content_summary_handles_missing_generation_output() -> None:
    workflow = read_workflow()

    assert "if [[ ! -s output/ranked_articles.json ]]" in workflow
    assert "Report unavailable because" in workflow
    assert "exit 0" in workflow


def test_pages_artifact_is_uploaded_only_for_production() -> None:
    workflow = read_workflow()

    assert "Upload GitHub Pages artifact" in workflow
    assert "actions/upload-pages-artifact@v4" in workflow
    assert "if: env.TARGET_ENVIRONMENT == 'production'" in workflow
    assert "path: site/" in workflow
    assert "retention-days: 1" in workflow


def test_pages_deploy_job_has_required_configuration() -> None:
    workflow = read_workflow()

    assert "name: Deploy GitHub Pages" in workflow
    assert (
        "if: needs.generate.outputs.target_environment == 'production'"
        in workflow
    )
    assert "pages: write" in workflow
    assert "id-token: write" in workflow
    assert "name: github-pages" in workflow
    assert "steps.deployment.outputs.page_url" in workflow
    assert "actions/configure-pages@v6" in workflow
    assert "actions/deploy-pages@v4" in workflow
    assert (
        "artifact_name: "
        "${{ needs.generate.outputs.pages_artifact_name }}"
        in workflow
    )
