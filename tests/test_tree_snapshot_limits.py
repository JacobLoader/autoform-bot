from __future__ import annotations

import gc
import os
import stat
import sys
import threading
import weakref
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from autoform_cli import _tree_snapshot as tree_snapshot_module
from autoform_cli._tree_snapshot import (
    BoundDirectoryTree,
    OpaqueDirectoryMarker,
    TreeCaptureLimitError,
    TreeCaptureLimits,
    TreeChangedError,
    TreeSelection,
    TreeSnapshot,
    TreeSnapshotError,
    bind_directory_tree,
)
from tests.test_lean_sources import _require_descriptor_capture, _use_portable_capture


def _forbid_unbounded_listdir(monkeypatch: pytest.MonkeyPatch) -> None:
    """Disable streaming enumeration and fail if the capture falls back to `os.listdir`."""

    def unexpected_listdir(*_args, **_kwargs):
        raise AssertionError("unexpected unbounded os.listdir call")

    monkeypatch.setattr(tree_snapshot_module, "_DESCRIPTOR_SCANDIR_SUPPORTED", False)
    monkeypatch.setattr(tree_snapshot_module.os, "listdir", unexpected_listdir)


def _capture(
    root: Path,
    selection: TreeSelection,
    *,
    portable: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> TreeSnapshot:
    if portable:
        _use_portable_capture(monkeypatch)
    else:
        _require_descriptor_capture()
    with bind_directory_tree(root, selection=selection) as bound:
        return bound.capture()


def _all_entries(limits: TreeCaptureLimits) -> TreeSelection:
    return TreeSelection(
        include=lambda _path, _mode: True,
        descend=lambda _path: True,
        limits=limits,
    )


@pytest.mark.parametrize("portable", [False, True])
@pytest.mark.parametrize("marker_kind", ["file", "directory"])
def test_presence_marker_makes_a_nested_directory_opaque(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    portable: bool,
    marker_kind: str,
) -> None:
    root = tmp_path / "tree"
    worker = root / "worker"
    payload = worker / "payload"
    payload.mkdir(parents=True)
    (root / "kept").write_bytes(b"kept\n")
    (payload / "hidden").write_text("before\n", encoding="utf-8")
    marker = worker / ".git"
    if marker_kind == "file":
        marker.write_text("gitdir: before\n", encoding="utf-8")
    else:
        marker.mkdir()

    selection = TreeSelection(
        include=lambda _path, _mode: True,
        descend=lambda _path: True,
        record_omitted=False,
        opaque_markers=(
            OpaqueDirectoryMarker(
                ".git",
                0,
                lambda _data: False,
                presence_only=True,
            ),
        ),
    )
    before = _capture(root, selection, portable=portable, monkeypatch=monkeypatch)

    assert before.opaque_directories == ("worker",)
    assert before.files == (("kept", b"kept\n"),)
    assert all(not relative.startswith("worker/") for relative, _identity in before.identities)

    (payload / "hidden").write_text("after\n", encoding="utf-8")
    if marker_kind == "file":
        marker.write_text("gitdir: after\n", encoding="utf-8")
    else:
        (marker / "config").write_text("[core]\n", encoding="utf-8")
    after = _capture(root, selection, portable=portable, monkeypatch=monkeypatch)

    assert after.revision == before.revision
    assert after.generation_revision == before.generation_revision


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("max_entries", -1),
        ("max_depth", True),
        ("max_file_bytes", 1.5),
        ("max_total_bytes", "1"),
    ],
)
def test_capture_limits_reject_invalid_values(field: str, value: object) -> None:
    with pytest.raises(ValueError, match=field):
        TreeCaptureLimits(**{field: value})  # type: ignore[arg-type]


def test_capture_limits_are_frozen() -> None:
    limits = TreeCaptureLimits(max_entries=1)

    with pytest.raises(FrozenInstanceError):
        limits.max_entries = 2  # type: ignore[misc]


def test_capture_limit_error_exposes_a_stable_discriminator() -> None:
    error = TreeCaptureLimitError("max_entries", 3)

    assert error.limit == "max_entries"
    assert error.maximum == 3
    assert str(error) == "directory tree exceeds max_entries=3"


