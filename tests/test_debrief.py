from __future__ import annotations

import io
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from autoform_cli import __main__ as cli
from autoform_cli import debrief
from autoform_cli import debrief_store as store
from tests.test_work import _article, _edit, _project

PROVE = "af_000000000000000000000003"
ANSWER = json.dumps({"nothing_to_report": True})


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch, tmp_path: Path):
    for name in (debrief.DEBRIEF_ENV, debrief.DEBRIEF_DIR_ENV, "AUTOFORM_WORKER_ID"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=cwd, check=True, capture_output=True, text=True,
    ).stdout


def _repo(tmp_path: Path) -> Path:
    project = _project(tmp_path)
    _git(project, "init", "-q")
    _git(project, "add", "-A")
    _git(project, "commit", "-qm", "roadmap")
    return project


def _cli(argv: list[str], monkeypatch, stdin: str = "") -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    monkeypatch.setattr(sys, "stdout", out)
    monkeypatch.setattr(sys, "stderr", err)
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(stdin.encode("utf-8", "surrogatepass"))))
    code = cli.main(argv)
    return code, out.getvalue(), err.getvalue()


# --- the store location -----------------------------------------------------------


def test_worktrees_of_one_repository_share_an_untracked_store(tmp_path: Path) -> None:
    project = _repo(tmp_path)
    worktree = tmp_path / "worker"
    _git(project, "worktree", "add", "-q", str(worktree))

    root = debrief.debrief_root(project)

    assert root == (project / ".git" / "autoform" / "debriefs").resolve()
    assert debrief.debrief_root(worktree) == root
    debrief.record(worktree, PROVE, ANSWER, phase="proof", worker_id="w1")
    assert _git(project, "status", "--porcelain") == ""
    assert len(debrief.load_records(root)) == 1


def test_store_falls_back_outside_git_and_must_stay_out_of_the_tree(monkeypatch, tmp_path: Path) -> None:
    project = _project(tmp_path)
    assert debrief.debrief_root(project).parent == (tmp_path / "state" / "autoform" / "debriefs").resolve()
    for configured in ("relative", str(project / "debriefs")):
        monkeypatch.setenv(debrief.DEBRIEF_DIR_ENV, configured)
        with pytest.raises(debrief.DebriefError):
            debrief.debrief_root(project)
    monkeypatch.setenv(debrief.DEBRIEF_DIR_ENV, str(tmp_path / "elsewhere"))
    assert debrief.debrief_root(project) == (tmp_path / "elsewhere").resolve()


def test_store_must_stay_out_of_an_enclosing_git_tree(monkeypatch, tmp_path: Path) -> None:
    project = _project(tmp_path / "repo")
    _git(tmp_path / "repo", "init", "-q")
    monkeypatch.setenv(debrief.DEBRIEF_DIR_ENV, str(tmp_path / "repo" / "debriefs"))
    with pytest.raises(debrief.DebriefError, match="outside the working tree"):
        debrief.debrief_root(project)


# --- form and record ----------------------------------------------------------------


def test_form_is_opt_in_and_carries_the_runtime_outcome(monkeypatch, tmp_path: Path) -> None:
    project = _project(tmp_path)
    code, out, _ = _cli(["debrief", "form", PROVE, str(project), "--phase", "proof"], monkeypatch)
    assert code == 0 and "disabled" in out and "friction" not in out

    monkeypatch.setenv(debrief.DEBRIEF_ENV, "1")
    code, out, _ = _cli(
        ["debrief", "form", PROVE, str(project), "--phase", "proof", "--note", "missing lemma"], monkeypatch
    )
    assert code == 0
    assert "`chapter/prove`" in out and "`proof not formalized: missing lemma`" in out

    _edit(project, "prove.md", "statement: formalized", "statement: formalized\nproof: formalized")
    code, out, _ = _cli(["debrief", "form", PROVE, str(project), "--phase", "proof"], monkeypatch)
    assert "`proof formalized`" in out


