# Bounded, Target-Scoped `claim list` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `autoform claim list [TARGET...] [--timeout SECONDS]` lists only the
named claims, finishes or fails within a bound, names slow steps, and labels
failures `timeout:`, `contention:` or `transport:`.

**Architecture:** `ClaimBoard._git` becomes a small bounded runner: its own
process group without a terminal, `GIT_TERMINAL_PROMPT=0`, an optional
monotonic deadline, a one-shot progress callback, and a group kill on expiry.
`ClaimBoard.list` passes a `functools.partial` of `_git` carrying its deadline
and callback down to its private helpers, and with targets names, fetches and
reads only their refs. The CLI maps the two new `ClaimTransportError`
subclasses to labels on stderr.

**Tech Stack:** Python ≥ 3.10 standard library (`subprocess`, `os.killpg`,
`functools`), Git, pytest, ruff.

**Spec:** `docs/superpowers/specs/2026-10-22-claim-list-targets-design.md`

**Worktree:** `/Users/avalon/Desktop/meta/autoform/autoform-bot-claim-list-targets`,
branch `feat/claim-list-targets`, based on upstream `main` (`5cb3f84c`). Run
every command from that directory. `origin` is a stale fork; never base
anything on `origin/main`.

## Global Constraints

- Every failure of `claim list` exits 1; a duplicate target exits 2.
- Failure labels, exactly: `error: timeout: no answer from the claim board within <N>s while <step>`, `error: transport: <reason>`, `error: contention: <reason>`.
- `claim list` writes only JSON to stdout; its errors, warnings and progress go to stderr.
- `--timeout` default 120 seconds, one deadline for the whole listing.
- Per git command limit stays 120 seconds; progress threshold 5 seconds.
- Progress line format: `claim list: <step>...`.
- Every claim git command runs with `GIT_TERMINAL_PROMPT=0`, in its own process group/session, stdin from the null device unless given input.
- Mutating commands (`acquire`, `renew`, `release`, `cleanup`) get no overall deadline and keep their messages and output channels.
- Without targets, `claim list` output is byte-for-byte today's.
- New exceptions subclass `ClaimTransportError`.
- Public CLI and JSON shapes are contracts: the JSON entry fields do not change.
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- `make lint` and `make test` pass at the end of every task.

## Review Focus

1. Targets whose keys differ only in case on a case-insensitive scratch: both must be listed (numbered private refs make this work; Task 3 pins it).
2. A listing that times out must still delete its private refs, though the deadline is spent (Task 2 pins it).
3. The 120 s per-command limit binding before the deadline must stay a plain transport error, not a `timeout:` (Task 1 pins it).
4. On failure, stdout must stay empty so a caller parsing JSON never sees an error line (Task 4 pins it for each label).
5. A progress callback that raises (for example stderr closed) must not leave git running (Task 1 pins that any exception kills the group).

---

### Task 1: Bounded claims runner and new error types

**Files:**
- Modify: `autoform_cli/claims.py` (imports at lines 9-24, constants near line 34-84, exception classes after line 111, `ClaimBoard._git` at lines 284-309, `__all__`)
- Modify: `.github/workflows/tests.yml` (Windows job's explicit pytest list, around line 236-245)
- Test: `tests/test_claims.py`

**Interfaces:**
- Produces:
  - `claims.ClaimTimeoutError(step: str)`, subclass of `ClaimTransportError`, attribute `step: str`, message `no answer from the claim board while {step}`.
  - `claims.ClaimContentionError`, subclass of `ClaimTransportError` (raised from Task 2).
  - `ClaimBoard._git(args, *, check=True, input_text=None, input_bytes=None, deadline: float | None = None, step: str = "running git", progress: Callable[[str], None] | None = None) -> subprocess.CompletedProcess[Any]`.
  - Module constants `_GIT_CALL_TIMEOUT_S = 120.0`, `_PROGRESS_AFTER_S = 5.0`, `_KILL_GRACE_S = 5.0` (tests patch the first two).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_claims.py`:

```python
def _alias(name: str, command: str) -> list[str]:
    """Git arguments that run ``command`` through sh as git alias ``name``."""
    return ["-c", f"alias.{name}=!{command}", name]


def _scratch_board(tmp_path: Path) -> claims.ClaimBoard:
    board = claims.ClaimBoard(tmp_path / "unused.git", "worker", tmp_path / "scratch")
    board._ensure_scratch()
    return board


def test_git_runs_without_terminal_prompts(tmp_path: Path) -> None:
    board = _scratch_board(tmp_path)

    assert board._git(_alias("env", "printenv GIT_TERMINAL_PROMPT")).stdout.strip() == "0"


@pytest.mark.skipif(os.name != "posix", reason="controlling terminals are POSIX")
def test_git_runs_without_a_controlling_terminal(tmp_path: Path) -> None:
    board = _scratch_board(tmp_path)

    probe = _alias("tty", "(exec 3</dev/tty) 2>/dev/null && echo tty || echo none")
    assert board._git(probe).stdout.strip() == "none"


def test_git_reads_no_input_it_was_not_given(tmp_path: Path) -> None:
    board = _scratch_board(tmp_path)

    assert board._git(_alias("read", "cat"), deadline=time.monotonic() + 10).stdout == ""


def test_git_stops_at_the_deadline_and_names_the_step(tmp_path: Path) -> None:
    board = _scratch_board(tmp_path)
    started = time.monotonic()

    with pytest.raises(claims.ClaimTimeoutError) as timed_out:
        board._git(_alias("hang", "sleep 30"), deadline=started + 0.5, step="hanging")

    assert timed_out.value.step == "hanging"
    assert str(timed_out.value) == "no answer from the claim board while hanging"
    assert time.monotonic() - started < 10


def test_git_does_not_start_once_the_deadline_has_passed(tmp_path: Path) -> None:
    board = _scratch_board(tmp_path)
    marker = tmp_path / "ran"

    with pytest.raises(claims.ClaimTimeoutError):
        board._git(_alias("touch", f"touch '{marker}'"), deadline=time.monotonic() - 1, step="late")

    assert not marker.exists()


def test_git_reports_its_own_time_limit_as_a_transport_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    board = _scratch_board(tmp_path)
    monkeypatch.setattr(claims, "_GIT_CALL_TIMEOUT_S", 0.5)

    with pytest.raises(claims.ClaimTransportError) as failed:
        board._git(_alias("hang", "sleep 30"), deadline=time.monotonic() + 60)

    assert not isinstance(failed.value, claims.ClaimTimeoutError)


@pytest.mark.skipif(os.name != "posix", reason="process groups are POSIX")
def test_git_kills_what_it_started_when_it_times_out(tmp_path: Path) -> None:
    board = _scratch_board(tmp_path)
    pid_file = tmp_path / "pid"

    with pytest.raises(claims.ClaimTimeoutError):
        board._git(
            _alias("spawn", f"sleep 30 & echo $! > '{pid_file}'; wait"),
            deadline=time.monotonic() + 1,
            step="spawning",
        )

    pid = int(pid_file.read_text())
    gone_by = time.monotonic() + 5
    while time.monotonic() < gone_by:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.05)
    pytest.fail(f"process {pid} that git started outlived its timeout")


