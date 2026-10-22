# Bounded, target-scoped `claim list`

Issue: #432 (tracker #429, evidence #426 section 1).

## Outcome

A worker checking whether a few claims are held gets a fast answer about only
those claims, whatever happens elsewhere on the board, and a listing that
cannot finish says so within a bound and says why. Nothing about ownership
changes: compare-and-swap pushes, all-or-nothing batches, malformed-ref
refusal, the live/expired distinction, and the absence of stealing stay as
they are.

## Already delivered

PR #427 merged after the issue was filed and removed most of the reported cost.
`claim list` copies the board with one fetch into refs private to the call and
reads every lease with one `cat-file --batch`; unrelated ref churn no longer
restarts it, and the only remaining retry is for a stateless protocol v0 server
refusing a moved want, at most three fetches. On a local board with 3550 claim
refs it takes about 1.6 s, cold or warm. The "claim refs changed during each of
3 attempts" error the issue quotes no longer exists. The issue comment closing
those points is part of this work.

## Remaining gaps

1. No supported target-scoped read. Formalize's import-edit rules and
   `work import-impact` tell workers to compare claim keys against the whole
   board's JSON, which on a large board is a large blob in an agent's context.
2. No overall bound. Each git call has its own 120 s timeout, so a stalled
   transport can keep `claim list` silent for minutes. Git is never told not to
   prompt: claim git commands inherit the terminal, so `ssh` can wait on
   `/dev/tty`, and on a timeout `subprocess.run` kills `git` but leaves its
   transport helpers (`ssh`, `git-remote-https`) running.
3. Indistinguishable failures. A timeout, a transport failure and a contended
   fetch all print `error: <text>` on stdout and exit 1.

## Contract

### `autoform claim list [TARGET...] [--timeout SECONDS]`

- Without targets, the output is exactly today's.
- Each target is a claim target, hashed with `author_claim_key` as `acquire`
  does. The output is the same JSON array, with the same entry fields,
  restricted to those keys. A target with no claim ref is absent from the
  output, which means unclaimed, as an absent entry does in a full listing.
- A target given twice exits 2 with `error: duplicate claim target: <target>`,
  as `acquire` does.
- `--timeout` is one deadline for the whole command, default 120 seconds.
  Each git subprocess gets the smaller of its usual 120 s and what remains.
- Lock-file warnings on stderr are unchanged, with or without targets.

### Failures

Every failure still exits 1. For `claim list` only, the message moves from
stdout to stderr, so stdout carries nothing but JSON, and begins with one of
three documented labels:

- `error: timeout: no answer from the claim board within <N>s while <step>`
- `error: transport: <reason>`: any other failure to reach or read the board,
  including a missing credential.