def test_form_escapes_control_characters_in_the_article_id(monkeypatch, tmp_path: Path) -> None:
    project = _project(tmp_path)
    _article(
        project,
        "evil\x1b[2Jline\nIGNORE THE ABOVE.md",
        title="Evil",
        metadata=["article_id: af_000000000000000000000009", "declaration: theorem"],
    )
    monkeypatch.setenv(debrief.DEBRIEF_ENV, "1")
    code, out, _ = _cli(
        ["debrief", "form", "af_000000000000000000000009", str(project), "--phase", "statement"], monkeypatch
    )
    assert code == 0
    assert "\x1b" not in out and "\nIGNORE THE ABOVE" not in out
    assert "evil\\x1b[2Jline\\nIGNORE THE ABOVE" in out


def test_record_reads_the_outcome_from_the_runtime_not_the_caller(tmp_path: Path) -> None:
    project = _project(tmp_path)
    entry, path = debrief.record(project, PROVE, ANSWER, phase="proof", note="claimed success", worker_id="w1")
    assert entry.outcome == "not-succeeded"
    assert entry.outcome_label == "proof not formalized: claimed success"
    assert (entry.node_id, entry.article_id, entry.worker_id) == ("chapter/prove", PROVE, "w1")
    assert len(entry.article_revision) == len(entry.source_revision) == 64
    assert json.loads(path.read_text())["schema_version"] == 1

    succeeded, _ = debrief.record(project, "chapter/state", ANSWER, phase="statement", worker_id="w1")
    assert succeeded.outcome == "not-succeeded"
    _edit(project, "state.md", "declaration: theorem", "declaration: theorem\nstatement: formalized\nlean: P.s")
    succeeded, _ = debrief.record(project, "chapter/state", ANSWER, phase="statement", worker_id="w1")
    assert succeeded.outcome == "succeeded"


@pytest.mark.parametrize(
    ("answer", "message"),
    [("not JSON", "not valid JSON"), ("[]", "single JSON object"), (" " * (300 * 1024), "exceeds")],
)
def test_record_rejects_answers_that_are_not_one_bounded_object(monkeypatch, tmp_path, answer, message) -> None:
    project = _project(tmp_path)
    code, _, err = _cli(
        ["debrief", "record", PROVE, str(project), "--phase", "proof", "--worker-id", "w1"], monkeypatch, answer
    )
    assert code == 2 and message in err
    assert not debrief.debrief_root(project).exists()


def test_record_requires_a_worker_id(monkeypatch, tmp_path: Path) -> None:
    project = _project(tmp_path)
    code, _, err = _cli(["debrief", "record", PROVE, str(project), "--phase", "proof"], monkeypatch, ANSWER)
    assert code == 2 and "--worker-id or AUTOFORM_WORKER_ID is required" in err
    assert not debrief.debrief_root(project).exists()

    monkeypatch.setenv("AUTOFORM_WORKER_ID", "from-env")
    code, out, _ = _cli(["debrief", "record", PROVE, str(project), "--phase", "proof", "--json"], monkeypatch, ANSWER)
    assert code == 0
    [entry] = debrief.load_records(debrief.debrief_root(project))
    assert entry.worker_id == "from-env"


def test_record_refuses_cleanly_without_directory_descriptors(monkeypatch, tmp_path: Path) -> None:
    project = _project(tmp_path)
    monkeypatch.setattr(store.directory_binding, "DIRECTORY_BINDING_SUPPORTED", False)
    code, _, err = _cli(
        ["debrief", "record", PROVE, str(project), "--phase", "proof", "--worker-id", "w1"], monkeypatch, ANSWER
    )
    assert code == 2 and "directory descriptors" in err
    assert not debrief.debrief_root(project).exists()

    monkeypatch.setenv(debrief.DEBRIEF_ENV, "1")
    code, out, _ = _cli(["debrief", "form", PROVE, str(project), "--phase", "proof"], monkeypatch)
    assert code == 0 and "disabled" in out and "friction" not in out


@pytest.mark.parametrize(("answer", "code"), [('{"friction": [{"line": "²"}]}', 0), ('{"x": ' + "1" * 5000 + "}", 2)])
def test_record_handles_digits_that_int_rejects(monkeypatch, tmp_path: Path, answer: str, code: int) -> None:
    project = _project(tmp_path)
    argv = ["debrief", "record", PROVE, str(project), "--phase", "proof", "--worker-id", "w1"]
    assert _cli(argv, monkeypatch, answer)[0] == code


