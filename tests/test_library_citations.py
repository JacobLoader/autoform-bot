from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from autoform_cli.__main__ import main
from autoform_cli.library.citations import cited_sources
from tests.library_fixture import declaration, make_library
from tests.test_search import _article

_THEOREM = "Nat.threeSquareRepresentationCount_eq_threeSquareRepresentationCount_div_four"
_MORTENSON = "DOI 10.1007/s00222-012-0383-5"
_GAUSS = "- [Gauss](https://arxiv.org/abs/2307.05244v2)"


@pytest.mark.parametrize(
    ("text", "source"),
    [
        ("Source: arXiv:2307.05244 `main.tex` lines 191-199", "arXiv 2307.05244"),
        ("arXiv 2307.05244v3", "arXiv 2307.05244"),
        ("arXiv `2311.13047v1`", "arXiv 2311.13047"),
        ("arXiv:1407.1234v2", "arXiv 1407.1234"),
        ("_arXiv:2307.05244_", "arXiv 2307.05244"),
        ("| arXiv | 2307.05244 |", "arXiv 2307.05244"),
        ("https://arxiv.org/abs/2307.05244v2", "arXiv 2307.05244"),
        ("https://arxiv.org/abs/2307.05244/", "arXiv 2307.05244"),
        ("http://arxiv.org/pdf/2307.05244v1.pdf", "arXiv 2307.05244"),
        ("https://export.arxiv.org/e-print/2209.11629", "arXiv 2209.11629"),
        ("https://arxiv.org/html/2307.05244v1", "arXiv 2307.05244"),
        ("https://doi.org/10.48550/arXiv.2307.05244", "arXiv 2307.05244"),
        ("doi:10.48550/arXiv.2307.05244v1", "arXiv 2307.05244"),
        ("arXiv:math.AG/0210149v2", "arXiv math/0210149"),
        ("https://arxiv.org/abs/math/0210149", "arXiv math/0210149"),
        ("doi:10.1007/S00222-012-0383-5.", _MORTENSON),
        ("DOI: 10.1007/s00222-012-0383-5", _MORTENSON),
        ("**DOI:** 10.1007/s00222-012-0383-5", _MORTENSON),
        ("| DOI | 10.1007/s00222-012-0383-5 |", _MORTENSON),
        ("*doi:10.1007/s00222-012-0383-5*", _MORTENSON),
        ("https://doi.org/10.1007/s00222-012-0383-5?via=ihub", _MORTENSON),
        ("(see https://dx.doi.org/10.1007%2Fs00222-012-0383-5)", _MORTENSON),
        ("[doi:10.1007/s00222-012-0383-5](https://doi.org/10.1007/s00222-012-0383-5).", _MORTENSON),
        ("[paper](https://doi.org/10.1016/0001-8708(77)90004-3)", "DOI 10.1016/0001-8708(77)90004-3"),
    ],
)
def test_a_paper_is_one_source_in_each_of_its_usual_spellings(text: str, source: str) -> None:
    assert cited_sources(text) == {source}


@pytest.mark.parametrize(
    "text", ["2307.05244", "an arXiv preprint", "arXiv:2307.052449", "10.1007/s00222-012-0383-5", "xarXiv:2307.05244"]
)
def test_a_number_without_its_arxiv_or_doi_label_cites_nothing(text: str) -> None:
    assert cited_sources(text) == frozenset()


def _consumer(
    tmp_path: Path,
    *,
    sources: str = _GAUSS,
    docstring: str | None = "Source: arXiv:2307.05244 `main.tex` lines 191-199.",
    module_doc: str | None = None,
    articles: int = 1,
    status: str = "complete",
    proved: bool = False,
    stated: bool = False,
    declarations: tuple | None = None,
) -> Path:
    # The blueprint and the Lake project share one root, as in a real consumer.
    library = make_library(
        tmp_path,
        declarations=declarations or (declaration(_THEOREM, status=status, docstring=docstring),),
        module_docs={"Lib.Convex": module_doc} if module_doc else None,
    )
    _article(library.project, "README.md", title="Three squares")
    for number in range(articles):
        lean = ("declaration: theorem", "statement: formalized", f"lean: Project.step{number}")
        _article(
            library.project,
            f"step-{number}.md",
            title=f"Step {number}",
            body=f"A step of the proof.\n\n## Sources\n\n{sources}",
            metadata=(
                f"article_id: af_{number:024x}",
                *(lean if proved or stated else ()),
                *(("proof: formalized",) if proved else ()),
            ),
        )
        if proved or stated:
            with (library.project / "Project.lean").open("a", encoding="utf-8") as file:
                file.write(f"theorem Project.step{number} : True := trivial\n")
    return library.project


