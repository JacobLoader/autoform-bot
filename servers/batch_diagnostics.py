"""Lean diagnostics from one batch elaboration of a file with ``lake lean``.

Each call runs ``lake --no-build lean <file> -- --json`` in its own process
group and reads Lean's messages from stdout, one JSON object per line. Lean's
exit is the completion signal: there is no long-lived stream to keep in sync,
no quiet period to guess, and no document version or request id to match. The
group is terminated and verified dead before the call returns. ``--no-build``
keeps builds out of the call: stale imports are reported, not rebuilt.
"""

from __future__ import annotations

import json
import os
import selectors
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from servers.repl.core import (
    _inherit_clean_env,
    _kill_subprocesses,
    _wait_for_live_process_group_exit,
)

MAX_STDOUT_BYTES = 16 * 1024 * 1024
# How long Lake may take to exit after closing its output, before the group is
# stopped. Both pipes close only when every process holding them has exited.
EXIT_GRACE_SECONDS = 2.0
# Lake replays stored build logs on stderr, megabytes for some projects; keep
# only the end, where a build failure is reported.
STDERR_TAIL_BYTES = 8 * 1024
REPORTED_TAIL_CHARS = 2000
# Lean's status after reporting errors, and Lake's when --no-build finds a
# target that would need building. Any other nonzero status is a failure.
LEAN_ERROR_EXIT_CODE = 1
NO_BUILD_EXIT_CODE = 3
CLEANUP_ATTEMPTS = 3
# Command-line Lean stops after 100 errors by default; the server does not.
LEAN_ARGS = ("--json", "-DmaxErrors=0")
_READ_CHUNK_BYTES = 64 * 1024
_SEVERITIES = {"error": 1, "warning": 2, "information": 3}


class BatchDiagnosticsError(RuntimeError):
    """Lean's output could not be trusted as a complete diagnostic set."""


def batch_diagnostics(
    root: Path,
    path: Path,
    *,
    command: tuple[str, ...],
    timeout: float,
) -> list[dict[str, Any]]:
    """Return LSP-shaped diagnostics for ``path`` from one ``lake lean`` run.

    The result is clean only when Lean exits 0 with no messages, every stdout
    line parses, and the file is unchanged. Anything else either returns Lean's
    messages or raises, so a failed run is never reported as a clean file.
    """
    source = path.read_bytes()
    returncode, stdout, stderr_tail = _run([*command, str(path), "--", *LEAN_ARGS], root, timeout)
    shown = f"`{' '.join(command)}`"
    tail = stderr_tail.decode("utf-8", errors="replace").strip()[-REPORTED_TAIL_CHARS:]
    ending = f"\nLake's output ended with:\n{tail}" if tail else ""
    if stdout is None:
        raise TimeoutError(
            f"Lean did not finish checking {path.name} within {timeout:g}s "
            f"({shown}; LEAN_LSP_TIMEOUT).{ending}"
        )
    if path.read_bytes() != source:
        raise BatchDiagnosticsError(f"{path} changed while Lean checked it; run again")

    lines = source.decode("utf-8", errors="replace").split("\n")
    diagnostics = [
        _diagnostic(message, lines)
        for message in _messages(stdout)
        if not message.get("isSilent", False)
    ]
    if returncode == 0:
        return diagnostics
    if returncode == LEAN_ERROR_EXIT_CODE and any(item["severity"] == 1 for item in diagnostics):
        return diagnostics
    if returncode == NO_BUILD_EXIT_CODE:
        raise BatchDiagnosticsError(
            f"Lean did not check {path.name}: some of its imports are not built or are out "
            "of date. Build the modules Lake lists below, for example with `lake build "
            f"<module>`, and run again.{ending}"
        )
    if returncode == LEAN_ERROR_EXIT_CODE:
        raise BatchDiagnosticsError(
            f"Lake could not check {path.name}: {shown} exited with status 1 before Lean "
            f"reported an error.{ending}"
        )
    raise BatchDiagnosticsError(
        f"Lean stopped checking {path.name} with status {returncode}, so its "
        f"diagnostics may be incomplete.{ending}"
    )