@pytest.mark.parametrize("portable", [False, True])
def test_capture_and_close_are_serialized(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    portable: bool,
) -> None:
    if portable:
        _use_portable_capture(monkeypatch)
    else:
        _require_descriptor_capture()
    root = tmp_path / "tree"
    root.mkdir()
    (root / "payload").write_bytes(b"payload")
    entered = threading.Event()
    release = threading.Event()
    close_started = threading.Event()
    closed = threading.Event()
    captured: list[TreeSnapshot] = []
    failures: list[BaseException] = []
    original_checkpoint = tree_snapshot_module._tree_snapshot_checkpoint

    def checkpoint(event: str, relative: str) -> None:
        original_checkpoint(event, relative)
        if event == "after-directory-list" and relative == "":
            entered.set()
            if not release.wait(5):
                raise AssertionError("capture test did not release its checkpoint")

    monkeypatch.setattr(tree_snapshot_module, "_tree_snapshot_checkpoint", checkpoint)
    bound = BoundDirectoryTree(root)

    def capture() -> None:
        try:
            captured.append(bound.capture())
        except BaseException as error:
            failures.append(error)

    def close() -> None:
        close_started.set()
        bound.close()
        closed.set()

    capture_thread = threading.Thread(target=capture)
    close_thread = threading.Thread(target=close)
    capture_thread.start()
    assert entered.wait(5)
    close_thread.start()
    try:
        assert close_started.wait(5)
        assert not closed.wait(0.1)
    finally:
        release.set()
        capture_thread.join(5)
        close_thread.join(5)

    assert failures == []
    assert len(captured) == 1
    assert not capture_thread.is_alive()
    assert not close_thread.is_alive()
    assert closed.is_set()


def test_portable_file_capture_accepts_windows_path_and_handle_stat_views(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "tree"
    root.mkdir()
    payload = root / "payload.cmd"
    payload.write_bytes(b"payload")
    original_fstat = tree_snapshot_module.os.fstat
    path_signature = tree_snapshot_module._stat_signature(os.lstat(payload))
    handle_signatures: list[tuple[int, ...]] = []
    inode_delta = 0

    class WindowsHandleStat:
        def __init__(self, metadata: os.stat_result) -> None:
            self.st_dev = metadata.st_dev
            self.st_ino = metadata.st_ino + inode_delta
            self.st_mode = metadata.st_mode ^ stat.S_IXUSR
            self.st_nlink = metadata.st_nlink
            self.st_size = metadata.st_size
            self.st_mtime_ns = metadata.st_mtime_ns
            self.st_ctime_ns = metadata.st_ctime_ns + 1

    def windows_handle_fstat(descriptor: int) -> WindowsHandleStat:
        metadata = WindowsHandleStat(original_fstat(descriptor))
        handle_signatures.append(tree_snapshot_module._stat_signature(metadata))
        return metadata

    monkeypatch.setattr(tree_snapshot_module.os, "fstat", windows_handle_fstat)
    monkeypatch.setattr(tree_snapshot_module, "_WINDOWS_STAT_VIEWS", True)

    snapshot = _capture(
        root,
        _all_entries(TreeCaptureLimits()),
        portable=True,
        monkeypatch=monkeypatch,
    )

    assert snapshot.files == (("payload.cmd", b"payload"),)
    assert handle_signatures
    assert handle_signatures[0][2] != path_signature[2]
    assert handle_signatures[0][6] != path_signature[6]
    assert (
        tree_snapshot_module._cross_interface_signature(handle_signatures[0])
        == tree_snapshot_module._cross_interface_signature(path_signature)
    )

    inode_delta = 1
    with pytest.raises(TreeSnapshotError, match="changed while it was captured"):
        _capture(
            root,
            _all_entries(TreeCaptureLimits()),
            portable=True,
            monkeypatch=monkeypatch,
        )


@pytest.mark.parametrize("portable", [False, True])
def test_invalid_selection_byte_limit_cannot_bypass_total_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    portable: bool,
) -> None:
    root = tmp_path / "tree"
    root.mkdir()
    (root / "payload").write_bytes(b"payload")
    selection = TreeSelection(
        include=lambda _path, _mode: True,
        descend=lambda _path: True,
        byte_limit=lambda _path: -2,
        limits=TreeCaptureLimits(max_total_bytes=1),
    )

    with pytest.raises(TreeSnapshotError, match="selection byte limit"):
        _capture(
            root,
            selection,
            portable=portable,
            monkeypatch=monkeypatch,
        )


