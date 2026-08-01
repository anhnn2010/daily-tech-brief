from __future__ import annotations

import importlib.util
import sys
import zipfile
from pathlib import Path

import pytest


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "final_release_check.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "final_release_check",
        SCRIPT_PATH,
    )
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_epub(
    path: Path,
    *,
    marker: str,
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "mimetype",
            "application/epub+zip",
        )
        archive.writestr(
            "META-INF/container.xml",
            "<container/>",
        )
        archive.writestr(
            "EPUB/content.xhtml",
            f"<html><body>{marker}</body></html>",
        )


def _prepare_valid_artifacts(
    root: Path,
) -> None:
    public_epub = root / "output" / "digest.epub"
    full_epub = root / "output" / "digest-full.epub"

    _write_epub(
        public_epub,
        marker="summary",
    )
    _write_epub(
        full_epub,
        marker="full",
    )

    site_epub = root / "site" / "digest.epub"
    latest_epub = (
        root
        / "site"
        / "latest"
        / "digest.epub"
    )

    site_epub.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    latest_epub.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    site_epub.write_bytes(
        public_epub.read_bytes()
    )
    latest_epub.write_bytes(
        public_epub.read_bytes()
    )


def test_validates_public_and_private_epubs(
    tmp_path: Path,
) -> None:
    module = _load_module()
    _prepare_valid_artifacts(tmp_path)

    artifacts = module.validate_release_artifacts(
        tmp_path
    )

    assert (
        artifacts.public_epub
        == tmp_path / "output" / "digest.epub"
    )
    assert (
        artifacts.full_epub
        == tmp_path
        / "output"
        / "digest-full.epub"
    )


def test_rejects_full_epub_in_public_site(
    tmp_path: Path,
) -> None:
    module = _load_module()
    _prepare_valid_artifacts(tmp_path)

    leaked = (
        tmp_path
        / "site"
        / "archive"
        / "digest-full.epub"
    )
    leaked.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    leaked.write_bytes(
        (
            tmp_path
            / "output"
            / "digest-full.epub"
        ).read_bytes()
    )

    with pytest.raises(
        module.FinalReleaseCheckError,
        match="leaked into the public site",
    ):
        module.validate_release_artifacts(
            tmp_path
        )


def test_rejects_mismatched_public_copy(
    tmp_path: Path,
) -> None:
    module = _load_module()
    _prepare_valid_artifacts(tmp_path)

    _write_epub(
        tmp_path
        / "site"
        / "latest"
        / "digest.epub",
        marker="different",
    )

    with pytest.raises(
        module.FinalReleaseCheckError,
        match="does not match",
    ):
        module.validate_release_artifacts(
            tmp_path
        )


def test_runs_commands_in_release_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_module()
    _prepare_valid_artifacts(tmp_path)

    commands: list[tuple[str, ...]] = []

    def fake_run_command(
        command,
        *,
        project_root,
    ) -> None:
        assert project_root == tmp_path
        commands.append(tuple(command))

    monkeypatch.setattr(
        module,
        "run_command",
        fake_run_command,
    )

    module.run_final_release_check(
        tmp_path
    )

    assert commands[0][1:] == (
        "-m",
        "pytest",
        "-q",
    )
    assert commands[1][1:] == (
        "-m",
        "src.main",
    )
    assert commands[2][1:] == (
        "scripts/verify_technical_learning.py",
    )
    assert commands[3][1:] == (
        "scripts/report_content_enrichment.py",
        "--problems-only",
    )
    assert commands[4][1:] == (
        "scripts/report_learning_coverage.py",
    )


def test_skip_flags_omit_tests_and_generation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_module()
    _prepare_valid_artifacts(tmp_path)

    commands: list[tuple[str, ...]] = []

    monkeypatch.setattr(
        module,
        "run_command",
        lambda command, *, project_root: commands.append(
            tuple(command)
        ),
    )

    module.run_final_release_check(
        tmp_path,
        skip_tests=True,
        skip_generate=True,
    )

    assert all(
        "pytest" not in command
        for command in commands
    )
    assert all(
        "src.main" not in command
        for command in commands
    )
