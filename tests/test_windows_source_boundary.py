from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from autoform_cli import _directory_binding as directory_binding_module
from autoform_cli.__main__ import main
from autoform_cli._tree_snapshot import descriptor_capture_supported
from autoform_cli.lean import index_project, snapshot_project_sources
from autoform_cli.render import PUBLICATION_MANIFEST


@pytest.mark.skipif(os.name != "nt", reason="Windows capability boundary")
@pytest.mark.parametrize("capture", [snapshot_project_sources, index_project])
def test_windows_source_inspection_fails_closed_without_descriptor_traversal(
    tmp_path: Path,
    capture,
) -> None:
    (tmp_path / "A.lean").write_text(
        "theorem notReadUnsafely : True := trivial\n",
        encoding="utf-8",
    )

    with pytest.raises(OSError, match="safe directory traversal is unavailable"):
        capture(tmp_path)


_SKIPPED_LINKS = (
    "warning: code links were skipped because this platform cannot capture Lean "
    "sources safely (directory-descriptor traversal is unavailable); "
    "render on Linux or macOS to link declarations"
)


def _project(tmp_path: Path, *, lean: str | None = "Project.top") -> Path:
    project = tmp_path / "project"
    (project / "Project").mkdir(parents=True)
    (project / "Project" / "Basic.lean").write_text(
        "namespace Project\n\ntheorem top : True := trivial\n\nend Project\n",
        encoding="utf-8",
    )
    blueprint = project / "blueprint"
    roadmap = blueprint / "roadmap"
    roadmap.mkdir(parents=True)
    (blueprint / "coverage").mkdir()
    (blueprint / "README.md").write_text(
        "---\nkind: blueprint\n---\n\n# Overview\n\n- [Roadmap](roadmap/README.md)\n",
        encoding="utf-8",
    )
    (roadmap / "README.md").write_text(
        "---\n---\n\n# Roadmap\n\nThe main result.\n\n## Results\n\n- [Top](top.md)\n",
        encoding="utf-8",
    )
    (roadmap / "top.md").write_text(
        "---\ndeclaration: theorem\n"
        + (f"statement: formalized\nlean: {lean}\n" if lean is not None else "")
        + "---\n\n"
        "# Top\n\nThe main result.\n\n## Depends on\n\nThis node has no prerequisites.\n",
        encoding="utf-8",
    )
    (blueprint / "coverage" / "README.md").write_text(
        "# Coverage\n\n"
        "| Area | Coverage | Evidence |\n"
        "| --- | --- | --- |\n"
        "| Project scope | MAPPED | Source audit pending |\n",
        encoding="utf-8",
    )
    return project


def _published_text(output: Path) -> str:
    return "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(output.rglob("*.md"))
    )


def _commit_checkout(root: Path) -> str:
    def git(*arguments: str) -> str:
        return subprocess.run(
            ["git", *arguments], cwd=root, capture_output=True, text=True, check=True
        ).stdout.strip()

    git("init")
    git("remote", "add", "origin", "https://github.com/owner/repo.git")
    git("add", ".")
    git(
        "-c",
        "user.name=Autoform Tests",
        "-c",
        "user.email=autoform@example.invalid",
        "commit",
        "-m",
        "fixture",
    )
    return git("rev-parse", "HEAD")


def _without_descriptor_capture(monkeypatch: pytest.MonkeyPatch) -> None:
    # A no-op on Windows, where the capability is absent natively.
    monkeypatch.setattr(directory_binding_module, "DIRECTORY_BINDING_SUPPORTED", False)


@pytest.mark.parametrize("require_declarations", [False, True])
def test_render_without_descriptor_capture_publishes_without_code_links(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    require_declarations: bool,
) -> None:
    _without_descriptor_capture(monkeypatch)
    for variable in ("GITHUB_WORKSPACE", "GITHUB_REPOSITORY", "GITHUB_SHA"):
        monkeypatch.delenv(variable, raising=False)
    project = _project(tmp_path)
    commit = _commit_checkout(project)
    output = tmp_path / "site-src"

    def unreachable(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("the implicit Lean root must not be read without descriptor capture")

    monkeypatch.setattr("autoform_cli.render.snapshot_project_sources", unreachable)
    arguments = ["render", str(project / "blueprint"), "--output", str(output)]
    if require_declarations:
        arguments.append("--require-declarations")

    # The second render replaces the first site.
    for _ in range(2):
        status = main(arguments)
        stdout = capsys.readouterr().out
        assert status == (1 if require_declarations else 0)
        assert [line for line in stdout.splitlines() if line.startswith("warning:")] == [_SKIPPED_LINKS]
    assert "0 code links" in stdout
    published = _published_text(output)
    assert "<code>Project.top</code>" in published
    assert "not found in the Lean sources" not in published
    # Links to the Markdown sources still pin the verified commit.
    assert json.loads((output / PUBLICATION_MANIFEST).read_text(encoding="utf-8"))["git_ref"] == commit
    assert f"https://github.com/owner/repo/blob/{commit}/blueprint/roadmap/top.md" in published


@pytest.mark.parametrize("require_declarations", [False, True])
def test_render_without_descriptor_capture_is_quiet_when_no_declaration_is_named(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    require_declarations: bool,
) -> None:
    _without_descriptor_capture(monkeypatch)
    project = _project(tmp_path, lean=None)
    output = tmp_path / "site-src"
    arguments = ["render", str(project / "blueprint"), "--output", str(output)]
    if require_declarations:
        arguments.append("--require-declarations")

    status = main(arguments)

    stdout = capsys.readouterr().out
    assert status == 0
    assert "warning:" not in stdout
    assert json.loads((output / PUBLICATION_MANIFEST).read_text(encoding="utf-8"))["complete"]


def test_render_explicit_lean_root_fails_closed_without_descriptor_capture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _without_descriptor_capture(monkeypatch)
    project = _project(tmp_path)
    output = tmp_path / "site-src"

    status = main(
        ["render", str(project / "blueprint"), "--output", str(output), "--lean-root", str(project)]
    )

    assert status == 1
    assert capsys.readouterr().out.splitlines() == [
        "error: Lean sources could not be indexed: "
        "safe directory traversal is unavailable on this platform"
    ]
    assert not output.exists()


def test_render_with_descriptor_capture_still_links_the_implicit_root(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    if not descriptor_capture_supported():
        pytest.skip("directory descriptor capture is unavailable")
    project = _project(tmp_path)
    output = tmp_path / "site-src"

    status = main(
        ["render", str(project / "blueprint"), "--output", str(output), "--require-declarations"]
    )

    stdout = capsys.readouterr().out
    assert status == 0
    assert "warning:" not in stdout
    assert "1 code links" in stdout
    assert "Project/Basic.lean" in _published_text(output)