@pytest.mark.parametrize("portable", [False, True])
def test_entry_limit_counts_ignored_and_placeholder_entries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    portable: bool,
) -> None:
    root = tmp_path / "tree"
    root.mkdir()
    (root / "ignored.bin").write_bytes(b"ignored")
    (root / "placeholder.bin").write_bytes(b"placeholder")

    def selection(max_entries: int) -> TreeSelection:
        return TreeSelection(
            include=lambda _path, _mode: False,
            descend=lambda _path: True,
            placeholder=lambda path, _mode: path.name == "placeholder.bin",
            limits=TreeCaptureLimits(
                max_entries=max_entries,
                max_file_bytes=0,
                max_total_bytes=0,
            ),
        )

    snapshot = _capture(
        root,
        selection(2),
        portable=portable,
        monkeypatch=monkeypatch,
    )

    assert snapshot.files == ()
    assert snapshot.placeholders == ("placeholder.bin",)
    assert snapshot.omitted == (("ignored.bin", "file"),)

    with pytest.raises(TreeCaptureLimitError, match="max_entries=1") as captured:
        _capture(
            root,
            selection(1),
            portable=portable,
            monkeypatch=monkeypatch,
        )
    assert captured.value.limit == "max_entries"
    assert captured.value.maximum == 1


@pytest.mark.parametrize("portable", [False, True])
def test_depth_limit_accepts_the_boundary_and_rejects_the_next_level(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    portable: bool,
) -> None:
    root = tmp_path / "tree"
    leaf = root / "one" / "two" / "leaf"
    leaf.parent.mkdir(parents=True)
    leaf.write_bytes(b"")

    snapshot = _capture(
        root,
        _all_entries(TreeCaptureLimits(max_depth=3)),
        portable=portable,
        monkeypatch=monkeypatch,
    )

    assert snapshot.files == (("one/two/leaf", b""),)

    with pytest.raises(TreeCaptureLimitError, match="max_depth=2") as captured:
        _capture(
            root,
            _all_entries(TreeCaptureLimits(max_depth=2)),
            portable=portable,
            monkeypatch=monkeypatch,
        )
    assert captured.value.limit == "max_depth"
    assert captured.value.maximum == 2


@pytest.mark.parametrize("portable", [False, True])
def test_file_byte_limit_accepts_the_boundary_and_rejects_one_more_byte(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    portable: bool,
) -> None:
    root = tmp_path / "tree"
    root.mkdir()
    payload = b"x" * (64 * 1024)
    (root / "payload").write_bytes(payload)

    snapshot = _capture(
        root,
        _all_entries(TreeCaptureLimits(max_file_bytes=len(payload))),
        portable=portable,
        monkeypatch=monkeypatch,
    )

    assert snapshot.files == (("payload", payload),)

    with pytest.raises(
        TreeCaptureLimitError,
        match=f"max_file_bytes={len(payload) - 1}",
    ) as captured:
        _capture(
            root,
            _all_entries(TreeCaptureLimits(max_file_bytes=len(payload) - 1)),
            portable=portable,
            monkeypatch=monkeypatch,
        )
    assert captured.value.limit == "max_file_bytes"
    assert captured.value.maximum == len(payload) - 1


@pytest.mark.parametrize("portable", [False, True])
def test_maximum_python_file_limit_does_not_overflow_the_reader(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    portable: bool,
) -> None:
    root = tmp_path / "tree"
    root.mkdir()
    (root / "payload").write_bytes(b"payload")

    snapshot = _capture(
        root,
        _all_entries(TreeCaptureLimits(max_file_bytes=sys.maxsize)),
        portable=portable,
        monkeypatch=monkeypatch,
    )

    assert snapshot.files == (("payload", b"payload"),)