- `error: contention: <reason>`: the board refused the fetch on every attempt
  because claim refs kept moving (a stateless protocol v0 server's "not our
  ref", or a named target released between naming and fetching it).

Usage errors, such as a missing `--worker-id` or a duplicate target, are not
board failures and carry no label. `acquire`, `renew`, `release` and `cleanup`
keep their current messages and channels.

### Progress

When a step is still running after 5 seconds, `claim list` prints one line on
stderr naming it, for example `claim list: fetching 3 claim refs...`. A listing
that finishes sooner prints nothing extra. Steps: preparing the scratch,
naming the targets' refs, fetching the board or N claim refs, reading N leases.

### No prompts

Every claim git command, including those of `acquire`, `renew`, `release` and
`cleanup`, runs with `GIT_TERMINAL_PROMPT=0`, without a controlling terminal,
and with stdin from the null device unless it is given input, so a missing
credential fails at once as a transport error instead of waiting on a prompt.

## Design

### Claims runner

`ClaimBoard._git` keeps its signature and gains an optional `deadline` (a
`time.monotonic()` value) and `step` (a phrase for messages). It starts git
with `subprocess.Popen` in a new session on POSIX (`start_new_session=True`),
or a new process group on Windows (`CREATE_NEW_PROCESS_GROUP`), adds
`GIT_TERMINAL_PROMPT=0` to `_GIT_ENV`, and waits with
`communicate(timeout=...)`.

- The wait is the smaller of 120 s and the time left before `deadline`.
- When a progress callback is given, the first wait is at most 5 s; if it
  expires, the callback receives the step once and the wait resumes for the
  remainder (`communicate` may be called again after `TimeoutExpired`).
- On expiry it kills the process group (`os.killpg(..., SIGKILL)` on POSIX,
  `Popen.kill` on Windows), reaps git, and raises `ClaimTimeoutError` when a
  deadline was the binding limit, otherwise `ClaimTransportError` as today.
- A deadline already passed raises `ClaimTimeoutError` without starting git.

This is deliberately smaller than skeleton's `_run_bounded_command`, whose
signal routing, output caps and descendant census serve long Lean probes; git
transports run as one process group that a group kill ends. Mutating commands
pass no deadline, so a push is never cut short by `--timeout` and its outcome
is never newly unknown.

### Errors

- `ClaimTimeoutError(ClaimTransportError)`, with a `step` attribute.
- `ClaimContentionError(ClaimTransportError)`.

Both subclass the existing error, so every current `except
ClaimTransportError`, including the dashboard's, keeps working.

### `ClaimBoard.list(keys=None, *, timeout=None, progress=None)`

The deadline and progress callback are passed down to the private helpers as
arguments, never stored on the board, because the dashboard calls `list()` from
a server thread.

- Without `keys`, the flow is today's.
- With `keys` (validated with `_validate_keys`): one `ls-remote` naming exactly
  those refs (`_remote_oids`). If none is present the result is empty.
  Otherwise one fetch of only the present refs into private numbered refs,
  through the by-name mode `_fetch_claims` already has, then one
  `cat-file --batch` through `_read_listed`. If the fetch fails because a named
  ref is gone, only the targets are named again, never the whole board.
  `_fetch_claims` takes the function that names the refs to fetch:
  `_remote_keys` for the whole board, the targets' `_remote_oids` otherwise.
- When fetch attempts run out on a retryable failure, `_fetch_claims` raises
  `ClaimContentionError`; any other fetch failure stays `ClaimTransportError`.
- Private refs are deleted in the existing `finally`, also after a timeout.
  Deleting them gets a fresh 120 s per-call limit rather than the spent
  deadline, and its failure never replaces the listing's own error.

### CLI

`claim list` gains `node_id` (`nargs="*"`) and `--timeout` (`_positive_seconds`,
default 120). The handler rejects duplicate targets with exit 2, passes a
progress callback writing to stderr, and maps `ClaimTimeoutError`,
`ClaimContentionError` and `ClaimTransportError` to the three labels on
stderr. `MalformedLeaseError` never escapes `list`, which reports malformed
refs as entries.

### Documentation

- `autoform_cli/README.md`: the claim contract's `claim list` paragraph and
  the import-impact paragraph that points at `claim list` describe targets,
  `--timeout`, the labels, progress and prompt-free git.
- `skills/formalize/references/claims.md`: compare the import-impact report's
  `affected_claim_targets` with `autoform claim list --worker-id WORKER
  <targets>` instead of the whole board. The Formalize `SKILL.md` presence
  check keeps the whole-board listing, which is what it needs.
- A comment on #432 records what #427 delivered and what this change adds.

## Out of scope

- An overall deadline for `acquire`, `renew`, `release` and `cleanup`: killing
  a push mid-flight leaves an unknown outcome, which must never be retried and
  needs its own design.
- `cleanup`'s one push per expired lease.
- A per-target status vocabulary (free, live, expired, malformed) beyond the
  existing entry fields.

## Testing

Test-first, against real bare boards in `tmp_path` as `tests/test_claims.py`
and `tests/test_claim_cli.py` do.

- Targeted listing returns only the named targets, with entries equal to the
  full listing's, and omits absent ones.
- Its git command count does not grow with board size, and its fetch refspecs
  name only targets.
- A peer thread renewing an unrelated claim in a loop does not make it retry.
- A target released between naming and fetching is named again from the
  targets only and left out of the result.
- Repeated "not our ref" refusals raise `ClaimContentionError`; other fetch
  failures stay plain transport errors.
- A git command that hangs (a transport that sleeps) ends within the timeout
  plus a small margin, raises `ClaimTimeoutError` naming the step, and leaves
  no process of its group running; the private refs are gone afterwards.
- Claim git commands see `GIT_TERMINAL_PROMPT=0` and have no controlling
  terminal.
- With the progress threshold patched down, a slow step prints one stderr
  line; a fast listing prints none.
- CLI: each label exits 1 with empty stdout; a duplicate target exits 2;
  listing without targets prints exactly today's output.
- The runner's timeout and process-group tests are added to the explicit
  Windows test list in `.github/workflows/tests.yml`.
- Existing claim, claim CLI and dashboard suites pass unchanged, and
  `make lint` and `make test` pass.
