"""Batch diagnostics: one ``lake lean`` run per call, verified dead afterwards."""

from __future__ import annotations

import json
import os
import shutil
import sys
import textwrap
import threading
import time
from pathlib import Path

import psutil
import pytest

from servers import batch_diagnostics as batch
from servers.lean_runtime import LeanRuntimeConfig, LeanRuntimeServices
from servers.lsp import server as lsp
from tests.test_impact import _SKELETON_FIXTURE, _lean_toolchain_available
from tests.test_shared_lean_runtime import make_lake_project, runtime_config

_requires_real_lean = pytest.mark.skipif(
    not _lean_toolchain_available(), reason="needs lake and the fixture's Lean toolchain"
)


def _fake_lake(tmp_path: Path, body: str) -> tuple[str, ...]:
    """Return a command that runs ``body`` with the target file as ``target``."""
    script = tmp_path / "fake_lake.py"
    script.write_text(
        "import json, os, subprocess, sys, time\n"
        "from pathlib import Path\n"
        "target = Path(sys.argv[1])\n"
        "assert sys.argv[2:] == ['--', '--json', '-DmaxErrors=0'], sys.argv\n" + textwrap.dedent(body),
        encoding="utf-8",
    )
    return (sys.executable, str(script))


def _lean_file(tmp_path: Path, text: str = "theorem t : True := trivial\n") -> Path:
    path = tmp_path / "Probe.lean"
    path.write_text(text, encoding="utf-8")
    return path


def _message(severity: str, line: int, column: int, data: str, **extra: object) -> str:
    return json.dumps(
        {"severity": severity, "pos": {"line": line, "column": column}, "data": data, **extra}
    )


def _gone(pid: int) -> bool:
    try:
        return psutil.Process(pid).status() == psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return True


def test_a_silent_successful_run_is_clean(tmp_path):
    command = _fake_lake(tmp_path, "sys.exit(0)\n")
    diagnostics = batch.batch_diagnostics(tmp_path, _lean_file(tmp_path), command=command, timeout=30)

    assert diagnostics == []
    assert lsp.format_lsp_diagnostics(diagnostics) == "No diagnostics — file compiles cleanly."


def test_messages_become_language_server_diagnostics(tmp_path):
    path = _lean_file(tmp_path, "theorem t : True := trivial\ndef «𝓝x» : Nat := \"y\"\n")
    lines = [
        _message("error", 2, 18, "Type mismatch", endPos={"line": 2, "column": 21}),
        _message("warning", 1, 8, "declaration uses `sorry`", endPos=None),
        _message("information", 1, 0, "2"),
        _message("information", 1, 0, "silent", isSilent=True),
    ]
    command = _fake_lake(tmp_path, f"print({chr(10).join(lines)!r})\nsys.exit(1)\n")

    diagnostics = batch.batch_diagnostics(tmp_path, path, command=command, timeout=30)

    # Lean counts lines from 1 and columns in code points; the language server
    # counts lines from 0 and columns in UTF-16 units, so 𝓝 counts twice.
    assert diagnostics == [
        {"severity": 1, "range": {"start": {"line": 1, "character": 19}, "end": {"line": 1, "character": 22}},
         "message": "Type mismatch"},
        {"severity": 2, "range": {"start": {"line": 0, "character": 8}, "end": {"line": 0, "character": 8}},
         "message": "declaration uses `sorry`"},
        {"severity": 3, "range": {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 0}},
         "message": "2"},
    ]


def test_unicode_line_separators_stay_inside_their_message(tmp_path):
    text = "one" + chr(0x2028) + "two" + chr(0x85) + "three"
    # Lean's JSON printer leaves these characters unescaped.
    line = json.dumps({"severity": "error", "pos": {"line": 1, "column": 0}, "data": text}, ensure_ascii=False)
    command = _fake_lake(tmp_path, f"sys.stdout.buffer.write({(line + chr(10)).encode()!r})\nsys.exit(1)\n")

    diagnostics = batch.batch_diagnostics(tmp_path, _lean_file(tmp_path), command=command, timeout=30)

    assert [item["message"] for item in diagnostics] == [text]


