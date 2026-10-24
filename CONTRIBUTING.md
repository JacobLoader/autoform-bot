# Contributing to autoform-bot

## Our Development Process
Development happens in this repository: changes reach `main` through pull
requests. You need Python 3.10 or newer, [`uv`](https://docs.astral.sh/uv/),
Git, and Make. From a clone:

```bash
make setup          # uv sync --extra dev --extra repl
make lint           # uv run ruff check autoform_cli servers tests
make test           # uv run pytest -q
make check-example  # validate, render, and build the bundled example site
```

CI ([`tests.yml`](.github/workflows/tests.yml) lists every job and its tests)
runs these steps on Python 3.10 and 3.13 for pull requests and for pushes to
`main` and to `scratch/` branches, which run CI without a pull request. CI sets
each `AUTOFORM_REQUIRE_*` variable below, so it fails where a local run skips:

- Browser tests skip without the `browser` extra and WebKit; `make test-browser`
  installs both and runs them as CI does (`AUTOFORM_REQUIRE_BROWSER_TESTS=1`).
- MathJax tests skip unless `AUTOFORM_MATHJAX_DIR` names an unpacked MathJax
  3.2.2 package, and the Node ones unless `node` is on `PATH`; CI's MathJax and
  WebKit jobs unpack it (`AUTOFORM_REQUIRE_MATHJAX_TESTS=1`).
- Lean tests skip without `lake` on `PATH`, and most without the toolchain in
  `tests/fixtures/skeleton-project/lean-toolchain`, which only the real-Lake
  test in `tests/test_project_inspect.py` lets elan download
  (`AUTOFORM_REQUIRE_REAL_LEAN_TESTS=1`).
- The Lean tests in `tests/test_library_generate.py` clone Batteries from GitHub
  and run only with `AUTOFORM_REQUIRE_REAL_LIBRARY_TESTS=1`.
- Run `lake build` in `skills/setup/assets/cabannes-thesis-project` when you
  change the example's Lean sources or declarations.

The kernel-trust probe `autoform_cli/probes/audit_probe.lean` has a verbatim
copy in `.github/autoform_audit.py`: edit the `.lean` file, then run
`python3 scripts/sync_audit_probe.py` to rewrite the template's and the bundled
example's copies. To check it without a project (silent when clean), run
`elan run "$(cat tests/fixtures/library-project/lean-toolchain)" lean
autoform_cli/probes/audit_probe.lean`.

`tests/test_real_repl.py` skips unless `AUTOFORM_RUN_REAL_REPL_TESTS=1`. To run
it locally, build its fixture and install the oldest supported toolchain first:

```bash
(cd tests/fixtures/repl-smoke && lake build Mathlib Secret @repl/repl)
elan toolchain install "$(cat tests/fixtures/minimum-lean/lean-toolchain)"
AUTOFORM_RUN_REAL_REPL_TESTS=1 uv run pytest -q tests/test_real_repl.py
```

## Pull Requests
We actively welcome your pull requests.

1. Fork the repo and create your branch from `main`.
2. If you've added code that should be tested, add tests.
3. If you've changed APIs, update the documentation.
4. Ensure the test suite passes.
5. Make sure your code lints.
6. If you haven't already, complete the Contributor License Agreement ("CLA").

## Contributor License Agreement ("CLA")
To accept your pull request, we need you to submit a CLA. You only need to do
this once to work on any of Meta's open source projects.

Complete your CLA here: <https://code.facebook.com/cla>

## Issues
We use GitHub issues to track public bugs. Please ensure your description is
clear and has sufficient instructions to be able to reproduce the issue.

Meta has a [bounty program](https://bugbounty.meta.com/) for the safe
disclosure of security bugs. In those cases, please go through the process
outlined on that page and do not file a public issue.

## Coding Style
* Python uses 4-space indentation and a 120-character line length
  (`[tool.ruff]`); `make lint` and CI run only ruff's default rules, which do
  not enforce them.
* There is no formatter: match the surrounding code and leave unrelated lines.

## License
By contributing to autoform-bot, you agree that your contributions will be licensed
under the LICENSE file in the root directory of this source tree.