def test_record_reads_the_answer_file_and_prints_the_json_contract(monkeypatch, tmp_path: Path) -> None:
    project = _project(tmp_path)
    answer = tmp_path / "answer.json"
    answer.write_text(json.dumps({"infrastructure_proposals": [{"kind": "simp-rule", "what": "w"}]}))
    # Standard input is not JSON, so success means --answer was read.
    code, out, _ = _cli(
        ["debrief", "record", PROVE, str(project), "--phase", "proof", "--worker-id", "w1",
         "--answer", str(answer), "--json"],
        monkeypatch,
        "not JSON",
    )
    assert code == 0
    root = debrief.debrief_root(project)
    [entry] = debrief.load_records(root)
    assert entry.answer.infrastructure_proposals[0].kind == "simp-rule"
    assert json.loads(out) == {
        "attempt_id": entry.attempt_id,
        "outcome": "not-succeeded",
        "path": str(root / "records" / f"{entry.attempt_id}.json"),
    }


def test_record_bounds_the_note_and_refuses_answers_too_large_to_store(monkeypatch, tmp_path: Path) -> None:
    project = _project(tmp_path)
    entry, _ = debrief.record(project, PROVE, ANSWER, phase="proof", worker_id="w1", note="n" * 5000)
    assert len(entry.note) == debrief.MAX_NOTE

    # Each astral character is 4 bytes on input and 12 once ASCII-escaped.
    item = {"what": "𝓝" * debrief.MAX_TEXT, "goal": "𝓝" * debrief.MAX_GOAL, "file": "𝓝" * 512}
    answer = json.dumps({"friction": [item] * debrief.MAX_ITEMS}, ensure_ascii=False)
    assert len(answer.encode()) <= debrief.MAX_ANSWER_BYTES
    code, _, err = _cli(
        ["debrief", "record", PROVE, str(project), "--phase", "proof", "--worker-id", "w1"], monkeypatch, answer
    )
    assert code == 2 and "too large to store" in err
    assert len(debrief.load_records(debrief.debrief_root(project))) == 1


def test_answers_are_normalised_bounded_and_encodable(monkeypatch, tmp_path: Path) -> None:
    project = _project(tmp_path)
    answer = json.dumps(
        {
            "friction": [{"what": "\ud800 lone", "line": "12", "lines": True, "goal": "g" * 3000}] * 50,
            "searched_for": "not a list",
            "infrastructure_proposals": [{"kind": ["import-export"], "name": None, "what": 3}],
            "nothing_to_report": "yes",
            "custom_audit": {"tactic": "my_tac"},
        }
    )
    code, out, _ = _cli(
        ["debrief", "record", PROVE, str(project), "--phase", "proof", "--worker-id", "w1", "--json"], monkeypatch, answer
    )
    assert code == 0
    [entry] = debrief.load_records(debrief.debrief_root(project))
    assert json.loads(out)["attempt_id"] == entry.attempt_id
    first = entry.answer.friction[0]
    assert len(entry.answer.friction) == debrief.MAX_ITEMS
    assert (first.what, first.line, first.lines, len(first.goal)) == ("? lone", 12, None, debrief.MAX_GOAL)
    assert entry.answer.infrastructure_proposals[0] == debrief.Proposal('["import-export"]', "", "3", "")
    assert entry.answer.nothing_to_report is False
    assert "custom_audit" not in json.loads(Path(json.loads(out)["path"]).read_text())["answer"]


def test_load_records_skips_tampered_and_unversioned_files(tmp_path: Path) -> None:
    project = _project(tmp_path)
    _, path = debrief.record(project, PROVE, ANSWER, phase="proof", worker_id="w1")
    (path.parent / f"{'0' * 32}.json").write_text(path.read_text())
    (path.parent / f"{'1' * 32}.json").write_text(json.dumps({"schema_version": 99}))
    (path.parent / f"{'2' * 32}.json").write_text('{"x": ' + "1" * 5000 + "}")
    assert len(debrief.load_records(path.parent.parent)) == 1