def _check(project: Path, capsys: pytest.CaptureFixture[str]) -> tuple[int, list[str]]:
    status = main(["check", str(project / "blueprint"), "--lean-root", str(project)])
    return status, [line for line in capsys.readouterr().out.splitlines() if line.startswith("warning:")]


def _warning(name: str = _THEOREM, source: str = "arXiv 2307.05244", reach: str = "1 unproved article reaches") -> str:
    return (
        f"warning: library atlas: {name}'s docstring cites {source}, which {reach}, including step-0; no "
        "implementation note, source page or project Lean file names it, so reuse it or record why it does not apply"
    )


def _note(project: Path, text: str, number: int = 0) -> None:
    notes = project / "blueprint/.implementation-notes"
    notes.mkdir(exist_ok=True)
    (notes / f"af_{number:024x}.md").write_text(text, encoding="utf-8")


def test_check_warns_about_a_library_result_citing_the_paper_until_a_note_or_lean_file_names_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project = _consumer(tmp_path)
    assert _check(project, capsys) == (0, [_warning()])

    _note(project, f"Reuse `{_THEOREM}` from ATLAS.\n")
    assert _check(project, capsys) == (0, [])

    (project / "blueprint/.implementation-notes" / f"af_{0:024x}.md").unlink()
    # After `open Nat` the project names it by its last component alone.
    (project / "Project.lean").write_text(
        "open Nat\n\nexample := threeSquareRepresentationCount_eq_threeSquareRepresentationCount_div_four\n",
        encoding="utf-8",
    )
    assert _check(project, capsys) == (0, [])


@pytest.mark.parametrize("text", ["Reuse {name}'s proof.", "Does {name}? apply", "{name} does not apply."])
def test_a_note_names_a_declaration_in_prose(tmp_path: Path, capsys: pytest.CaptureFixture[str], text: str) -> None:
    project = _consumer(tmp_path)
    _note(project, text.format(name=_THEOREM) + "\n")

    assert _check(project, capsys) == (0, [])