def test_git_names_a_slow_step_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    board = _scratch_board(tmp_path)
    monkeypatch.setattr(claims, "_PROGRESS_AFTER_S", 0.2)
    steps: list[str] = []

    board._git(_alias("slow", "sleep 1"), step="sleeping", progress=steps.append)

    assert steps == ["sleeping"]


def test_git_sends_its_input_once_to_a_slow_step(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    board = _scratch_board(tmp_path)
    monkeypatch.setattr(claims, "_PROGRESS_AFTER_S", 0.2)

    echoed = board._git(_alias("echo", "sleep 1; cat"), input_text="once\n", progress=lambda step: None)

    assert echoed.stdout == "once\n"


@pytest.mark.skipif(os.name != "posix", reason="process groups are POSIX")
def test_git_kills_its_command_when_progress_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    board = _scratch_board(tmp_path)
    # Long enough for sh to write the pid file before the callback runs.
    monkeypatch.setattr(claims, "_PROGRESS_AFTER_S", 0.5)
    pid_file = tmp_path / "pid"

    def broken(step: str) -> None:
        raise BrokenPipeError("stderr closed")

    with pytest.raises(BrokenPipeError):
        board._git(_alias("spawn", f"sleep 30 & echo $! > '{pid_file}'; wait"), progress=broken)

    pid = int(pid_file.read_text())
    gone_by = time.monotonic() + 5
    while time.monotonic() < gone_by:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.05)
    pytest.fail(f"process {pid} outlived a progress callback that raised")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest -q tests/test_claims.py -k "test_git_"`
Expected: FAIL. `test_git_runs_without_terminal_prompts` prints an empty
value, the deadline tests fail with `TypeError: ... unexpected keyword argument 'deadline'`,
and `claims.ClaimTimeoutError` raises `AttributeError`.

- [ ] **Step 3: Implement the runner**

In `autoform_cli/claims.py`, add to the imports (keep alphabetical order):

```python
import contextlib
import signal
from typing import Any, Callable, Mapping, Sequence
```

After `_LOCK_POLL_S = 0.05`, add:

```python
# One git command's time limit, whatever deadline its caller has.
_GIT_CALL_TIMEOUT_S = 120.0
# A step still running after this long is named to a progress callback.
_PROGRESS_AFTER_S = 5.0
# How long a killed git command gets to be reaped.
_KILL_GRACE_S = 5.0
# Each git command leads its own process group, without a controlling
# terminal, so ssh cannot prompt and a timeout also ends git's transport.
_NEW_PROCESS_GROUP: dict[str, Any] = (
    {"start_new_session": True}
    if os.name == "posix"
    else {"creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)}
)
```

Add `"GIT_TERMINAL_PROMPT": "0",` as the last entry of `_GIT_ENV`, with this
comment above the dictionary's closing brace:

```python
    # A missing credential fails at once instead of waiting for a prompt.
    "GIT_TERMINAL_PROMPT": "0",
```

After `class MalformedLeaseError`, add:

```python
class ClaimTimeoutError(ClaimTransportError):
    """The claim board did not answer before the caller's deadline."""

    def __init__(self, step: str) -> None:
        super().__init__(f"no answer from the claim board while {step}")
        self.step = step


class ClaimContentionError(ClaimTransportError):
    """The board refused every attempt to fetch claims because claim refs kept moving."""
```

Before `class ClaimBoard`, add the two module helpers:

```python
def _communicate(
    process: subprocess.Popen[Any],
    data: str | bytes | None,
    limit: float,
    step: str,
    progress: Callable[[str], None] | None,
) -> tuple[Any, Any]:
    """Wait up to ``limit`` seconds for ``process``, naming a slow ``step`` to ``progress`` once."""
    if progress is not None and limit > _PROGRESS_AFTER_S:
        try:
            return process.communicate(data, timeout=_PROGRESS_AFTER_S)
        except subprocess.TimeoutExpired:
            progress(step)
        # communicate keeps the input it was given and never sends it twice.
        return process.communicate(timeout=limit - _PROGRESS_AFTER_S)
    return process.communicate(data, timeout=limit)


def _kill_group(process: subprocess.Popen[Any]) -> None:
    """Kill a git command and everything it started, then reap it."""
    with contextlib.suppress(OSError, subprocess.SubprocessError):
        if os.name == "posix":
            # git is not reaped yet, so its pid still names its process group.
            os.killpg(process.pid, signal.SIGKILL)
        else:
            subprocess.run(
                ["taskkill", "/T", "/F", "/PID", str(process.pid)],
                capture_output=True,
                timeout=_KILL_GRACE_S,
            )
    with contextlib.suppress(OSError):
        process.kill()
    with contextlib.suppress(subprocess.TimeoutExpired):
        process.communicate(timeout=_KILL_GRACE_S)
```

Replace the whole body of `ClaimBoard._git` (lines 284-309) with:

```python
    def _git(
        self,
        args: list[str],
        *,
        check: bool = True,
        input_text: str | None = None,
        input_bytes: bytes | None = None,
        deadline: float | None = None,
        step: str = "running git",
        progress: Callable[[str], None] | None = None,
    ) -> subprocess.CompletedProcess[Any]:
        """Run git in the scratch board; with ``input_bytes``, input and output are bytes.

        A command gets at most 120 seconds and, with ``deadline`` (a
        ``time.monotonic()`` value), no time past it, which raises
        ``ClaimTimeoutError`` naming ``step``. Running out kills the command's
        whole process group. ``progress`` hears ``step`` once if the command
        is still running after five seconds.
        """
        limit = _GIT_CALL_TIMEOUT_S
        if deadline is not None:
            limit = min(limit, deadline - time.monotonic())
            if limit <= 0:
                raise ClaimTimeoutError(step)
        data = input_text if input_bytes is None else input_bytes
        try:
            process = subprocess.Popen(
                ["git", *args],
                cwd=self.scratch,
                stdin=subprocess.DEVNULL if data is None else subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=input_bytes is None,
                env={**os.environ, **_GIT_ENV},
                **_NEW_PROCESS_GROUP,
            )
        except OSError as exc:
            raise ClaimTransportError(f"git claim-board operation failed: {exc}") from exc
        try:
            stdout, stderr = _communicate(process, data, limit, step, progress)
        except subprocess.TimeoutExpired as exc:
            _kill_group(process)
            if limit < _GIT_CALL_TIMEOUT_S:
                raise ClaimTimeoutError(step) from exc
            raise ClaimTransportError(f"git claim-board operation failed: {exc}") from exc
        except BaseException:
            _kill_group(process)
            raise
        proc = subprocess.CompletedProcess(["git", *args], process.returncode, stdout, stderr)
        if check and proc.returncode != 0:
            output = proc.stderr or proc.stdout
            detail = (output if isinstance(output, str) else os.fsdecode(output)).strip()[:300]
            raise ClaimTransportError(f"git {' '.join(args[:2])} failed against claim board: {detail}")
        return proc
```

Note: `limit < _GIT_CALL_TIMEOUT_S` is true only when a deadline shortened
the limit, so the 120 s limit stays a plain transport error. When the test
patches `_GIT_CALL_TIMEOUT_S` to 0.5 with a 60 s deadline, the limit is 0.5,
not shorter than the patched constant, so it is a transport error, as the test
requires.

Add `"ClaimContentionError",` and `"ClaimTimeoutError",` to `__all__` in
alphabetical order.

- [ ] **Step 4: Add the portable runner tests to the Windows CI job**

In `.github/workflows/tests.yml`, in the Windows job's `uv run pytest -q`
list (the one that names `tests/test_skeleton.py::test_bounded_command_rejects_excess_output`),
add these lines after the last `tests/test_skeleton.py::...` entry, with the
same indentation:

```yaml
          tests/test_claims.py::test_git_runs_without_terminal_prompts
          tests/test_claims.py::test_git_stops_at_the_deadline_and_names_the_step
          tests/test_claims.py::test_git_does_not_start_once_the_deadline_has_passed
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest -q tests/test_claims.py tests/test_claim_cli.py tests/test_dashboard.py`
Expected: all pass, including the new `test_git_*` tests and every existing claim test.

- [ ] **Step 6: Lint**

Run: `make lint`
Expected: no findings.

- [ ] **Step 7: Commit**

```bash
git add autoform_cli/claims.py tests/test_claims.py .github/workflows/tests.yml
git commit -m "Bound claim git commands and never wait for a credential prompt

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Deadline, progress and contention for the whole-board listing

**Files:**
- Modify: `autoform_cli/claims.py` (`_ensure_scratch`, `list`, `_fetch_claims`, `_remote_keys`, `_refs_in`, `_delete_refs`, `_read_commits`, `_read_listed`; a `_validate_timeout` helper beside `_validate_ttl`)
- Test: `tests/test_claims.py`

**Interfaces:**
- Consumes: `ClaimBoard._git(..., deadline=, step=, progress=)`, `ClaimTimeoutError`, `ClaimContentionError` from Task 1.
- Produces:
  - `ClaimBoard.list(*, timeout: float | None = None, progress: Callable[[str], None] | None = None) -> list[dict[str, Any]]` (Task 3 adds a leading `keys` parameter).
  - Private helpers taking a runner `git` (a callable with `_git`'s signature): `_ensure_scratch(git=None)`, `_fetch_claims(written, git)`, `_remote_keys(git)`, `_refs_in(namespace, git)`, `_read_commits(oids, git)`, `_read_listed(listed, git)`.
  - Step names, exactly: `"preparing the scratch"`, `"naming the claim refs"`, `"fetching the claim board"`, `"reading the fetched refs"`, `f"reading {n} leases"`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_claims.py`:

```python
@pytest.fixture
def hanging_board(monkeypatch: pytest.MonkeyPatch) -> str:
    """A board URL whose transport never answers."""
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "protocol.ext.allow")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "always")
    return "ext::sleep 30"