def _run(argv: list[str], root: Path, timeout: float) -> tuple[int, bytes | None, bytes]:
    """Run one command in a fresh process group and verify the group is gone.

    Returns ``None`` for stdout when the deadline passed first.
    """
    deadline = time.monotonic() + timeout
    # Lake leaves a temporary setup file behind on every run; keep it per call.
    with tempfile.TemporaryDirectory(prefix="autoform-lake-lean-") as scratch:
        env = _inherit_clean_env()
        env["TMPDIR"] = scratch
        process = subprocess.Popen(
            argv,
            cwd=root,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        try:
            stdout, stderr_tail = _drain(process, deadline)
            if stdout is not None:
                _wait_for_live_process_group_exit(
                    process.pid, time.monotonic() + EXIT_GRACE_SECONDS
                )
        finally:
            try:
                _retire(process)
            finally:
                for stream in (process.stdout, process.stderr):
                    assert stream is not None
                    stream.close()
    return process.returncode, stdout, stderr_tail


def _retire(process: subprocess.Popen) -> None:
    """Stop the run's process group, then reap Lake, retrying a failed attempt.

    Lake leads the group and stays unreaped until the group is gone, so its
    group id cannot be reused while stragglers are being stopped.
    """
    for attempt in range(CLEANUP_ATTEMPTS):
        try:
            _kill_subprocesses(process, process.pid)
            return
        except Exception:
            if attempt + 1 == CLEANUP_ATTEMPTS:
                raise
            time.sleep(0.1 * 2**attempt)


def _drain(process: subprocess.Popen, deadline: float) -> tuple[bytes | None, bytes]:
    """Read stdout and the end of stderr until both close or time runs out.

    Returns ``None`` for stdout when the deadline passes first.
    """
    assert process.stdout is not None and process.stderr is not None
    stdout = bytearray()
    stderr_tail = bytearray()
    with selectors.DefaultSelector() as selector:
        for stream, sink in ((process.stdout, stdout), (process.stderr, stderr_tail)):
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_READ, sink)
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None, bytes(stderr_tail)
            for key, _ in selector.select(remaining):
                try:
                    chunk = os.read(key.fd, _READ_CHUNK_BYTES)
                except BlockingIOError:
                    continue
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                sink = key.data
                sink.extend(chunk)
                if sink is stderr_tail:
                    del sink[:-STDERR_TAIL_BYTES]
                elif len(sink) > MAX_STDOUT_BYTES:
                    raise BatchDiagnosticsError(
                        f"Lean wrote more than {MAX_STDOUT_BYTES} bytes of messages"
                    )
    return bytes(stdout), bytes(stderr_tail)


def _messages(stdout: bytes) -> list[dict[str, Any]]:
    try:
        text = stdout.decode("utf-8")
    except UnicodeDecodeError as error:
        raise BatchDiagnosticsError("Lean wrote invalid UTF-8 messages") from error
    messages = []
    # Lean escapes newlines inside a message, but not U+2028 and its kin, so
    # split on newlines only.
    for line in text.split("\n"):
        if not line.strip():
            continue
        try:
            message = json.loads(line)
        except ValueError as error:
            raise BatchDiagnosticsError(
                f"Lean wrote a line that is not a JSON message: {line[:200]!r}"
            ) from error
        if not isinstance(message, dict):
            raise BatchDiagnosticsError(f"Lean wrote a JSON value that is not a message: {line[:200]!r}")
        messages.append(message)
    return messages


def _diagnostic(message: dict[str, Any], lines: list[str]) -> dict[str, Any]:
    """Shape one ``lean --json`` message like the language server's diagnostic."""
    severity = _SEVERITIES.get(message.get("severity"))
    if severity is None:
        raise BatchDiagnosticsError(f"Lean message has an unknown severity: {message!r:.200}")
    start = _position(message.get("pos"), lines)
    if start is None:
        raise BatchDiagnosticsError(f"Lean message has no position: {message!r:.200}")
    text = message.get("data")
    if not isinstance(text, str):
        raise BatchDiagnosticsError(f"Lean message has no text: {message!r:.200}")
    end = _position(message.get("endPos"), lines) or start
    return {"severity": severity, "range": {"start": start, "end": end}, "message": text}


def _position(value: Any, lines: list[str]) -> dict[str, int] | None:
    """Convert Lean's 1-based line and code-point column to LSP's UTF-16 form."""
    if not isinstance(value, dict):
        return None
    line, column = value.get("line"), value.get("column")
    if not isinstance(line, int) or not isinstance(column, int) or line < 1 or column < 0:
        return None
    text = lines[line - 1] if line <= len(lines) else ""
    character = len(text[:column].encode("utf-16-le")) // 2 + max(0, column - len(text))
    return {"line": line - 1, "character": character}