@pytest.mark.parametrize("portable", [False, True])
def test_total_byte_limit_accepts_the_boundary_and_rejects_one_more_byte(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    portable: bool,
) -> None:
    root = tmp_path / "tree"
    root.mkdir()
    (root / "a").write_bytes(b"12")
    (root / "b").write_bytes(b"345")

    snapshot = _capture(
        root,
        _all_entries(TreeCaptureLimits(max_total_bytes=5)),
        portable=portable,
        monkeypatch=monkeypatch,
    )

    assert snapshot.files == (("a", b"12"), ("b", b"345"))
    reader_name = "_read_portable_file" if portable else "_read_file"
    original_reader = getattr(tree_snapshot_module, reader_name)
    read_paths: list[str] = []

    def record_read(*args, **kwargs):
        path = args[0] if portable else args[1]
        read_paths.append(Path(path).name)
        return original_reader(*args, **kwargs)

    monkeypatch.setattr(tree_snapshot_module, reader_name, record_read)

    with pytest.raises(TreeCaptureLimitError, match="max_total_bytes=4") as captured:
        _capture(
            root,
            _all_entries(TreeCaptureLimits(max_total_bytes=4)),
            portable=portable,
            monkeypatch=monkeypatch,
        )

    assert read_paths == ["a"]
    assert captured.value.limit == "max_total_bytes"
    assert captured.value.maximum == 4


@pytest.mark.parametrize("portable", [False, True])
def test_selection_and_capture_byte_limits_compose_on_retained_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    portable: bool,
) -> None:
    root = tmp_path / "tree"
    root.mkdir()
    (root / "payload").write_bytes(b"0123456789")

    def selection(max_file_bytes: int) -> TreeSelection:
        return TreeSelection(
            include=lambda _path, _mode: True,
            descend=lambda _path: True,
            byte_limit=lambda _path: 2,
            limits=TreeCaptureLimits(max_file_bytes=max_file_bytes),
        )

    snapshot = _capture(
        root,
        selection(3),
        portable=portable,
        monkeypatch=monkeypatch,
    )

    assert snapshot.files == (("payload", b"012"),)

    with pytest.raises(TreeCaptureLimitError) as captured:
        _capture(
            root,
            selection(2),
            portable=portable,
            monkeypatch=monkeypatch,
        )
    assert captured.value.limit == "max_file_bytes"
    assert captured.value.maximum == 2


def test_file_read_cap_does_not_trust_an_underreported_size() -> None:
    budget = tree_snapshot_module._CaptureBudget(TreeCaptureLimits())

    assert budget.file_read_limit(0, None) is None
    assert budget.file_read_limit(0, 10) == 10


@pytest.mark.parametrize("portable", [False, True])
def test_oversized_file_is_rejected_before_its_reader_runs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    portable: bool,
) -> None:
    root = tmp_path / "tree"
    root.mkdir()
    (root / "payload").write_bytes(b"1234")
    reader_name = "_read_portable_file" if portable else "_read_file"

    def unexpected_read(*_args, **_kwargs):
        raise AssertionError("an oversized file must not be opened for reading")

    monkeypatch.setattr(tree_snapshot_module, reader_name, unexpected_read)

    with pytest.raises(TreeSnapshotError, match="max_file_bytes=3"):
        _capture(
            root,
            _all_entries(TreeCaptureLimits(max_file_bytes=3)),
            portable=portable,
            monkeypatch=monkeypatch,
        )


@pytest.mark.parametrize(
    "limits",
    [
        TreeCaptureLimits(max_entries=1),
        TreeCaptureLimits(max_depth=1),
    ],
)
def test_descriptor_fallback_fails_before_unbounded_listdir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    limits: TreeCaptureLimits,
) -> None:
    _require_descriptor_capture()
    root = tmp_path / "tree"
    root.mkdir()
    (root / "payload").write_bytes(b"payload")
    _forbid_unbounded_listdir(monkeypatch)

    with pytest.raises(TreeSnapshotError, match="bounded directory enumeration"):
        _capture(
            root,
            _all_entries(limits),
            portable=False,
            monkeypatch=monkeypatch,
        )


def test_descriptor_and_portable_limits_capture_the_same_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _require_descriptor_capture()
    root = tmp_path / "tree"
    (root / "nested").mkdir(parents=True)
    (root / "nested" / "included").write_bytes(b"data")
    (root / "ignored").write_bytes(b"ignored")
    (root / "placeholder").write_bytes(b"placeholder")
    limits = TreeCaptureLimits(
        max_entries=4,
        max_depth=2,
        max_file_bytes=4,
        max_total_bytes=4,
    )
    selection = TreeSelection(
        include=lambda path, _mode: path.name == "included",
        descend=lambda _path: True,
        placeholder=lambda path, _mode: path.name == "placeholder",
        limits=limits,
    )

    descriptor_snapshot = _capture(
        root,
        selection,
        portable=False,
        monkeypatch=monkeypatch,
    )
    with monkeypatch.context() as portable_context:
        portable_snapshot = _capture(
            root,
            selection,
            portable=True,
            monkeypatch=portable_context,
        )

    assert descriptor_snapshot == portable_snapshot


