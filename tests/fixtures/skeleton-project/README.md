# Skeleton fixture

A Mathlib-free Lean project for `tests/test_skeleton.py`, which copies it to a
temporary directory and builds it there, so the fixture itself is never
modified. Its `lean-toolchain` also names the toolchain CI's Lean jobs install
and the real-Lean gate in `tests/conftest.py` looks for, and several other
real-Lean tests copy or read it.