def test_stale_imports_are_reported_instead_of_built(tmp_path):
    command = _fake_lake(
        tmp_path,
        """
        sys.stderr.write("error: target is out-of-date and needs to be rebuilt\\n")
        sys.stderr.write("Some required targets logged failures:\\n- Skel.Defs\\n")
        sys.exit(3)
        """,
    )

    with pytest.raises(batch.BatchDiagnosticsError, match="imports are not built") as raised:
        batch.batch_diagnostics(tmp_path, _lean_file(tmp_path), command=command, timeout=30)

    assert "Build the modules Lake lists below" in str(raised.value)
    assert str(raised.value).endswith("- Skel.Defs")


def test_a_lake_failure_without_a_lean_error_is_never_clean(tmp_path):
    command = _fake_lake(
        tmp_path,
        """
        print(json.dumps({"severity": "warning", "pos": {"line": 1, "column": 0}, "data": "w"}))
        sys.stderr.write("boom\\n")
        sys.exit(1)
        """,
    )

    with pytest.raises(batch.BatchDiagnosticsError, match="Lake could not check Probe.lean") as raised:
        batch.batch_diagnostics(tmp_path, _lean_file(tmp_path), command=command, timeout=30)

    assert raised.value.args[0].endswith("boom")


def test_a_crash_after_an_error_is_not_a_complete_result(tmp_path):
    command = _fake_lake(tmp_path, f"print({_message('error', 1, 0, 'first error')!r})\nsys.exit(137)\n")

    with pytest.raises(batch.BatchDiagnosticsError, match="status 137, so its diagnostics may be incomplete"):
        batch.batch_diagnostics(tmp_path, _lean_file(tmp_path), command=command, timeout=30)


@pytest.mark.parametrize(
    "line",
    ["not json", "[1, 2]", json.dumps({"severity": "fatal", "pos": {"line": 1, "column": 0}, "data": "x"}),
     json.dumps({"severity": "error", "data": "no position"})],
)
def test_output_that_is_not_a_well_formed_message_fails_closed(tmp_path, line):
    command = _fake_lake(tmp_path, f"print({line!r})\nsys.exit(0)\n")

    with pytest.raises(batch.BatchDiagnosticsError):
        batch.batch_diagnostics(tmp_path, _lean_file(tmp_path), command=command, timeout=30)


def test_a_file_edited_during_the_run_fails_closed(tmp_path):
    command = _fake_lake(tmp_path, "target.write_text('changed', encoding='utf-8')\nsys.exit(0)\n")

    with pytest.raises(batch.BatchDiagnosticsError, match="changed while Lean checked it"):
        batch.batch_diagnostics(tmp_path, _lean_file(tmp_path), command=command, timeout=30)


def test_a_timeout_stops_the_whole_process_group(tmp_path):
    pid_file = tmp_path / "child.pid"
    command = _fake_lake(
        tmp_path,
        f"""
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(600)"])
        Path({str(pid_file)!r}).write_text(str(child.pid))
        sys.stderr.write("still elaborating\\n")
        sys.stderr.flush()
        time.sleep(600)
        """,
    )

    started = time.monotonic()
    with pytest.raises(TimeoutError, match="LEAN_LSP_TIMEOUT") as raised:
        batch.batch_diagnostics(tmp_path, _lean_file(tmp_path), command=command, timeout=2)

    assert time.monotonic() - started < 30
    assert "Lean did not finish checking Probe.lean within 2s" in str(raised.value)
    assert str(raised.value).endswith("still elaborating")
    assert _gone(int(pid_file.read_text()))