def test_portable_capture_sanitizes_unsupported_reparse_points(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "tree"
    root.mkdir()
    payload = root / "opaque-entry"
    payload.write_bytes(b"payload")
    identity = (payload.stat().st_dev, payload.stat().st_ino)
    original_reparse = tree_snapshot_module._is_reparse_point

    def is_reparse(metadata) -> bool:
        return (metadata.st_dev, metadata.st_ino) == identity or original_reparse(
            metadata
        )

    def unsupported_readlink(_path) -> str:
        raise ValueError("private unsupported reparse tag")

    _use_portable_capture(monkeypatch)
    monkeypatch.setattr(tree_snapshot_module, "_is_reparse_point", is_reparse)
    monkeypatch.setattr(tree_snapshot_module.os, "readlink", unsupported_readlink)

    with pytest.raises(
        TreeSnapshotError,
        match="directory tree contains an unsupported reparse point",
    ) as caught:
        with bind_directory_tree(root) as bound:
            bound.capture()

    assert "private" not in str(caught.value)


@pytest.mark.parametrize("portable", [False, True])
def test_capture_releases_its_state_without_cyclic_gc(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    portable: bool,
) -> None:
    root = tmp_path / "tree"
    root.mkdir()
    (root / "payload").write_bytes(b"payload")
    selection = _all_entries(TreeCaptureLimits())
    # Capture state left in a reference cycle would keep the selection, and so
    # its include callable, alive until the cyclic collector runs.
    released = weakref.ref(selection.include)

    enabled = gc.isenabled()
    gc.disable()
    try:
        snapshot = _capture(root, selection, portable=portable, monkeypatch=monkeypatch)
        del selection
        assert released() is None
    finally:
        if enabled:
            gc.enable()

    assert snapshot.files == (("payload", b"payload"),)


def _selected_sources(
    *,
    markers: tuple[OpaqueDirectoryMarker, ...] = (),
) -> TreeSelection:
    return TreeSelection(
        include=lambda path, _mode: path.suffix == ".src",
        descend=lambda _path: True,
        record_omitted=False,
        opaque_markers=markers,
        unselected_may_change=True,
    )


def _at_final_verification(monkeypatch: pytest.MonkeyPatch, action) -> None:
    original = tree_snapshot_module._tree_snapshot_checkpoint

    def checkpoint(name: str, path: str) -> None:
        original(name, path)
        if name == "before-final-verification":
            action()

    monkeypatch.setattr(tree_snapshot_module, "_tree_snapshot_checkpoint", checkpoint)


def test_selected_capture_requires_no_omitted_records() -> None:
    with pytest.raises(ValueError, match="record_omitted=False"):
        TreeSelection(
            include=lambda _path, _mode: True,
            descend=lambda _path: True,
            unselected_may_change=True,
        )


def test_selected_capture_refuses_portable_traversal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "a.src").write_bytes(b"a\n")

    with pytest.raises(TreeSnapshotError, match="directory-descriptor traversal"):
        _capture(tmp_path, _selected_sources(), portable=True, monkeypatch=monkeypatch)


@pytest.mark.parametrize(("folder", "expected"), [("", "."), ("sub", "sub")])
def test_strict_selection_still_rejects_unselected_churn(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    folder: str,
    expected: str,
) -> None:
    _require_descriptor_capture()
    parent = tmp_path / folder if folder else tmp_path
    parent.mkdir(exist_ok=True)
    (parent / "notes.md").write_bytes(b"0\n")

    def save() -> None:
        (parent / "notes.md.tmp").write_bytes(b"1\n")

    _at_final_verification(monkeypatch, save)

    with pytest.raises(TreeChangedError) as error:
        _capture(tmp_path, _all_entries(TreeCaptureLimits()), portable=False, monkeypatch=monkeypatch)

    assert error.value.relative == expected