def test_list_stops_at_its_timeout_and_names_the_step(tmp_path: Path, hanging_board: str) -> None:
    reader = claims.ClaimBoard(hanging_board, "worker-b", tmp_path / "scratch")
    started = time.monotonic()

    with pytest.raises(claims.ClaimTimeoutError) as timed_out:
        reader.list(timeout=1)

    assert timed_out.value.step == "fetching the claim board"
    assert time.monotonic() - started < 10
    assert _git("for-each-ref", "refs/autoform-list/", cwd=tmp_path / "scratch") == ""


def test_list_deletes_its_refs_after_a_timeout_later_in_the_listing(
    tmp_path: Path, board_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = _board(tmp_path, board_repo, "worker-a")
    assert owner.acquire("a", ttl=600)
    reader = _board(tmp_path, board_repo, "worker-b")
    git = reader._git

    def times_out_reading_leases(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[0] == "cat-file":
            raise claims.ClaimTimeoutError(str(kwargs["step"]))
        return git(args, **kwargs)

    monkeypatch.setattr(reader, "_git", times_out_reading_leases)
    with pytest.raises(claims.ClaimTimeoutError) as timed_out:
        reader.list(timeout=60)

    assert timed_out.value.step == "reading 1 leases"
    assert _git("for-each-ref", "refs/autoform-list/", cwd=tmp_path / "scratch-worker-b") == ""


def test_list_gives_every_git_command_its_deadline_except_cleanup(
    tmp_path: Path, board_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = _board(tmp_path, board_repo, "worker-a")
    assert owner.acquire("a", ttl=600)
    reader = _board(tmp_path, board_repo, "worker-b")
    git = reader._git
    deadlines: dict[str, object] = {}

    def recording_git(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        deadlines[args[0]] = kwargs.get("deadline")
        return git(args, **kwargs)

    monkeypatch.setattr(reader, "_git", recording_git)
    reader.list(timeout=60)

    assert deadlines.pop("update-ref") is None
    assert deadlines and all(isinstance(deadline, float) for deadline in deadlines.values())


def test_list_names_no_step_when_every_step_is_fast(tmp_path: Path, board_repo: Path) -> None:
    owner = _board(tmp_path, board_repo, "worker-a")
    assert owner.acquire("a", ttl=600)
    steps: list[str] = []

    assert [lease["_key"] for lease in _board(tmp_path, board_repo, "worker-b").list(progress=steps.append)] == ["a"]
    assert steps == []


@pytest.mark.parametrize("timeout", [0, -1, float("nan"), float("inf"), True])
def test_list_refuses_a_timeout_that_is_not_a_positive_finite_number(
    tmp_path: Path, board_repo: Path, timeout: float
) -> None:
    with pytest.raises(ValueError, match="timeout"):
        _board(tmp_path, board_repo, "worker-b").list(timeout=timeout)


def test_list_reports_contention_when_every_fetch_is_refused_because_refs_moved(
    tmp_path: Path, board_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = _board(tmp_path, board_repo, "worker-a")
    assert owner.acquire("a", ttl=600)
    reader = _board(tmp_path, board_repo, "worker-b")
    git = reader._git
    fetches: list[list[str]] = []

    def always_refused(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[0] == "fetch":
            fetches.append(args)
            return subprocess.CompletedProcess(
                ["git", *args], 128, "", "fatal: remote error: upload-pack: not our ref 1234\n"
            )
        return git(args, **kwargs)

    monkeypatch.setattr(reader, "_git", always_refused)
    with pytest.raises(claims.ClaimContentionError, match="not our ref"):
        reader.list()
    assert len(fetches) == 3
```

Also, in the existing `test_list_reports_a_failed_fetch_without_retrying`,
add one line after the `with pytest.raises(...)` block so a plain failure is
pinned as not contention:

```python
    with pytest.raises(claims.ClaimTransportError, match=r"cannot fetch the claim board.*simulated fetch failure") as failed:
        reader.list()
    assert not isinstance(failed.value, claims.ClaimContentionError)
    assert len(fetches) == 1
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest -q tests/test_claims.py -k "list_"`
Expected: the new tests FAIL with `TypeError: ... unexpected keyword argument 'timeout'`
(or `'progress'`); the contention test fails because a `ClaimTransportError` is raised instead.

- [ ] **Step 3: Implement**

Add `import functools` to the imports, in alphabetical order.

Beside `_validate_ttl`, add:

```python
def _validate_timeout(timeout: float) -> float:
    if not _is_finite_number(timeout) or timeout <= 0:
        raise ValueError("claim list timeout must be a finite positive number")
    return timeout
```

After the imports' `_GIT_ENV` block (or beside the other module constants),
add the runner type:

```python
# ClaimBoard._git, or a functools.partial of it that carries a deadline.
_Git = Callable[..., "subprocess.CompletedProcess[Any]"]
```

`_ensure_scratch` takes an optional runner and names its step; replace its
two `self._git(...)` calls:

```python
    def _ensure_scratch(self, git: _Git | None = None) -> None:
        git = self._git if git is None else git
        last_error: BaseException | None = None
        for attempt in range(_SCRATCH_INIT_ATTEMPTS):
            try:
                if self.scratch.is_dir():
                    ready = git(
                        ["rev-parse", "--is-bare-repository"],
                        check=False,
                        step="preparing the scratch",
                    )
                    if ready.returncode == 0 and ready.stdout.strip() == "true":
                        return
                self.scratch.mkdir(parents=True, exist_ok=True)
            except ClaimTimeoutError:
                raise
            except (OSError, ClaimTransportError) as exc:
                last_error = exc
                break
            try:
                git(["init", "--bare", "--quiet", "."], step="preparing the scratch")
                return
            except ClaimTimeoutError:
                raise
            except ClaimTransportError as exc:
                last_error = exc
            if attempt + 1 < _SCRATCH_INIT_ATTEMPTS:
                time.sleep(_SCRATCH_INIT_DELAY_S)
        raise ClaimTransportError(
            "cannot prepare the local claim-board scratch directory"
        ) from last_error
```

(The `except ClaimTimeoutError: raise` clauses keep a timeout from being
swallowed into the generic "cannot prepare" error.)

Replace `list`:

```python
    def list(
        self,
        *,
        timeout: float | None = None,
        progress: Callable[[str], None] | None = None,
    ) -> list[dict[str, Any]]:
        """Return all claim refs, including malformed and expired entries.

        One fetch copies every claim ref and its commit into refs private to
        this call, so each listed lease is the one its ref named when the board
        answered, other processes sharing the scratch cannot change it, and the
        git commands it takes do not grow with the number of claims. A ref that
        changes meanwhile is listed as it was; every update checks ownership
        again.

        With ``timeout``, the listing gets that many seconds in all, and running
        out raises ``ClaimTimeoutError`` naming the step it was on.
        ``progress`` hears the name of each step still running after five
        seconds.
        """
        deadline = None if timeout is None else time.monotonic() + _validate_timeout(timeout)
        git = functools.partial(self._git, deadline=deadline, progress=progress)
        self._ensure_scratch(git)
        written: dict[str, dict[str, str] | None] = {}
        try:
            return self._read_listed(self._fetch_claims(written, git), git)
        finally:
            # Deleting the private refs gets its own time limit, even after the deadline.
            for namespace, refs in written.items():
                self._delete_refs(namespace, refs)
```

Replace `_fetch_claims`, keeping its docstring and adding one sentence:

```python
    def _fetch_claims(self, written: dict[str, dict[str, str] | None], git: _Git) -> dict[str, str]:
        """Fetch every claim ref into refs private to this call; return each claim's object ID, by key.

        Each fetch's namespace goes into ``written`` before it runs, with the refs
        it wrote once they are read. A private ref is named after its claim key,
        which a case-insensitive scratch cannot do for two keys that differ only
        in case; the board's keys are then fetched again by name into numbered refs.
        A board that refuses every attempt because claim refs moved raises
        ``ClaimContentionError``.
        """
        keys: list[str] | None = None
        failures = 0
        while True:
            namespace = f"{_LIST_REF_PREFIX}{uuid.uuid4().hex}/"
            written[namespace] = None
            # Negotiate only from this fetch's refs, which do not exist yet: the
            # scratch's other refs save nothing here, and under protocol v0 each
            # round spent offering them is a window in which a renewal fails it.
            args = ["fetch", "--quiet", "--no-tags", f"--negotiation-tip={namespace}*"]
            if keys is None:
                fetch = git(
                    [*args, self.repo_url, f"+{CLAIM_REF_PREFIX}*:{namespace}*"],
                    check=False,
                    step="fetching the claim board",
                )
            else:
                refspecs = "".join(f"+{CLAIM_REF_PREFIX}{key}:{namespace}{index}\n" for index, key in enumerate(keys))
                fetch = git(
                    [*args, "--stdin", self.repo_url],
                    check=False,
                    input_text=refspecs,
                    step=f"fetching {len(keys)} claim refs",
                )
            if fetch.returncode == 0:
                refs = written[namespace] = self._refs_in(namespace, git)
                if keys is None:
                    return _claims_by_key(refs, namespace)
                numbered = ((key, refs.get(f"{namespace}{index}")) for index, key in enumerate(keys))
                return {key: oid for key, oid in numbered if oid is not None}
            if keys is None and any(marker in fetch.stderr for marker in _CASE_COLLISION):
                keys = self._remote_keys(git)
                continue
            failures += 1
            # A claim released after `ls-remote` named it is no longer there to fetch.
            retryable = _MOVED_WANT in fetch.stderr or (keys is not None and _MISSING_REF in fetch.stderr)
            if not retryable:
                raise ClaimTransportError(f"cannot fetch the claim board: {_fetch_failure(fetch.stderr)}")
            if failures == _LIST_FETCH_ATTEMPTS:
                raise ClaimContentionError(
                    f"the claim board refused {failures} fetches because claim refs kept moving: "
                    f"{_fetch_failure(fetch.stderr)}"
                )
            if keys is not None:
                keys = self._remote_keys(git)
```

Thread `git` through the remaining helpers:

```python
    def _remote_keys(self, git: _Git) -> list[str]:
        """Return every validly named claim key the board advertises."""
        proc = git(["ls-remote", "--refs", self.repo_url, f"{CLAIM_REF_PREFIX}*"], step="naming the claim refs")
        refs = {line.partition("\t")[2]: "" for line in proc.stdout.splitlines()}
        return list(_claims_by_key(refs, CLAIM_REF_PREFIX))

    def _refs_in(self, namespace: str, git: _Git) -> dict[str, str]:
        """Return the object ID of every ref under ``namespace``, by ref name."""
        proc = git(
            ["for-each-ref", "--format=%(objectname)%09%(refname)", namespace],
            step="reading the fetched refs",
        )
        ...  # rest unchanged
```

In `_delete_refs`, change `refs = self._refs_in(namespace)` to
`refs = self._refs_in(namespace, self._git)`; its `update-ref` call stays on
`self._git` with no deadline.

`_read_commits(self, oids: Sequence[str], git: _Git)`: change its git call to

```python
        output = git(["cat-file", "--batch"], input_bytes=requests, step=f"reading {len(oids)} leases").stdout
```

`_read_listed(self, listed: Mapping[str, str], git: _Git)`: change its first
line to `commits = self._read_commits(list(dict.fromkeys(listed.values())), git)`.

Run `grep -n "_read_listed\|_read_commits\|_refs_in\|_remote_keys" autoform_cli/claims.py`
and confirm every call passes a runner.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest -q tests/test_claims.py tests/test_claim_cli.py tests/test_dashboard.py`
Expected: all pass.

- [ ] **Step 5: Lint and commit**

Run: `make lint` (expected: clean), then:

```bash
git add autoform_cli/claims.py tests/test_claims.py
git commit -m "Bound a claim listing, name its slow steps, and report contention

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: List only named targets

**Files:**
- Modify: `autoform_cli/claims.py` (`list`, `_fetch_claims`, `_remote_oids`)
- Test: `tests/test_claims.py`

**Interfaces:**
- Consumes: Task 2's `list`, `_fetch_claims(written, git)`, runner helpers.
- Produces:
  - `ClaimBoard.list(keys: Sequence[str] | None = None, *, timeout: float | None = None, progress: Callable[[str], None] | None = None) -> list[dict[str, Any]]`. `keys` are claim keys (already hashed); validated with `_validate_keys` (non-empty, no duplicates, a `str` raises `TypeError`).
  - `_fetch_claims(written, git, targets: tuple[str, ...] | None = None)`.
  - `_remote_oids(keys, git: _Git | None = None)`; existing one-argument callers unchanged.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_claims.py`:

```python
def _counting(reader: claims.ClaimBoard, monkeypatch: pytest.MonkeyPatch) -> list[tuple[list[str], dict[str, object]]]:
    git = reader._git
    calls: list[tuple[list[str], dict[str, object]]] = []

    def counting_git(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append((args, kwargs))
        return git(args, **kwargs)

    monkeypatch.setattr(reader, "_git", counting_git)
    return calls


def test_list_of_targets_returns_only_their_leases_as_a_full_listing_does(
    tmp_path: Path, board_repo: Path
) -> None:
    owner = _board(tmp_path, board_repo, "worker-a")
    assert owner.acquire_many(["a", "b", "c"], ttl=600)
    reader = _board(tmp_path, board_repo, "worker-b")

    full = {lease["_key"]: lease for lease in reader.list()}
    targeted = reader.list(["c", "a", "absent"])

    assert [lease["_key"] for lease in targeted] == ["a", "c"]
    assert targeted == [full["a"], full["c"]]


def test_list_of_absent_targets_is_empty_without_fetching(
    tmp_path: Path, board_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = _board(tmp_path, board_repo, "worker-a")
    assert owner.acquire("a", ttl=600)
    reader = _board(tmp_path, board_repo, "worker-b")
    calls = _counting(reader, monkeypatch)

    assert reader.list(["absent"]) == []
    assert not any(args[0] == "fetch" for args, _ in calls)


def test_list_of_targets_fetches_only_their_refs_whatever_the_board_size(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    counts = []
    for size in (1, 30):
        repo = tmp_path / f"board-{size}.git"
        _git("init", "--bare", "--quiet", str(repo))
        owner = claims.ClaimBoard(repo, "worker-a", tmp_path / f"owner-{size}")
        assert owner.acquire_many([f"k{index}" for index in range(size)], ttl=600)
        reader = claims.ClaimBoard(repo, "worker-b", tmp_path / f"reader-{size}")
        calls = _counting(reader, monkeypatch)

        assert [lease["_key"] for lease in reader.list(["k0"])] == ["k0"]
        fetches = [kwargs for args, kwargs in calls if args[0] == "fetch"]
        assert len(fetches) == 1
        [refspec] = str(fetches[0]["input_text"]).splitlines()
        assert refspec.startswith(f"+{claims.CLAIM_REF_PREFIX}k0:")
        assert not any(f"{claims.CLAIM_REF_PREFIX}*" in args for args, _ in calls)
        counts.append(len(calls))

    assert counts[0] == counts[1]


def test_list_of_targets_ignores_a_peer_renewing_another_claim(
    tmp_path: Path, board_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = _board(tmp_path, board_repo, "worker-a")
    assert owner.acquire_many(["a", "b"], ttl=600)
    reader = _board(tmp_path, board_repo, "worker-b")
    git = reader._git
    fetches = 0

    def renew_b_after_each_git_command(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        nonlocal fetches
        fetches += args[0] == "fetch"
        proc = git(args, **kwargs)
        assert owner.renew("b")
        return proc

    monkeypatch.setattr(reader, "_git", renew_b_after_each_git_command)

    assert [lease["_key"] for lease in reader.list(["a"])] == ["a"]
    assert fetches == 1


def test_list_of_targets_names_only_the_targets_again_when_one_is_released_meanwhile(
    tmp_path: Path, board_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = _board(tmp_path, board_repo, "worker-a")
    assert owner.acquire_many(["a", "b"], ttl=600)
    reader = _board(tmp_path, board_repo, "worker-b")
    git = reader._git
    calls: list[list[str]] = []

    def release_b_before_the_first_fetch(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[0] == "fetch" and not any(call[0] == "fetch" for call in calls):
            assert owner.release("b")
        calls.append(args)
        return git(args, **kwargs)

    monkeypatch.setattr(reader, "_git", release_b_before_the_first_fetch)

    assert [lease["_key"] for lease in reader.list(["a", "b"])] == ["a"]
    assert sum(call[0] == "fetch" for call in calls) == 2
    assert not any(f"{claims.CLAIM_REF_PREFIX}*" in call for call in calls)


def test_list_of_targets_reports_a_malformed_target_as_an_entry(tmp_path: Path, board_repo: Path) -> None:
    blob = _git("hash-object", "-w", "--stdin", cwd=board_repo, input_text="not a lease")
    _git("update-ref", f"{claims.CLAIM_REF_PREFIX}m", blob, cwd=board_repo)

    [lease] = _board(tmp_path, board_repo, "worker-b").list(["m"])

    assert lease["_key"] == "m"
    assert lease["_malformed"] is True


def test_list_of_targets_lists_keys_that_differ_only_in_case(tmp_path: Path, board_repo: Path) -> None:
    owner = _board(tmp_path, board_repo, "worker-a")
    assert owner.acquire_many(["Case", "case"], ttl=600)

    listed = _board(tmp_path, board_repo, "worker-b").list(["Case", "case"])

    assert sorted(lease["_key"] for lease in listed) == ["Case", "case"]


def test_list_of_targets_refuses_invalid_targets_before_running_git(
    tmp_path: Path, board_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reader = _board(tmp_path, board_repo, "worker-b")
    calls = _counting(reader, monkeypatch)

    with pytest.raises(ValueError, match="duplicate"):
        reader.list(["a", "a"])
    with pytest.raises(ValueError, match="at least one"):
        reader.list([])
    with pytest.raises(ValueError, match="invalid claim key"):
        reader.list(["../x"])
    with pytest.raises(TypeError):
        reader.list("a")
    assert calls == []


def test_list_of_targets_stops_at_its_timeout_while_naming_them(tmp_path: Path, hanging_board: str) -> None:
    reader = claims.ClaimBoard(hanging_board, "worker-b", tmp_path / "scratch")

    with pytest.raises(claims.ClaimTimeoutError) as timed_out:
        reader.list(["a"], timeout=1)

    assert timed_out.value.step == "naming the claim refs"
```

Note on the refspec assertion in
`test_list_ fail**

Run: `uv run pytest -q tests/test_claims.py -k "list_of_targets"`
Expected: FAIL with `TypeError: ClaimBoard.list() takes 1 positional argument but 2 were given`.

- [ ] **Step 3: Implement**

`_remote_oids` takes an optional runner and names its step:

```python
    def _remote_oids(self, keys: Sequence[str], git: _Git | None = None) -> dict[str, str]:
        """Read every present key's object ID with one ``ls-remote``."""
        git = self._git if git is None else git
        keys_by_ref = {self._ref(key): key for key in keys}
        proc = git(["ls-remote", self.repo_url, *keys_by_ref], step="naming the claim refs")
        ...  # rest unchanged
```

`list` gains `keys` and validates it before any git command:

```python
    def list(
        self,
        keys: Sequence[str] | None = None,
        *,
        timeout: float | None = None,
        progress: Callable[[str], None] | None = None,
    ) -> list[dict[str, Any]]:
        """Return all claim refs, or those of ``keys``, including malformed and expired entries.

        ...existing paragraphs...

        With ``keys``, only their refs are named, fetched and read, so neither
        the board's size nor changes to other claims affect the listing; a key
        without a claim ref is left out.

        ...timeout/progress paragraph from Task 2...
        """
        targets = None if keys is None else _validate_keys(keys)
        deadline = None if timeout is None else time.monotonic() + _validate_timeout(timeout)
        git = functools.partial(self._git, deadline=deadline, progress=progress)
        self._ensure_scratch(git)
        written: dict[str, dict[str, str] | None] = {}
        try:
            return self._read_listed(self._fetch_claims(written, git, targets), git)
        finally:
            # Deleting the private refs gets its own time limit, even after the deadline.
            for namespace, refs in written.items():
                self._delete_refs(namespace, refs)
```

`_fetch_claims` gains `targets` and a `name` function that says which keys to
fetch by name; the whole-board path is unchanged:

```python
    def _fetch_claims(
        self,
        written: dict[str, dict[str, str] | None],
        git: _Git,
        targets: tuple[str, ...] | None = None,
    ) -> dict[str, str]:
        """Fetch every claim ref, or those of ``targets``, into refs private to this call; return each claim's object ID, by key.

        ...existing docstring paragraphs...
        With ``targets``, only the present targets are fetched by name, and a
        target released meanwhile has the targets named again, never the board.
        """
        if targets is None:
            keys: list[str] | None = None

            def name() -> list[str]:
                return self._remote_keys(git)
        else:

            def name() -> list[str]:
                return list(self._remote_oids(targets, git))

            keys = name()
        failures = 0
        while True:
            if keys is not None and not keys:
                return {}
            ...  # loop body from Task 2, with both `keys = self._remote_keys(git)` lines replaced by `keys = name()`
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest -q tests/test_claims.py tests/test_claim_cli.py tests/test_dashboard.py`
Expected: all pass, including every existing whole-board listing test.

- [ ] **Step 5: Lint and commit**

Run: `make lint` (expected: clean), then:

```bash
git add autoform_cli/claims.py tests/test_claims.py
git commit -m "List only the claims a caller names

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: `claim list` targets, `--timeout`, labels and progress in the CLI

**Files:**
- Modify: `autoform_cli/__main__.py` (import at line 22; `claim list` parser at lines 378-379; `_claim` at lines 1497-1550; new `_claim_list` and `_warn_about_ref_locks` beside it)
- Test: `tests/test_claim_cli.py` (update the assertion at line 90-91; add tests)

**Interfaces:**
- Consumes: `ClaimBoard.list(keys, *, timeout, progress)`, `ClaimTimeoutError.step`, `ClaimContentionError`, `ClaimTransportError`, `author_claim_key`, `_positive_seconds`, `_claim_board`.
- Produces: CLI `autoform claim list [node_id ...] [--timeout SECONDS]`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_claim_cli.py`, change the existing missing-worker-id assertion
(lines 90-91) to read stderr:

```python
    assert main(["claim", "list", "--repo", str(repo), "--scratch", str(second)]) == 1
    assert "--worker-id" in capsys.readouterr().err
```

Append:

```python
def test_claim_cli_lists_only_the_named_targets(tmp_path: Path, capsys) -> None:
    repo = _bare_repo(tmp_path)
    scratch = tmp_path / "scratch"
    assert main(_args(repo, scratch, "acquire", "node-a", "node-b")) == 0
    capsys.readouterr()

    assert main(_args(repo, scratch, "list", "node-b", "node-absent")) == 0
    captured = capsys.readouterr()

    assert [lease["_key"] for lease in json.loads(captured.out)] == [author_claim_key("node-b")]
    assert captured.err == ""


def test_claim_cli_list_refuses_a_duplicate_target(tmp_path: Path, capsys) -> None:
    repo = _bare_repo(tmp_path)

    assert main(_args(repo, tmp_path / "scratch", "list", "node-a", "node-a")) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "error: duplicate claim target: node-a\n"


def test_claim_cli_list_labels_a_timeout(tmp_path: Path, capsys, monkeypatch) -> None:
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "protocol.ext.allow")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "always")
    args = ["claim", "list", "--repo", "ext::sleep 30", "--worker-id", "worker-a"]

    assert main([*args, "--scratch", str(tmp_path / "scratch"), "--timeout", "1"]) == 1
    captured = capsys.readouterr()

    assert captured.out == ""
    assert captured.err == (
        "error: timeout: no answer from the claim board within 1s while fetching the claim board\n"
    )


def test_claim_cli_list_labels_a_transport_failure(tmp_path: Path, capsys) -> None:
    missing = tmp_path / "missing" / "claims.git"

    assert main(_args(missing, tmp_path / "scratch", "list")) == 1
    captured = capsys.readouterr()

    assert captured.out == ""
    assert captured.err.startswith("error: transport: ")


def test_claim_cli_list_labels_contention(tmp_path: Path, capsys, monkeypatch) -> None:
    def contended(self: ClaimBoard, *args: object, **kwargs: object) -> list[dict[str, object]]:
        raise claims.ClaimContentionError("the claim board refused 3 fetches because claim refs kept moving")

    monkeypatch.setattr(ClaimBoard, "list", contended)

    assert main(_args(_bare_repo(tmp_path), tmp_path / "scratch", "list")) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == (
        "error: contention: the claim board refused 3 fetches because claim refs kept moving\n"
    )


def test_claim_cli_list_names_a_slow_step_on_stderr(tmp_path: Path, capsys, monkeypatch) -> None:
    seen: dict[str, object] = {}

    def slow(self: ClaimBoard, keys: object = None, *, timeout: object = None, progress=None) -> list[object]:
        seen.update(keys=keys, timeout=timeout)
        progress("fetching 1 claim refs")
        return []

    monkeypatch.setattr(ClaimBoard, "list", slow)

    assert main([*_args(_bare_repo(tmp_path), tmp_path / "scratch", "list", "node-a"), "--timeout", "7"]) == 0
    captured = capsys.readouterr()
    assert captured.out == "[]\n"
    assert captured.err == "claim list: fetching 1 claim refs...\n"
    assert seen == {"keys": [author_claim_key("node-a")], "timeout": 7.0}


def test_claim_cli_list_without_targets_passes_none_and_the_default_timeout(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    seen: dict[str, object] = {}

    def record(self: ClaimBoard, keys: object = None, *, timeout: object = None, progress=None) -> list[object]:
        seen.update(keys=keys, timeout=timeout)
        return []

    monkeypatch.setattr(ClaimBoard, "list", record)

    assert main(_args(_bare_repo(tmp_path), tmp_path / "scratch", "list")) == 0
    assert seen == {"keys": None, "timeout": 120.0}
```

`_args` puts the command words before `--repo`, so `"list", "node-a"` yields
`claim list node-a --repo ...`, which argparse accepts with `nargs="*"`.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest -q tests/test_claim_cli.py`
Expected: FAIL. argparse rejects `node-b` (`unrecognized arguments`, exit 2 via
`SystemExit`), the missing-worker-id error is on stdout, and there are no labels.

- [ ] **Step 3: Implement**

Import the new errors (line 22):

```python
from .claims import (
    CLAIM_TTL_S,
    ClaimBoard,
    ClaimContentionError,
    ClaimTimeoutError,
    ClaimTransportError,
    author_claim_key,
)
```

Replace the `claim list` parser lines (378-379):

```python
    claim_list = claim_subparsers.add_parser("list")
    claim_list.add_argument("node_id", nargs="*", help="list only these claim targets")
    _add_claim_board_arguments(claim_list)
    claim_list.add_argument(
        "--timeout",
        type=_positive_seconds,
        default=120.0,
        metavar="SECONDS",
        help="time limit for the whole listing (default: 120)",
    )
```

At the top of `_claim`, before its `try:`, add:

```python
    if args.claim_command == "list":
        return _claim_list(args)
```

and replace the `list`/`cleanup` branch inside `try:` with:

```python
        if operation == "cleanup":
            print(f"removed {board.cleanup()} expired claim(s)")
            _warn_about_ref_locks(board)
            return 0
```

Add after `_claim`:

```python
def _claim_list(args: argparse.Namespace) -> int:
    """List claims; stdout carries only the JSON, and a failure's line on stderr says what kind it is."""
    targets: dict[str, str] = {}
    for node_id in args.node_id:
        key = author_claim_key(node_id)
        if key in targets:
            print(f"error: duplicate claim target: {node_id}", file=sys.stderr)
            return 2
        targets[key] = node_id

    def progress(step: str) -> None:
        print(f"claim list: {step}...", file=sys.stderr, flush=True)

    try:
        board = _claim_board(args)
        leases = board.list(list(targets) or None, timeout=args.timeout, progress=progress)
    except ClaimTimeoutError as exc:
        print(
            f"error: timeout: no answer from the claim board within {args.timeout:g}s while {exc.step}",
            file=sys.stderr,
        )
        return 1
    except ClaimContentionError as exc:
        print(f"error: contention: {exc}", file=sys.stderr)
        return 1
    except ClaimTransportError as exc:
        print(f"error: transport: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(leases, sort_keys=True, separators=(",", ":")))
    _warn_about_ref_locks(board)
    return 0


def _warn_about_ref_locks(board: ClaimBoard) -> None:
    # Lock files are not refs, so neither list's nor cleanup's own output can show one.
    for lock in board.ref_locks():
        print(
            f"warning: {lock.describe()}; if no Git process is using the claim board, delete it",
            file=sys.stderr,
        )
```

`ClaimTimeoutError` and `ClaimContentionError` must be caught before
`ClaimTransportError`, their base class.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest -q tests/test_claim_cli.py tests/test_claims.py tests/test_dashboard.py tests/test_contract.py`
Expected: all pass. If `tests/test_contract.py` snapshots the CLI's help or
arguments and fails, update its expectation to include `node_id` and
`--timeout` for `claim list`, and nothing else.

- [ ] **Step 5: Lint and commit**

Run: `make lint` (expected: clean), then:

```bash
git add autoform_cli/__main__.py tests/test_claim_cli.py tests/test_contract.py
git commit -m "Let claim list take targets and a timeout, and label its failures

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Documentation, changelog, and the issue note

**Files:**
- Modify: `autoform_cli/README.md` (usage block near line 1245-1251; import-impact paragraph near line 1188-1191; claim contract near line 2451-2459)
- Modify: `skills/formalize/references/claims.md` (lines 30-32)
- Modify: `CHANGELOG.md` (under `## Unreleased`)
- Test: `tests/test_skill_examples.py`, `tests/test_contract.py`, full suite

**Interfaces:**
- Consumes: the CLI contract from Task 4.

- [ ] **Step 1: README usage block**

In the `bash` block after "Coordinate temporary cross-machine ownership
without modifying the book:", add as its last line:

```bash
autoform claim list af_5b0e4d3c2a1f09e8d7c6b5a4 af_0123456789abcdef01234567
```

- [ ] **Step 2: README import-impact paragraph**

Replace the sentence fragment
"`claim_keys` and `affected_claim_keys` match the JSON from
`autoform claim list --worker-id WORKER`."
with:

```markdown
`claim_keys` and `affected_claim_keys` match the `_key` fields of
`autoform claim list --worker-id WORKER TARGET...` given the corresponding
`claim_targets` or `affected_claim_targets`, which lists only those claims.
```

- [ ] **Step 3: README claim contract**

After the paragraph that begins "`claim list` copies the whole board with one
fetch" and ends "every acquire, renew, and release checks ownership again.",
add:

```markdown
`claim list TARGET...` lists only those targets' claims, in the same JSON; a
target without a claim is left out, and a duplicate target exits 2. It names
the targets' refs, fetches only those and reads their leases, so neither the
board's size nor changes to other claims affect it, and a target released
meanwhile has the targets named again, never the whole board. `--timeout
SECONDS`, 120 by default, bounds the whole listing, and a step still running
after five seconds is named on stderr as `claim list: <step>...`. A listing
that fails exits 1 with nothing on stdout and one line on stderr: `error:
timeout:` when the board did not answer in time, naming the step; `error:
contention:` when the board refused every fetch because claims kept moving; or
`error: transport:` for any other failure to reach or read the board. Claim
commands run Git without a terminal and with `GIT_TERMINAL_PROMPT=0`, so a
missing credential fails at once instead of waiting for a prompt, and a Git
command that runs out of time is ended together with everything it started.
```

- [ ] **Step 4: Formalize claims reference**

In `skills/formalize/references/claims.md`, replace
"Compare the import-impact report's claim keys with the JSON from
`autoform claim list --worker-id WORKER`:"
with:

```markdown
Compare the import-impact report's claim keys with the JSON from
`autoform claim list --worker-id WORKER` given its `affected_claim_targets`,
which lists only those claims:
```

Keep the rest of that paragraph unchanged. Do not change the whole-board
presence check in `skills/formalize/SKILL.md`.

- [ ] **Step 5: Changelog**

Under `## Unreleased` in `CHANGELOG.md`, add:

```markdown
- **Claims.** `claim list TARGET...` lists only those claims, whatever the
  rest of the board holds or does. `--timeout` (120 seconds by default) bounds
  a listing, a slow step is named on stderr, and a failure goes to stderr
  labelled `timeout:`, `contention:` or `transport:` with nothing on stdout.
  Claim commands no longer wait for a Git credential prompt, and a Git command
  that runs out of time no longer leaves its transport running (#432).
```

- [ ] **Step 6: Run the documentation and full checks**

Run: `make lint && make test`
Expected: clean lint; all tests pass (doc-checking tests such as
`tests/test_skill_examples.py` and `tests/test_contract.py` included). If a
doc-consistency test names a README or skill line, fix the wording it
reports, not the test.

- [ ] **Step 7: Commit**

```bash
git add autoform_cli/README.md skills/formalize/references/claims.md CHANGELOG.md
git commit -m "Document target-scoped, bounded claim listing

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 8: Draft the issue note (do not post)**

Write this draft for the human partner to post on #432, or to approve for
posting; posting is outward-facing and needs their go-ahead:

```markdown
#427 (merged after this issue was filed) already covers the batching and churn points:
`claim list` copies the board with one fetch into private refs and reads every lease with one
`cat-file --batch`; unrelated ref churn no longer restarts it, and the only retry left is for a
stateless protocol v0 server refusing a moved want (at most three fetches). On a local board with
3550 claim refs it takes about 1.6 s, cold or warm.

<this branch's PR> adds the rest:
- `claim list TARGET...` names, fetches and reads only those claims, unaffected by board size or
  other claims' churn, with the same JSON.
- `--timeout` (default 120 s) bounds a listing; a step still running after 5 s is named on stderr.
- Failures exit 1 with nothing on stdout and a labelled stderr line: `timeout:` (with the step),
  `contention:`, or `transport:`.
- Claim git commands run without a terminal and with `GIT_TERMINAL_PROMPT=0`, and a timed-out
  command's whole process group is killed.

Out of scope: an overall deadline for acquire/renew/release/cleanup, where killing a push leaves an
unknown outcome, and cleanup's one push per expired lease.
```

- [ ] **Step 9: Before opening a PR**

Drop the planning documents from the branch (the repository's guidance
discourages committed planning state):

```bash
git rm docs/superpowers/specs/2026-10-22-claim-list-targets-design.md docs/superpowers/plans/2026-10-22-claim-list-targets.md
git commit -m "Drop the claim list planning documents

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

Then read the full diff against `upstream/main` and list every removed
`def test_` line; none should be removed.