def test_processes_left_behind_after_a_normal_exit_are_stopped(tmp_path, monkeypatch):
    monkeypatch.setattr(batch, "EXIT_GRACE_SECONDS", 0.2)
    pid_file = tmp_path / "child.pid"
    command = _fake_lake(
        tmp_path,
        f"""
        child = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(600)"],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        Path({str(pid_file)!r}).write_text(str(child.pid))
        sys.exit(0)
        """,
    )

    assert batch.batch_diagnostics(tmp_path, _lean_file(tmp_path), command=command, timeout=30) == []
    assert _gone(int(pid_file.read_text()))


def test_a_failed_cleanup_attempt_is_retried(tmp_path, monkeypatch):
    calls = []
    real = batch._kill_subprocesses

    def flaky(process, process_group_id):
        calls.append(process_group_id)
        if len(calls) == 1:
            raise RuntimeError("timed out terminating the Lean process group")
        real(process, process_group_id)

    monkeypatch.setattr(batch, "_kill_subprocesses", flaky)
    command = _fake_lake(tmp_path, "sys.exit(0)\n")

    assert batch.batch_diagnostics(tmp_path, _lean_file(tmp_path), command=command, timeout=30) == []
    assert len(calls) == 2


def test_output_over_the_limit_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setattr(batch, "MAX_STDOUT_BYTES", 1000)
    command = _fake_lake(tmp_path, "sys.stdout.write('x' * 5000)\nsys.stdout.flush()\ntime.sleep(600)\n")

    with pytest.raises(batch.BatchDiagnosticsError, match="more than 1000 bytes"):
        batch.batch_diagnostics(tmp_path, _lean_file(tmp_path), command=command, timeout=30)


def test_only_the_end_of_lakes_output_is_kept(tmp_path):
    command = _fake_lake(
        tmp_path,
        """
        sys.stderr.write("replayed build log\\n" * 200000)
        sys.stderr.write("LAST LINE\\n")
        sys.exit(2)
        """,
    )

    with pytest.raises(batch.BatchDiagnosticsError) as raised:
        batch.batch_diagnostics(tmp_path, _lean_file(tmp_path), command=command, timeout=60)

    tail = str(raised.value).split("Lake's output ended with:\n", 1)[1]
    assert tail.endswith("LAST LINE")
    assert len(tail) <= batch.REPORTED_TAIL_CHARS


def _services(**config: object) -> LeanRuntimeServices:
    def no_sessions(_root):
        raise AssertionError("batch diagnostics must not start a language server")

    return LeanRuntimeServices(runtime_config(**config), lsp_factory=no_sessions, start_sweepers=False)


def _check(services: LeanRuntimeServices, project: Path) -> object:
    try:
        return services.dispatch("lsp.diagnostics", {"project_dir": str(project), "file_path": "Probe.lean"})
    except Exception as error:
        return error


def test_the_lake_backend_starts_no_language_server(tmp_path):
    project = make_lake_project(tmp_path, "probe")
    _lean_file(project)
    services = _services(diagnostics_backend="lake", diagnostics_command=_fake_lake(tmp_path, "sys.exit(0)\n"))
    try:
        assert _check(services, project) == "No diagnostics — file compiles cleanly."
    finally:
        services.close()


def test_at_most_max_projects_checks_run_at_once(tmp_path):
    project = make_lake_project(tmp_path, "probe")
    _lean_file(project)
    marker = tmp_path / "running"
    command = _fake_lake(
        tmp_path,
        f"""
        marker = Path({str(marker)!r})
        fd = os.open(marker, os.O_CREAT | os.O_EXCL)
        time.sleep(0.5)
        os.close(fd)
        marker.unlink()
        """,
    )
    services = _services(diagnostics_backend="lake", diagnostics_command=command, max_projects=1)
    results: list[object] = []
    threads = [threading.Thread(target=lambda: results.append(_check(services, project))) for _ in range(3)]
    try:
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60)
    finally:
        services.close()

    assert results == ["No diagnostics — file compiles cleanly."] * 3