def test_selected_capture_ignores_unselected_churn(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _require_descriptor_capture()
    (tmp_path / "kept.src").write_bytes(b"kept\n")
    (tmp_path / "out" / "deep").mkdir(parents=True)
    (tmp_path / "out" / "deep" / "page.html").write_bytes(b"0\n")

    def rebuild() -> None:
        (tmp_path / "out" / "deep" / "page.html").unlink()
        (tmp_path / "out" / "deep").rmdir()
        (tmp_path / "out" / "fresh").mkdir()
        (tmp_path / "notes.md.tmp").write_bytes(b"1\n")

    _at_final_verification(monkeypatch, rebuild)

    snapshot = _capture(tmp_path, _selected_sources(), portable=False, monkeypatch=monkeypatch)

    assert snapshot.directories == ("",)
    assert snapshot.files == (("kept.src", b"kept\n"),)
    assert snapshot.omitted == ()


def test_selected_capture_relist_uses_the_selection_limits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _require_descriptor_capture()
    (tmp_path / "kept.src").write_bytes(b"kept\n")
    (tmp_path / "notes.md").write_bytes(b"0\n")
    selection = TreeSelection(
        include=lambda path, _mode: path.suffix == ".src",
        descend=lambda _path: True,
        record_omitted=False,
        unselected_may_change=True,
        limits=TreeCaptureLimits(max_entries=2),
    )

    snapshot = _capture(tmp_path, selection, portable=False, monkeypatch=monkeypatch)
    assert snapshot.files == (("kept.src", b"kept\n"),)

    # The scan lists two entries.  A temporary file that exists only while
    # the folder is relisted pushes that relist over max_entries; the final
    # verification sees two entries again.
    original = tree_snapshot_module._tree_snapshot_checkpoint
    temporary = tmp_path / "notes.md.tmp"

    def checkpoint(name: str, path: str) -> None:
        original(name, path)
        if name == "after-directory-list" and path == "":
            temporary.write_bytes(b"1\n")
        elif name == "before-final-verification":
            temporary.unlink(missing_ok=True)

    monkeypatch.setattr(tree_snapshot_module, "_tree_snapshot_checkpoint", checkpoint)

    with pytest.raises(TreeChangedError) as error:
        _capture(tmp_path, selection, portable=False, monkeypatch=monkeypatch)

    assert error.value.relative == "."


@pytest.mark.parametrize("holds_selected_entry", [False, True])
def test_verification_recognizes_markers_like_the_scan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    holds_selected_entry: bool,
) -> None:
    _require_descriptor_capture()
    (tmp_path / "kept.src").write_bytes(b"kept\n")
    folder = tmp_path / "X"
    folder.mkdir()
    (folder / "m.json").write_bytes(b"no")
    if holds_selected_entry:
        (folder / "inner.src").write_bytes(b"inner\n")
    selection = _selected_sources(
        markers=(OpaqueDirectoryMarker("m.json", 16, lambda data: data == b"ok"),),
    )

    snapshot = _capture(tmp_path, selection, portable=False, monkeypatch=monkeypatch)
    assert ("X" in snapshot.directories) is holds_selected_entry
    assert snapshot.opaque_directories == ()

    def add_late_entry() -> None:
        (folder / "late.src").write_bytes(b"late\n")

    def recognize() -> None:
        (folder / "m.json").write_bytes(b"ok")
        add_late_entry()

    changes = [recognize]
    _at_final_verification(monkeypatch, lambda: changes[0]())
    if not holds_selected_entry:
        # An unrecognized marker name hides nothing: a selected entry that
        # appears beside it is a change.
        changes[0] = add_late_entry
        with pytest.raises(TreeChangedError) as error:
            _capture(tmp_path, selection, portable=False, monkeypatch=monkeypatch)
        assert error.value.relative == "X/late.src"
        (folder / "late.src").unlink()
        # A folder that holds nothing selected may become hidden by a marker
        # the walk recognizes from its bytes, as the scan does; it then
        # contributes nothing, whatever it holds.
        changes[0] = recognize
        snapshot = _capture(tmp_path, selection, portable=False, monkeypatch=monkeypatch)
        assert snapshot.directories == ("",)
        assert snapshot.files == (("kept.src", b"kept\n"),)
        assert snapshot.opaque_directories == ()
        return

    # A marker that now hides recorded selected entries is a change.
    with pytest.raises(TreeChangedError) as error:
        _capture(tmp_path, selection, portable=False, monkeypatch=monkeypatch)

    assert error.value.relative == "X"
