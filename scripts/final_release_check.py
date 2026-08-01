from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class FinalReleaseCheckError(RuntimeError):
    """Raised when the final Daily Tech Brief validation fails."""


@dataclass(frozen=True)
class ReleaseArtifacts:
    public_epub: Path
    full_epub: Path
    site_epub: Path
    latest_site_epub: Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the final Daily Tech Brief release gate: tests, "
            "generation, verification, reports, and EPUB publication checks."
        )
    )
    parser.add_argument(
        "--skip-tests",
        action="store_true",
        help="Skip the full pytest suite.",
    )
    parser.add_argument(
        "--skip-generate",
        action="store_true",
        help="Reuse existing output and site artifacts.",
    )
    return parser


def run_command(
    command: Sequence[str],
    *,
    project_root: Path,
) -> None:
    printable = " ".join(command)
    print(f"\n>>> {printable}")

    completed = subprocess.run(
        list(command),
        cwd=project_root,
        check=False,
    )

    if completed.returncode != 0:
        raise FinalReleaseCheckError(
            f"Command failed with exit code "
            f"{completed.returncode}: {printable}"
        )


def validate_release_artifacts(
    project_root: Path,
) -> ReleaseArtifacts:
    output_dir = project_root / "output"
    site_dir = project_root / "site"

    artifacts = ReleaseArtifacts(
        public_epub=output_dir / "digest.epub",
        full_epub=output_dir / "digest-full.epub",
        site_epub=site_dir / "digest.epub",
        latest_site_epub=site_dir / "latest" / "digest.epub",
    )

    for path in (
        artifacts.public_epub,
        artifacts.full_epub,
        artifacts.site_epub,
        artifacts.latest_site_epub,
    ):
        _require_non_empty_file(path)
        _validate_epub_archive(path)

    public_digest = _sha256(artifacts.public_epub)

    for public_copy in (
        artifacts.site_epub,
        artifacts.latest_site_epub,
    ):
        if _sha256(public_copy) != public_digest:
            raise FinalReleaseCheckError(
                "Public EPUB copy does not match "
                f"output/digest.epub: {public_copy}"
            )

    leaked_full_epubs = sorted(
        path
        for path in site_dir.rglob("digest-full.epub")
        if path.is_file()
    )
    if leaked_full_epubs:
        leaked = ", ".join(
            str(path.relative_to(project_root))
            for path in leaked_full_epubs
        )
        raise FinalReleaseCheckError(
            "Full-content EPUB leaked into the public site: "
            f"{leaked}"
        )

    return artifacts


def run_final_release_check(
    project_root: Path,
    *,
    skip_tests: bool = False,
    skip_generate: bool = False,
) -> ReleaseArtifacts:
    python = sys.executable

    if not skip_tests:
        run_command(
            (python, "-m", "pytest", "-q"),
            project_root=project_root,
        )

    if not skip_generate:
        run_command(
            (python, "-m", "src.main"),
            project_root=project_root,
        )

    run_command(
        (
            python,
            "scripts/verify_technical_learning.py",
        ),
        project_root=project_root,
    )
    run_command(
        (
            python,
            "scripts/report_content_enrichment.py",
            "--problems-only",
        ),
        project_root=project_root,
    )
    run_command(
        (
            python,
            "scripts/report_learning_coverage.py",
        ),
        project_root=project_root,
    )

    artifacts = validate_release_artifacts(project_root)

    print("\nFinal Daily Tech Brief release check passed")
    print(
        "- Public EPUB:        "
        f"{artifacts.public_epub.relative_to(project_root)}"
    )
    print(
        "- Full EPUB artifact: "
        f"{artifacts.full_epub.relative_to(project_root)}"
    )
    print(
        "- Public site copy:   "
        f"{artifacts.site_epub.relative_to(project_root)}"
    )
    print(
        "- Latest site copy:   "
        f"{artifacts.latest_site_epub.relative_to(project_root)}"
    )
    print("- Full EPUB in site:  none")

    return artifacts


def _require_non_empty_file(path: Path) -> None:
    if not path.is_file():
        raise FinalReleaseCheckError(
            f"Required artifact was not found: {path}"
        )

    if path.stat().st_size <= 0:
        raise FinalReleaseCheckError(
            f"Required artifact is empty: {path}"
        )


def _validate_epub_archive(path: Path) -> None:
    if not zipfile.is_zipfile(path):
        raise FinalReleaseCheckError(
            f"EPUB is not a valid ZIP archive: {path}"
        )

    try:
        with zipfile.ZipFile(path) as archive:
            bad_member = archive.testzip()
            names = set(archive.namelist())
    except (OSError, zipfile.BadZipFile) as exc:
        raise FinalReleaseCheckError(
            f"Unable to inspect EPUB {path}: {exc}"
        ) from exc

    if bad_member is not None:
        raise FinalReleaseCheckError(
            f"EPUB contains a corrupt member: "
            f"{path}::{bad_member}"
        )

    required_members = {
        "mimetype",
        "META-INF/container.xml",
    }
    missing_members = sorted(required_members - names)
    if missing_members:
        raise FinalReleaseCheckError(
            f"EPUB is missing required members "
            f"{missing_members}: {path}"
        )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(
            lambda: handle.read(1024 * 1024),
            b"",
        ):
            digest.update(chunk)

    return digest.hexdigest()


def main(
    argv: list[str] | None = None,
) -> int:
    args = build_parser().parse_args(argv)

    try:
        run_final_release_check(
            PROJECT_ROOT,
            skip_tests=args.skip_tests,
            skip_generate=args.skip_generate,
        )
    except FinalReleaseCheckError as exc:
        print(
            f"\nFinal release check failed: {exc}",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
