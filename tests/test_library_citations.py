from __future__ import annotations

from pathlib import Path

import pytest

from autoform_cli.__main__ import main
from autoform_cli.library.citations import cited_sources
from tests.library_fixture import declaration, make_library
from tests.test_search import _article

_THEOREM = "Nat.threeSquareRepresentationCount_eq_threeSquareRepresentationCount_div_four"


@pytest.mark.parametrize(
    ("text", "source"),
    [
        ("Source: arXiv:2307.05244 `main.tex` lines 191-199", "arXiv 2307.05244"),
        ("arXiv 2307.05244v3", "arXiv 2307.05244"),
        ("https://arxiv.org/abs/2307.05244v2", "arXiv 2307.05244"),
        ("http://arxiv.org/pdf/2307.05244v1.pdf", "arXiv 2307.05244"),
        ("https://doi.org/10.48550/arXiv.2307.05244", "arXiv 2307.05244"),
        ("arXiv:math.AG/0210149v2", "arXiv math/0210149"),
        ("https://arxiv.org/abs/math/0210149", "arXiv math/0210149"),
        ("doi:10.1007/S00222-012-0383-5.", "DOI 10.1007/s00222-012-0383-5"),
        ("DOI: 10.1007/s00222-012-0383-5", "DOI 10.1007/s00222-012-0383-5"),
        ("(see https://dx.doi.org/10.1007%2Fs00222-012-0383-5)", "DOI 10.1007/s00222-012-0383-5"),
        ("[paper](https://doi.org/10.1016/0001-8708(77)90004-3)", "DOI 10.1016/0001-8708(77)90004-3"),
    ],
)
def test_a_paper_is_one_source_in_each_of_its_usual_spellings(text: str, source: str) -> None:
    assert cited_sources(text) == {source}


@pytest.mark.parametrize("text", ["2307.05244", "an arXiv preprint", "arXiv:2307.052449", "10.1007/s00222-012-0383-5"])
def test_a_number_without_its_arxiv_or_doi_label_cites_nothing(text: str) -> None:
    assert cited_sources(text) == frozenset()


def _consumer(
    tmp_path: Path,
    *,
    sources: str = "- [Gauss](https://arxiv.org/abs/2307.05244v2)",
    docstring: str | None = "Source: arXiv:2307.05244 `main.tex` lines 191-199.",
    module_doc: str | None = None,
    articles: int = 1,
) -> Path:
    # The blueprint and the Lake project share one root, as in a real consumer.
    library = make_library(
        tmp_path,
        declarations=(declaration(_THEOREM, docstring=docstring),),
        module_docs={"Lib.Convex": module_doc} if module_doc else None,
    )
    _article(library.project, "README.md", title="Three squares")
    for number in range(articles):
        _article(
            library.project,
            f"step-{number}.md",
            title=f"Step {number}",
            body=f"A step of the proof.\n\n## Sources\n\n{sources}",
            metadata=(f"article_id: af_{number:024x}",),
        )
    return library.project


def _check(project: Path, capsys: pytest.CaptureFixture[str]) -> tuple[int, list[str]]:
    status = main(["check", str(project / "blueprint"), "--lean-root", str(project)])
    return status, [line for line in capsys.readouterr().out.splitlines() if line.startswith("warning:")]


def test_check_warns_about_a_library_result_citing_the_paper_until_a_note_or_lean_file_names_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project = _consumer(tmp_path)

    assert _check(project, capsys) == (
        0,
        [
            f"warning: library atlas declares {_THEOREM}, whose docstring cites arXiv 2307.05244, "
            "which 1 article cites; no implementation note or project Lean file names it"
        ],
    )

    note = project / f"blueprint/.implementation-notes/af_{0:024x}.md"
    note.parent.mkdir()
    note.write_text(f"Reuse `{_THEOREM}` from ATLAS.\n", encoding="utf-8")
    assert _check(project, capsys) == (0, [])

    note.unlink()
    # After `open Nat` the project names it by its last component alone.
    (project / "Project.lean").write_text(
        "open Nat\n\nexample := threeSquareRepresentationCount_eq_threeSquareRepresentationCount_div_four\n",
        encoding="utf-8",
    )
    assert _check(project, capsys) == (0, [])


def test_a_source_page_an_article_links_counts_with_what_it_cites(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project = _consumer(
        tmp_path,
        sources="- [Mortenson, Theorem 2](../sources/mortenson.md#theorem-2)",
        docstring=None,
        module_doc="Gauss's three-square formula, after doi:10.1007/S00222-012-0383-5.",
    )
    page = project / "blueprint/sources/mortenson.md"
    page.parent.mkdir(parents=True)
    page.write_text(
        "# Mortenson\n\nPublished as https://doi.org/10.1007/s00222-012-0383-5.\n\n## Theorem 2\n\nLines 127-131.\n",
        encoding="utf-8",
    )

    assert _check(project, capsys) == (
        0,
        [
            f"warning: library atlas declares {_THEOREM}, whose module docstring cites "
            "DOI 10.1007/s00222-012-0383-5, which 1 article cites; no implementation note or project Lean file names it"
        ],
    )


def test_the_warning_counts_every_article_citing_the_source(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    project = _consumer(tmp_path, sources="- [Gauss](https://arxiv.org/pdf/2307.05244)", articles=3)

    status, warnings = _check(project, capsys)

    assert status == 0
    assert [warning.split(", which ")[1].split(";")[0] for warning in warnings] == ["3 articles cite"]


def test_a_wanted_result_citing_the_paper_is_no_proof_to_reuse(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    wanted = declaration(_THEOREM, status="wanted", docstring="Source: arXiv:2307.05244.")
    library = make_library(tmp_path, declarations=(wanted,))
    _article(library.project, "README.md", title="Three squares")
    _article(
        library.project,
        "step.md",
        title="Step",
        body="A step.\n\n## Sources\n\n- [Gauss](https://arxiv.org/abs/2307.05244)",
    )

    assert _check(library.project, capsys) == (0, [])


def test_a_library_citing_another_paper_or_an_uncited_blueprint_gives_no_warning(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project = _consumer(tmp_path, docstring="Source: arXiv:1702.01627v2.")
    assert _check(project, capsys) == (0, [])

    other = _consumer(tmp_path / "other", sources="- [A talk](https://example.org/talk)")
    assert _check(other, capsys) == (0, [])


def test_an_index_that_cannot_be_used_is_named_and_never_fails_the_check(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project = _consumer(tmp_path)
    # An edit after indexing makes the index stale, so search would refuse it too.
    source = project / ".lake/packages/atlas/Lib/Classic.lean"
    source.write_text(source.read_text(encoding="utf-8") + "-- edited\n", encoding="utf-8")

    status, warnings = _check(project, capsys)

    assert status == 0
    assert len(warnings) == 1
    assert warnings[0].startswith(
        "warning: library atlas: its index cannot be used, so its declarations were not compared with the "
        "blueprint's sources: "
    )