def test_a_note_must_write_the_full_name(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    project = _consumer(tmp_path)
    _note(project, "Reuse threeSquareRepresentationCount_eq_threeSquareRepresentationCount_div_four.\n")

    assert _check(project, capsys) == (0, [_warning()])


def test_a_note_naming_a_longer_declaration_does_not_name_this_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project = _consumer(tmp_path)
    _note(project, f"Reuse `{_THEOREM}_aux`, then finish.\n")

    assert _check(project, capsys) == (0, [_warning()])


def test_a_source_page_records_a_declaration_that_does_not_apply_for_every_article(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project = _consumer(tmp_path, sources="- [Gauss, Theorem 2](../sources/gauss.md#theorem-2)", articles=2)
    page = project / "blueprint/sources/gauss.md"
    page.parent.mkdir(parents=True)
    page.write_text("# Gauss\n\narXiv:2307.05244.\n\n## Theorem 2\n\nLines 191-199.\n", encoding="utf-8")
    assert _check(project, capsys) == (0, [_warning(reach="2 unproved articles reach")])

    # Unlike an implementation note, the page stays once an article is proved.
    page.write_text(page.read_text(encoding="utf-8") + f"\n`{_THEOREM}` states r(n) only for n > 0.\n")
    assert _check(project, capsys) == (0, [])


def test_a_source_page_an_article_links_counts_with_what_it_cites(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project = _consumer(
        tmp_path,
        sources="- [Mortenson, Theorem 2](../sources/mortenson.md#theorem-2)",
        docstring="After https://doi.org/10.1007/s00222-012-0383-5.",
    )
    page = project / "blueprint/sources/mortenson.md"
    page.parent.mkdir(parents=True)
    page.write_text(
        "# Mortenson\n\nPublished as [doi:10.1007/s00222-012-0383-5](https://doi.org/10.1007/s00222-012-0383-5).\n\n"
        "## Theorem 2\n\nLines 127-131.\n",
        encoding="utf-8",
    )

    assert _check(project, capsys) == (0, [_warning(source=_MORTENSON)])


def test_a_module_docstring_citing_the_paper_warns_once_for_the_module(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    helpers = tuple(declaration(f"Lib.Convex.helper{letter}", docstring="A helper.") for letter in "ABCD")
    project = _consumer(tmp_path, declarations=helpers, module_doc="Gauss's formula, after arXiv:2307.05244.")

    assert _check(project, capsys) == (
        0,
        [
            "warning: library atlas: module Lib.Convex's docstring cites arXiv 2307.05244, which 1 unproved article "
            "reaches, including step-0; no implementation note, source page or project Lean file names the module "
            "or any of its 4 declarations, such as Lib.Convex.helperA, Lib.Convex.helperB and Lib.Convex.helperC, "
            "so reuse them or record why they do not apply"
        ],
    )

    (project / "Project.lean").write_text("import Lib.Convex\n", encoding="utf-8")
    assert _check(project, capsys) == (0, [])


def test_a_declaration_whose_docstring_and_module_docstring_both_cite_warns_once(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _check(_consumer(tmp_path, module_doc="After arXiv:2307.05244."), capsys) == (0, [_warning()])


def test_the_warning_counts_every_article_reaching_the_source(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project = _consumer(tmp_path, sources="- [Gauss](https://arxiv.org/pdf/2307.05244)", articles=3)

    assert _check(project, capsys) == (0, [_warning(reach="3 unproved articles reach")])


@pytest.mark.parametrize(
    "changes",
    [{"status": "wanted"}, {"declarations": (declaration(_THEOREM, docstring="arXiv:2307.05244", auto_named=True),)}],
)
def test_a_wanted_or_automatically_named_declaration_is_not_reported(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], changes: dict
) -> None:
    assert _check(_consumer(tmp_path, **changes), capsys) == (0, [])


def test_a_proved_article_no_longer_asks_for_a_search(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _check(_consumer(tmp_path, proved=True), capsys) == (0, [])


def test_an_article_stated_in_lean_but_unproved_still_asks_for_a_search(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _check(_consumer(tmp_path, stated=True), capsys) == (0, [_warning()])


def _cited(*names: str) -> tuple:
    return tuple(declaration(name, docstring="arXiv:2307.05244") for name in names)


def test_declarations_named_in_different_notes_are_both_named(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project = _consumer(tmp_path, articles=2, declarations=_cited("A.foo", "B.bar"))
    _note(project, "Reuse `A.foo`.\n", 0)
    _note(project, "Reuse `B.bar`.\n", 1)

    assert _check(project, capsys) == (0, [])


def test_declarations_sharing_a_last_component_are_each_reported(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project = _consumer(tmp_path, declarations=_cited("A.foo", "B.foo"))

    assert _check(project, capsys) == (0, [_warning("A.foo"), _warning("B.foo")])


def test_a_hidden_file_among_the_notes_names_nothing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    project = _consumer(tmp_path)
    notes = project / "blueprint/.implementation-notes"
    notes.mkdir()
    (notes / f".af_{0:024x}.md.swp").write_text(f"{_THEOREM}\n", encoding="utf-8")

    assert _check(project, capsys) == (0, [_warning()])


def test_a_library_citing_another_paper_or_an_uncited_blueprint_gives_no_warning(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _check(_consumer(tmp_path, docstring="Source: arXiv:1702.01627v2."), capsys) == (0, [])
    assert _check(_consumer(tmp_path / "other", sources="- [A talk](https://example.org/talk)"), capsys) == (0, [])


def _stale(project: Path) -> None:
    # An edit after indexing makes the index stale, so search would refuse it too.
    source = project / ".lake/packages/atlas/Lib/Classic.lean"
    source.write_text(source.read_text(encoding="utf-8") + "-- edited\n", encoding="utf-8")


def test_an_index_that_cannot_be_used_is_named_and_never_fails_the_check(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project = _consumer(tmp_path)
    _stale(project)

    status, warnings = _check(project, capsys)

    assert status == 0
    assert warnings == [
        "warning: library atlas: its index cannot be used, so its declarations were not compared with the "
        "blueprint's sources: 1 source file differs from its index: Lib/Classic.lean"
    ]


@pytest.mark.parametrize("sources", ["- [A talk](https://example.org/talk)", _GAUSS])
def test_a_stale_index_is_not_verified_when_it_cites_nothing_the_blueprint_does(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], sources: str
) -> None:
    project = _consumer(tmp_path, sources=sources, docstring="Source: arXiv:1702.01627.")
    _stale(project)

    assert _check(project, capsys) == (0, [])


def test_a_lean_root_without_a_lake_manifest_compares_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project = _consumer(tmp_path)
    (project / "lake-manifest.json").unlink()

    assert _check(project, capsys) == (0, [])


def test_a_lake_manifest_that_cannot_be_read_is_named(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    project = _consumer(tmp_path)
    manifest = project / "lake-manifest.json"
    manifest.write_text(json.dumps({**json.loads(manifest.read_text(encoding="utf-8")), "lakeDir": "_lake"}))

    assert _check(project, capsys) == (
        0,
        [
            "warning: the Lake manifest cannot be read, so no shared library was compared with the blueprint's "
            "sources: lake-manifest.json sets lakeDir to '_lake'; only .lake is supported"
        ],
    )


@pytest.mark.parametrize("root", ["~autoform-no-such-user/project", "{project}\x00"])
def test_a_lean_root_that_cannot_be_resolved_keeps_its_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], root: str
) -> None:
    project = _consumer(tmp_path)

    assert main(["check", str(project / "blueprint"), "--lean-root", root.format(project=project)]) == 1
    assert capsys.readouterr().out.splitlines()[-1].startswith("error: Lean sources could not be indexed")


def test_a_failing_lean_name_keeps_the_check_failing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    project = _consumer(tmp_path)
    _article(project, "bad.md", title="Bad", metadata=("declaration: theorem", "lean: Project.missing"))

    assert main(["check", str(project / "blueprint"), "--lean-root", str(project)]) == 1
    assert "error: bad: declaration not found in" in capsys.readouterr().out


_UNREADABLE = pytest.mark.skipif(
    sys.platform == "win32" or (hasattr(os, "geteuid") and os.geteuid() == 0), reason="mode 0 still reads"
)


@_UNREADABLE
def test_lean_files_that_cannot_be_read_leave_the_index_build_to_report_them(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project = _consumer(tmp_path)
    lean = project / "Project.lean"
    lean.write_text("theorem Project.other : True := trivial\n", encoding="utf-8")
    lean.chmod(0)
    try:
        status = main(["check", str(project / "blueprint"), "--lean-root", str(project)])
    finally:
        lean.chmod(0o644)

    assert status == 1
    assert "error: Lean sources could not be indexed" in capsys.readouterr().out


@_UNREADABLE
def test_a_source_page_that_cannot_be_read_cites_nothing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    project = _consumer(tmp_path, sources="- [Gauss](../sources/gauss.md)")
    page = project / "blueprint/sources/gauss.md"
    page.parent.mkdir(parents=True)
    page.write_text("arXiv:2307.05244\n", encoding="utf-8")
    page.chmod(0)
    try:
        assert _check(project, capsys) == (0, [])
    finally:
        page.chmod(0o644)


def test_a_declaration_name_cannot_forge_output(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    project = _consumer(tmp_path, declarations=_cited("Nat.foo\x1b[2K\rerror: forged"))

    assert main(["check", str(project / "blueprint"), "--lean-root", str(project)]) == 0
    out = capsys.readouterr().out
    assert "\x1b" not in out and "\r" not in out
    assert "Nat.foo\\x1b[2K\\rerror: forged's docstring cites" in out


def test_a_symlinked_lean_root_is_compared_like_its_target(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project = _consumer(tmp_path)
    link = tmp_path / "link"
    try:
        link.symlink_to(project, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks are unavailable")

    assert main(["check", str(project / "blueprint"), "--lean-root", str(link)]) == 0
    assert [line for line in capsys.readouterr().out.splitlines() if line.startswith("warning:")] == [_warning()]
