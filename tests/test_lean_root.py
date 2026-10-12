"""Every command that takes a Lean root names why an unusable root was refused."""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from autoform_cli.__main__ import main

_MISSING = "Lean root does not exist or is not a directory"
_UNSEARCHABLE = "permission denied while resolving the Lean root"
_UNRESOLVABLE = "Lean root cannot be resolved"


def _blueprint(tmp_path: Path) -> Path:
    blueprint = tmp_path / "blueprint"
    roadmap = blueprint / "roadmap"
    coverage = blueprint / "coverage"
    roadmap.mkdir(parents=True)
    coverage.mkdir(parents=True)
    (roadmap / "result.md").write_text(
        "---\ndeclaration: theorem\nlean: Proj.result\n---\n\n"
        "# Result\n\nA precise statement.\n\n## Depends on\n\nNo prerequisites.\n",
        encoding="utf-8",
    )
    (coverage / "README.md").write_text(
        "# Coverage\n\n"
        "| Area | Coverage | Evidence |\n"
        "| --- | --- | --- |\n"
        "| Narrative | OUT | No formalization target |\n",
        encoding="utf-8",
    )
    return blueprint


@pytest.fixture
def unusable_root(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[tuple[Path, str]]:
    """Yield a Lean root that cannot be used and the reason it must be refused with."""

    kind = request.param
    if kind == "missing":
        yield tmp_path / "missing", _MISSING
    elif kind == "file":
        root = tmp_path / "file"
        root.write_text("", encoding="utf-8")
        yield root, _MISSING
    elif kind == "unknown-home":
        if os.name == "nt":
            pytest.skip("Windows expands ~name beside the current home directory")
        yield Path("~autoform-no-such-user/proj"), _UNRESOLVABLE
    elif kind == "loop":
        if os.name == "nt":
            pytest.skip("Windows reports a symbolic link loop by its own error code")
        root = tmp_path / "loop"
        try:
            root.symlink_to(root)
        except OSError:
            pytest.skip("symbolic links are unavailable")
        yield root, _UNRESOLVABLE
    else:
        if os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0):
            pytest.skip("search permission is not enforced here")
        locked = tmp_path / "locked"
        (locked / "proj").mkdir(parents=True)
        (locked / "proj" / "Proj.lean").write_text("theorem result : True := trivial\n", encoding="utf-8")
        locked.chmod(0)
        try:
            if os.access(locked, os.X_OK):
                pytest.skip("search permission is not enforced")
            yield locked / "proj", _UNSEARCHABLE
        finally:
            locked.chmod(0o755)


_EVERY_ROOT = pytest.mark.parametrize(
    "unusable_root", ["missing", "file", "unsearchable", "unknown-home", "loop"], indirect=True
)
# audit, search and work named a missing or non-directory root correctly before
# resolve_lean_root (tests/test_search.py and tests/test_work.py pin the
# missing case), so they are checked only for the roots they misreported.
_MISREPORTED_ROOT = pytest.mark.parametrize("unusable_root", ["unsearchable", "unknown-home", "loop"], indirect=True)


def _without_host_paths(text: str, tmp_path: Path) -> bool:
    return str(tmp_path) not in text and str(tmp_path.resolve()) not in text


@_EVERY_ROOT
def test_check_names_the_unusable_lean_root(
    tmp_path: Path, unusable_root: tuple[Path, str], capsys: pytest.CaptureFixture[str]
) -> None:
    root, reason = unusable_root
    blueprint = _blueprint(tmp_path)

    assert main(["check", str(blueprint), "--lean-root", str(root)]) == 1

    captured = capsys.readouterr()
    assert captured.out == f"error: Lean sources could not be indexed: {reason}\n"
    assert _without_host_paths(captured.out + captured.err, tmp_path)