def _run_two_checks(services: LeanRuntimeServices, project: Path) -> list[object]:
    results: list[object] = []
    threads = [threading.Thread(target=lambda: results.append(_check(services, project))) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    return results


def test_time_waiting_for_a_slot_counts_against_lean_lsp_timeout(tmp_path, monkeypatch):
    project = make_lake_project(tmp_path, "probe")
    _lean_file(project)
    budgets: list[float] = []

    def check(_root, _path, *, command, timeout):
        budgets.append(timeout)
        time.sleep(0.6)
        return []

    monkeypatch.setattr("servers.lean_runtime.batch_diagnostics", check)
    services = _services(diagnostics_backend="lake", max_projects=1, lsp_timeout=2.0)
    try:
        results = _run_two_checks(services, project)
    finally:
        services.close()

    assert results == ["No diagnostics — file compiles cleanly."] * 2
    # The second call waited about 0.6 s for the slot, so it got that much less.
    assert max(budgets) > 1.9
    assert min(budgets) < 1.5


def test_a_slot_that_never_frees_fails_within_lean_lsp_timeout(tmp_path, monkeypatch):
    project = make_lake_project(tmp_path, "probe")
    _lean_file(project)

    def check(_root, _path, *, command, timeout):
        time.sleep(1.5)
        return []

    monkeypatch.setattr("servers.lean_runtime.batch_diagnostics", check)
    services = _services(diagnostics_backend="lake", max_projects=1, lsp_timeout=1.0)
    try:
        results = _run_two_checks(services, project)
    finally:
        services.close()

    assert "No diagnostics — file compiles cleanly." in results
    [failure] = [result for result in results if isinstance(result, TimeoutError)]
    assert "no free Lean slot within 1s" in str(failure)


def test_the_language_server_path_remains_available(tmp_path):
    project = make_lake_project(tmp_path, "probe")
    _lean_file(project)
    started: list[Path] = []

    class Session:
        def get_diagnostics(self, _path):
            return []

        def is_alive(self):
            return True

        def close(self):
            pass

    def factory(root):
        started.append(root)
        return Session()

    services = LeanRuntimeServices(
        runtime_config(diagnostics_backend="lsp"), lsp_factory=factory, start_sweepers=False
    )
    try:
        assert _check(services, project) == "No diagnostics — file compiles cleanly."
    finally:
        services.close()

    assert started == [project.resolve()]


def test_diagnostics_configuration_from_the_environment(monkeypatch):
    monkeypatch.delenv("LEAN_LSP_CMD", raising=False)
    monkeypatch.delenv("LEAN_DIAGNOSTICS_BACKEND", raising=False)
    config = LeanRuntimeConfig.from_environment()
    assert config.diagnostics_command == ("lake", "--no-build", "lean")
    assert config.diagnostics_backend == "lake"

    # Diagnostics follow the Lake that LEAN_LSP_CMD names.
    monkeypatch.setenv("LEAN_LSP_CMD", "elan run leanprover/lean4:v4.32.2 lake serve")
    monkeypatch.setenv("LEAN_DIAGNOSTICS_BACKEND", "lsp")
    config = LeanRuntimeConfig.from_environment()
    assert config.diagnostics_command == ("elan", "run", "leanprover/lean4:v4.32.2", "lake", "--no-build", "lean")
    assert config.diagnostics_backend == "lsp"

    monkeypatch.setenv("LEAN_LSP_CMD", "my-lean-server --stdio")
    assert LeanRuntimeConfig.from_environment().diagnostics_command == ("lake", "--no-build", "lean")

    monkeypatch.setenv("LEAN_DIAGNOSTICS_BACKEND", "server")
    with pytest.raises(ValueError, match="LEAN_DIAGNOSTICS_BACKEND"):
        LeanRuntimeConfig.from_environment()


# --------------------------------------------------------------------------- #
# Real Lean
# --------------------------------------------------------------------------- #

_PROBE = """\
theorem good : 1 + 1 = 2 := rfl

-- 𝓝 sits before the error column on the last line.
def bad : Nat := "not a nat"

#eval (2 : Nat)

theorem warns (h : True) : True := by
  sorry

def «𝓝x» : Nat := "astral before the error column"
"""

_PROBE_DIAGNOSTICS = """\
Diagnostics: 2 error(s), 1 warning(s)
4:17: error: Type mismatch
  "not a nat"
has type
  String
but is expected to have type
  Nat
6:0: info: 2
8:8: warning: declaration uses `sorry`
11:19: error: Type mismatch
  "astral before the error column"
has type
  String
but is expected to have type
  Nat"""

_LAKE_LEAN = ("lake", "--no-build", "lean")


def _real_lean_project(root: Path, **modules: str) -> Path:
    (root / "Probe").mkdir(parents=True)
    shutil.copy(_SKELETON_FIXTURE / "lean-toolchain", root / "lean-toolchain")
    (root / "lakefile.toml").write_text('name = "probe"\n\n[[lean_lib]]\nname = "Probe"\n', encoding="utf-8")
    for name, text in modules.items():
        (root / "Probe" / f"{name}.lean").write_text(text, encoding="utf-8")
    return root


@_requires_real_lean
def test_real_lean_batch_diagnostics_match_the_language_server(tmp_path):
    project = _real_lean_project(tmp_path / "probe", Main=_PROBE, Clean="theorem ok : True := trivial\n")
    path = project / "Probe" / "Main.lean"

    from_batch = batch.batch_diagnostics(project, path, command=_LAKE_LEAN, timeout=300)
    clean = batch.batch_diagnostics(project, project / "Probe" / "Clean.lean", command=_LAKE_LEAN, timeout=300)
    session = lsp.LeanLspSession(lsp.LspConfig(cwd=str(project), timeout=300))
    session.start()
    try:
        from_server = session.get_diagnostics(str(path))
    finally:
        session.close()

    assert lsp.format_lsp_diagnostics(from_batch) == _PROBE_DIAGNOSTICS
    assert lsp.format_lsp_diagnostics(from_server) == _PROBE_DIAGNOSTICS
    assert clean == []


@_requires_real_lean
def test_real_lean_reports_unbuilt_imports_without_building_them(tmp_path):
    project = _real_lean_project(tmp_path / "stale", Main="import Probe.Dep\n", Dep="def dep : Nat := 1\n")

    with pytest.raises(batch.BatchDiagnosticsError, match="imports are not built") as raised:
        batch.batch_diagnostics(project, project / "Probe" / "Main.lean", command=_LAKE_LEAN, timeout=300)

    assert "Probe.Dep" in str(raised.value)
    assert not list((project / ".lake").rglob("Dep.olean"))


@_requires_real_lean
def test_real_lean_batch_diagnostics_through_a_mathlib_import():
    root = os.environ.get("AUTOFORM_REAL_LEAN_MATHLIB_PROJECT")
    if not root:
        if os.environ.get("AUTOFORM_REQUIRE_REAL_LEAN_TESTS") == "1":
            pytest.fail("AUTOFORM_REAL_LEAN_MATHLIB_PROJECT must name a built Mathlib project")
        pytest.skip("needs AUTOFORM_REAL_LEAN_MATHLIB_PROJECT, a built Mathlib project")
    project = Path(root).resolve()
    probe = project / "src" / "GeneratedProject" / "BatchDiagnosticsProbe.lean"
    created = not probe.parent.exists()
    probe.parent.mkdir(parents=True, exist_ok=True)
    probe.write_text("import Mathlib\nexample : (2 : Nat) + 2 = 5 := rfl\n", encoding="utf-8")
    try:
        diagnostics = batch.batch_diagnostics(project, probe, command=_LAKE_LEAN, timeout=300)
    finally:
        probe.unlink(missing_ok=True)
        if created:
            probe.parent.rmdir()

    assert [item["range"]["start"]["line"] for item in diagnostics if item["severity"] == 1] == [1]