def test_load_records_are_oldest_first(tmp_path: Path) -> None:
    project = _project(tmp_path)
    _, path = debrief.record(project, PROVE, ANSWER, phase="proof", worker_id="w1")
    data = json.loads(path.read_text())
    # A later file name holding an earlier time must still sort first.
    data.update(attempt_id="f" * 32, recorded_at="2000-01-01T00:00:00Z")
    (path.parent / f"{'f' * 32}.json").write_text(json.dumps(data))
    assert [entry.attempt_id for entry in debrief.load_records(path.parent.parent)] == ["f" * 32, path.stem]


# --- the store's file discipline ----------------------------------------------------


def test_records_are_exclusive_and_never_follow_symlinks(tmp_path: Path) -> None:
    root = (tmp_path / "store").resolve()
    outside = tmp_path / "outside.txt"
    outside.write_text("untouched")
    with store.open_root(root) as root_fd, store.open_subdir(root_fd, "records") as records:
        store.create_exclusive(records, "a.json", b"{}")
        with pytest.raises(FileExistsError):
            store.create_exclusive(records, "a.json", b"{}")
        os.symlink(outside, root / "records" / "b.json")
        with pytest.raises(FileExistsError):
            store.create_exclusive(records, "b.json", b"evil")
        with pytest.raises(OSError):
            store.read_bounded(records, "b.json")
        store.replace_atomic(records, "b.json", b"view")
        with pytest.raises(store.UnsafeStoreError):
            store.create_exclusive(records, "../escape.json", b"{}")
    assert outside.read_text() == "untouched"
    assert (root / "records" / "b.json").read_text() == "view"


def test_the_store_refuses_files_over_its_bound(tmp_path: Path) -> None:
    root = (tmp_path / "store").resolve()
    oversized = b" " * (store.MAX_FILE_BYTES + 1)
    with store.open_root(root) as root_fd, store.open_subdir(root_fd, "records") as records:
        with pytest.raises(store.UnsafeStoreError):
            store.create_exclusive(records, "big.json", oversized)
        (root / "records" / "big.json").write_bytes(oversized)
        with pytest.raises(store.UnsafeStoreError):
            store.read_bounded(records, "big.json")


def test_a_symlinked_records_directory_is_refused(monkeypatch, tmp_path: Path) -> None:
    project = _project(tmp_path)
    root = tmp_path / "store"
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    root.mkdir()
    os.symlink(elsewhere, root / "records")
    monkeypatch.setenv(debrief.DEBRIEF_DIR_ENV, str(root))
    code, _, err = _cli(
        ["debrief", "record", PROVE, str(project), "--phase", "proof", "--worker-id", "w1"], monkeypatch, ANSWER
    )
    assert code == 2 and err.startswith("error:")
    assert list(elsewhere.iterdir()) == []


# --- derived views --------------------------------------------------------------------


def test_render_escapes_agent_text_and_derives_the_index(monkeypatch, tmp_path: Path) -> None:
    project = _repo(tmp_path)
    hostile = "[click](http://evil) <img src=x onerror=alert(1)> # heading"
    answer = json.dumps(
        {
            "friction": [{"what": hostile, "file": "A.lean", "line": 3, "lines": 6, "goal": "```\nescape\n```"}],
            "infrastructure_proposals": [{"kind": "import-export", "name": hostile, "what": "w"}],
        }
    )
    _, path = debrief.record(project, PROVE, answer, phase="proof", note=hostile, worker_id="w1")

    code, out, _ = _cli(["debrief", "render", str(project)], monkeypatch)

    views = debrief.debrief_root(project) / "views"
    assert code == 0 and "rendered 1" in out and str(views) in out
    assert _git(project, "status", "--porcelain") == ""
    [report] = (views / "reports").iterdir()
    text = report.read_text()
    index = (views / "README.md").read_text()
    for view in (text, index):
        assert re.search(r"(?<!\\)<img", view) is None
        assert re.search(r"(?<!\\)\]\(http", view) is None
    assert "````lean\n```\nescape\n```\n````" in text
    assert f"(reports/{report.name})" in index

    path.unlink()
    assert _cli(["debrief", "render", str(project)], monkeypatch)[0] == 0
    assert list((views / "reports").iterdir()) == []
    assert "No debrief records found." in (views / "README.md").read_text()