@_MISREPORTED_ROOT
def test_audit_names_the_unusable_lean_root(
    tmp_path: Path, unusable_root: tuple[Path, str], capsys: pytest.CaptureFixture[str]
) -> None:
    root, reason = unusable_root
    blueprint = _blueprint(tmp_path)

    assert main(["audit", str(blueprint), "--lean-root", str(root), "--json"]) == 1

    captured = capsys.readouterr()
    findings = json.loads(captured.out)["findings"]
    assert {"article_path": ".", "code": "invalid-lean-root", "reason": reason} in findings
    assert _without_host_paths(captured.out + captured.err, tmp_path)


@_EVERY_ROOT
@pytest.mark.parametrize("ref", [None, "main"])
def test_render_names_the_unusable_lean_root(
    tmp_path: Path,
    unusable_root: tuple[Path, str],
    capsys: pytest.CaptureFixture[str],
    ref: str | None,
) -> None:
    root, reason = unusable_root
    blueprint = _blueprint(tmp_path)
    output = tmp_path / "site"
    arguments = ["render", str(blueprint), "-o", str(output), "--lean-root", str(root)]
    if ref is not None:
        arguments += ["--repository-url", "https://github.com/owner/repo", "--ref", ref]

    assert main(arguments) == 1

    captured = capsys.readouterr()
    assert captured.out == f"error: Lean sources could not be indexed: {reason}\n"
    assert _without_host_paths(captured.out + captured.err, tmp_path)
    assert not output.exists()


@_MISREPORTED_ROOT
def test_search_names_the_unusable_lean_root(
    tmp_path: Path, unusable_root: tuple[Path, str], capsys: pytest.CaptureFixture[str]
) -> None:
    root, reason = unusable_root
    blueprint = _blueprint(tmp_path)

    assert main(["search", str(blueprint), "result", "--lean-root", str(root)]) == 2

    captured = capsys.readouterr()
    assert captured.err == f"error: {reason}\n"
    assert _without_host_paths(captured.out + captured.err, tmp_path)


@_MISREPORTED_ROOT
def test_work_names_the_unusable_lean_root(
    tmp_path: Path, unusable_root: tuple[Path, str], capsys: pytest.CaptureFixture[str]
) -> None:
    root, reason = unusable_root
    blueprint = _blueprint(tmp_path)

    assert main(["work", "list", str(blueprint), "--lean-root", str(root)]) == 2

    captured = capsys.readouterr()
    assert captured.err == f"error: {reason}\n"
    assert _without_host_paths(captured.out + captured.err, tmp_path)


@_EVERY_ROOT
def test_skeleton_checks_the_lean_root_before_the_lake_files(
    tmp_path: Path, unusable_root: tuple[Path, str], capsys: pytest.CaptureFixture[str]
) -> None:
    root, reason = unusable_root
    blueprint = _blueprint(tmp_path)

    assert main(["skeleton", str(blueprint), "--lean-root", str(root)]) == 2

    captured = capsys.readouterr()
    assert captured.err == f"error: {reason}\n"
    assert _without_host_paths(captured.out + captured.err, tmp_path)


@_EVERY_ROOT
def test_impact_checks_the_lean_root_before_the_lake_files(
    tmp_path: Path, unusable_root: tuple[Path, str], capsys: pytest.CaptureFixture[str]
) -> None:
    root, reason = unusable_root
    blueprint = _blueprint(tmp_path)

    assert main(["work", "impact", "result", str(blueprint), "--lean-root", str(root)]) == 2

    captured = capsys.readouterr()
    assert captured.err == f"error: {reason}\n"
    assert _without_host_paths(captured.out + captured.err, tmp_path)


@_EVERY_ROOT
def test_doctor_reports_why_the_lean_root_is_unusable(
    tmp_path: Path, unusable_root: tuple[Path, str], capsys: pytest.CaptureFixture[str]
) -> None:
    root, reason = unusable_root
    blueprint = _blueprint(tmp_path)

    assert main(["doctor", str(blueprint), "--lean-root", str(root), "--json"]) == 1

    captured = capsys.readouterr()
    checks = {check["name"]: check for check in json.loads(captured.out)["checks"]}
    assert checks["lean targets"] == {"detail": reason, "name": "lean targets", "ok": False}
    assert checks["runtime"]["ok"]
    assert _without_host_paths(captured.out + captured.err, tmp_path)
