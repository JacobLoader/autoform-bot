"""The release version: one number that every manifest and the lock carry."""

from __future__ import annotations

import importlib.metadata
import json
from pathlib import Path

import pytest
import tomli

from autoform_cli.__main__ import main


def _project_version(repo_root: Path) -> tuple[str, str]:
    project = tomli.loads((repo_root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    return project["name"], project["version"]


def test_every_manifest_and_the_lock_name_the_project_version(repo_root: Path) -> None:
    """pyproject.toml sets the version, and the lock, the Claude and Muse
    manifests, and the base of Codex's cachebuster version must name the same
    one, or a release installs a plugin that reports another."""

    name, version = _project_version(repo_root)
    lock = tomli.loads((repo_root / "uv.lock").read_text(encoding="utf-8"))
    manifests = {
        "uv.lock": next(package["version"] for package in lock["package"] if package["name"] == name),
        ".claude-plugin/plugin.json": json.loads((repo_root / ".claude-plugin/plugin.json").read_text())["version"],
        ".muse-plugin/plugin.json": json.loads((repo_root / ".muse-plugin/plugin.json").read_text())["version"],
        ".codex-plugin/plugin.json": json.loads((repo_root / ".codex-plugin/plugin.json").read_text())["version"].split(
            "+", 1
        )[0],
    }

    assert manifests == dict.fromkeys(manifests, version)


def test_version_names_the_installed_release(repo_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exited:
        main(["--version"])

    assert exited.value.code == 0
    try:
        installed = importlib.metadata.version("autoform")
    except importlib.metadata.PackageNotFoundError:
        pytest.skip("autoform is not installed in this environment")
    assert capsys.readouterr().out == f"autoform {installed}\n"
    assert installed == _project_version(repo_root)[1]
