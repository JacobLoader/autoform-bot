#!/usr/bin/env python3
"""Copy the audit probe's Lean source into the helper that `autoform init` writes.

The helper must stay one self-contained file, so it carries the probe as a raw
string. Edit autoform_cli/probes/audit_probe.lean, then run this from anywhere:
it rewrites that string in autoform_cli/templates/github/autoform_audit.py and
copies the helper to the bundled example, which mirrors it byte for byte.
"""

from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_SOURCE = _ROOT / "autoform_cli/probes/audit_probe.lean"
_HELPER = _ROOT / "autoform_cli/templates/github/autoform_audit.py"
_EXAMPLE = _ROOT / "skills/setup/assets/cabannes-thesis-project/.github/autoform_audit.py"
_START = '_PROBE = r"""'
_END = '"""'


def main() -> int:
    probe = _SOURCE.read_text(encoding="utf-8")
    if _END in probe or not probe.endswith("\n"):
        print(f"error: {_SOURCE} must end with a newline and hold no {_END}, so a raw string can carry it")
        return 1
    helper = _HELPER.read_text(encoding="utf-8")
    start = helper.index(_START) + len(_START)
    end = helper.index(_END, start)
    # Rewriting the files in place keeps their executable mode.
    with _HELPER.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(helper[:start] + probe + helper[end:])
    _EXAMPLE.write_bytes(_HELPER.read_bytes())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
