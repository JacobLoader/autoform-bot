from __future__ import annotations

from pathlib import Path

import pytest

from autoform_cli import site_check
from autoform_cli.__main__ import main
from autoform_cli.render import render_site
from autoform_cli.scaffold import scaffold_project
from autoform_cli.site_check import SiteCheckError, check_site


def _site(root: Path, pages: dict[str, str]) -> Path:
    for name, body in pages.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    return root


def test_check_reports_dead_links_missing_anchors_and_links_that_leave_the_site(tmp_path: Path) -> None:
    site = _site(
        tmp_path / "site",
        {
            "index.html": (
                '<a href="a.html">a</a> <a href="a.html#kept">kept</a> <a href="a.html#gone">gone</a>'
                '<a href="missing.html">missing</a> <a href="roadmap/ch/README.html#x">readme</a>'
                '<a href="../outside.html">outside</a> <img src="figure.svg"> <a href="#top">top</a>'
                '<a href="#nowhere">nowhere</a> <span id="top"></span>'
            ),
            "a.html": '<h2 id="kept">Kept</h2><a name="named"></a><a href="index.html#named">wrong page</a>',
            "roadmap/ch/index.html": '<div id="x"></div>',
        },
    )

    report = check_site(site)

    assert report.pages == 3
    assert report.issues == (
        "a.html: index.html#named names no anchor #named on index.html",
        "index.html: a.html#gone names no anchor #gone on a.html",
        "index.html: missing.html names missing.html, which the site does not contain",
        "index.html: roadmap/ch/README.html#x names roadmap/ch/README.html, which the site does not contain",
        "index.html: ../outside.html leaves the site",
        "index.html: figure.svg names figure.svg, which the site does not contain",
        "index.html: #nowhere names no anchor #nowhere on index.html",
    )


def test_check_skips_links_that_depend_on_where_the_site_is_served(tmp_path: Path) -> None:
    site = _site(
        tmp_path / "site",
        {
            "index.html": (
                '<a href="https://example.org/x.html#y">web</a> <a href="mailto:a@b.c">mail</a>'
                '<a href="//cdn.example.org/a.js">cdn</a> <a href="/root.html">root</a>'
                '<script src="javascript:void(0)"></script> <a href="">self</a> <a href="#">top</a>'
                '<a href="sub/">sub</a> <a href="sub/#in">in</a> <a href=".">here</a>'
                '<a href="a%20b.html#c%20d">spaced</a> <link rel="stylesheet" href="assets/site.css?v=1">'
            ),
            "sub/index.html": '<p id="in"></p>',
            "a b.html": '<p id="c d"></p>',
            "assets/site.css": "",
        },
    )

    assert check_site(site).issues == ()


def test_check_compares_each_page_with_the_cards_render_wrote(tmp_path: Path) -> None:
    card = '<div class="bp-thmwrapper theorem-style-plain bp-stated" id="{0}" data-autoform-node-id="ch/{0}" markdown="1">'
    source = _site(
        tmp_path / "site-src",
        {
            "roadmap/ch/README.md": "# Chapter\n\n" + "\n".join(card.format(name) for name in ("a", "b", "c")) + "\n",
            "roadmap/other.md": "# Other\n\n" + card.format("d") + "\n",
            "roadmap/gone.md": "# Gone\n\n" + card.format("e") + "\n",
            "notes.md": "# Notes\n\nNo cards.\n",
        },
    )
    built = '<div class="bp-thmwrapper theorem-style-plain bp-stated" id="{0}" data-autoform-node-id="ch/{0}"></div>'
    site = _site(
        tmp_path / "site",
        {
            "roadmap/ch/index.html": built.format("a"),
            "roadmap/other/index.html": built.format("d"),
            "notes.html": "<p>No cards.</p>",
        },
    )

    report = check_site(site, source)

    assert report.issues == (
        "roadmap/ch/index.html: 2 of the 3 statement card(s) in roadmap/ch/README.md did not survive the build: "
        "ch/b, ch/c",
        "roadmap/gone.md: no built page holds its 1 statement card(s)",
    )


def test_check_reads_each_page_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    count = 1_200
    pages = {
        f"page{index:04d}.html": f'<h1 id="p{index}">Page</h1><a href="page{(index + 1) % count:04d}.html#p{(index + 1) % count}">next</a>'
        for index in range(count)
    }
    site = _site(tmp_path / "site", pages)
    fed: list[int] = []
    feed = site_check._PageParser.feed

    def counting_feed(self, data: str) -> None:
        fed.append(len(data))
        feed(self, data)

    monkeypatch.setattr(site_check._PageParser, "feed", counting_feed)

    report = check_site(site)

    assert report.pages == count
    assert report.issues == ()
    assert len(fed) == count


def test_cli_prints_problems_as_warnings_and_never_fails_on_them(tmp_path: Path, capsys) -> None:
    site = _site(tmp_path / "site", {"index.html": '<a href="missing.html">missing</a>'})

    assert main(["site", "check", str(site)]) == 0
    assert capsys.readouterr().out == (
        f"{site}: 1 pages, 1 problem(s)\n"
        "warning: index.html: missing.html names missing.html, which the site does not contain\n"
    )
    assert main(["site", "check", str(tmp_path / "absent")]) == 1
    assert capsys.readouterr().out == f"error: {tmp_path / 'absent'} is not a directory\n"
    with pytest.raises(SiteCheckError, match="is not a directory"):
        check_site(site, tmp_path / "no-source")


def test_check_passes_a_rendered_project_that_mkdocs_built_with_the_template(tmp_path: Path) -> None:
    mkdocs_build = pytest.importorskip("mkdocs.commands.build")
    from mkdocs.config import load_config

    project = tmp_path / "project"
    scaffold_project(project, title="Site Check", repository_url="https://github.com/owner/repo")
    roadmap = project / "blueprint" / "roadmap"
    (roadmap / "README.md").write_text(
        "---\n---\n\n# Roadmap\n\nThe one result.\n\n## Results\n\n- [Top](top.md)\n", encoding="utf-8"
    )
    (roadmap / "top.md").write_text(
        "---\ndeclaration: theorem\nstatement: formalized\nproof: formalized\nlean: Project.top\n---\n\n"
        "# Top\n\nFor $a < b$ and every n, the main result holds.\n\n## Depends on\n\nThis node has no prerequisites.\n",
        encoding="utf-8",
    )
    render_site(project / "blueprint", project / "site-src")
    mkdocs_build.build(load_config(config_file=str(project / "mkdocs.yml")))

    report = check_site(project / "site", project / "site-src")

    # The card the check compares, written with a `<` the site's conversion once mistook for a tag.
    assert 'data-autoform-node-id="top"' in (project / "site-src/roadmap/README.md").read_text(encoding="utf-8")
    assert report.pages > 0
    assert report.issues == ()
