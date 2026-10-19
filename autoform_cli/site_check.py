"""Find the links and statement cards a site's build broke.

``mkdocs build --strict`` never checks a link written as raw HTML, and it logs a
broken Markdown anchor only at info level. Render writes many links as raw HTML,
and a Markdown conversion has dropped statement cards with every check green.
This reads the built site itself, and reports what it finds as warnings.
"""

from __future__ import annotations

import html
import posixpath
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

#: The attribute through which each element links to, or loads, another file.
_LINK_ATTRIBUTES = {
    "a": "href",
    "area": "href",
    "link": "href",
    "audio": "src",
    "embed": "src",
    "iframe": "src",
    "img": "src",
    "script": "src",
    "source": "src",
    "track": "src",
    "video": "src",
}

#: The opening tag render writes for each statement card, on a line of its own.
_SOURCE_CARD = re.compile(r'^<div class="bp-thmwrapper\b[^"]*"[^>]*?\bdata-autoform-node-id="([^"]*)"', re.MULTILINE)


class SiteCheckError(ValueError):
    """The site or its source cannot be read as a directory."""


@dataclass(frozen=True, slots=True)
class SiteReport:
    pages: int
    issues: tuple[str, ...]


@dataclass(slots=True)
class _Page:
    ids: set[str] = field(default_factory=set)
    links: list[str] = field(default_factory=list)
    cards: list[str] = field(default_factory=list)


class _PageParser(HTMLParser):
    def __init__(self, page: _Page) -> None:
        super().__init__(convert_charrefs=True)
        self.page = page

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values: dict[str, str] = {}
        for name, value in attrs:
            # A browser keeps the first of two equal attribute names.
            values.setdefault(name, value or "")
        if "id" in values:
            self.page.ids.add(values["id"])
        if tag == "a" and "name" in values:
            self.page.ids.add(values["name"])
        attribute = _LINK_ATTRIBUTES.get(tag)
        if attribute is not None and attribute in values:
            self.page.links.append(values[attribute])
        if tag == "div" and "bp-thmwrapper" in values.get("class", "").split() and "data-autoform-node-id" in values:
            self.page.cards.append(values["data-autoform-node-id"])

    handle_startendtag = handle_starttag


def check_site(site_dir: str | Path, source_dir: str | Path | None = None) -> SiteReport:
    """Report the internal links, fragments and statement cards a built site lacks.

    Every HTML page under *site_dir* is read once. A link with a scheme or a
    network location, or a path from the site root, depends on where the site
    is served and is not checked. With *source_dir*, the rendered Markdown the
    site was built from, each source page's statement cards must all be on the
    page built from it.
    """

    site = Path(site_dir)
    if not site.is_dir():
        raise SiteCheckError(f"{site} is not a directory")
    pages: dict[str, _Page] = {}
    for path in sorted(site.rglob("*.html")):
        if path.is_file():
            page = _Page()
            parser = _PageParser(page)
            parser.feed(path.read_text(encoding="utf-8", errors="replace"))
            parser.close()
            pages[path.relative_to(site).as_posix()] = page
    issues: list[str] = []
    files: dict[str, str | None] = {}
    for name, page in pages.items():
        for link in page.links:
            problem = _link_problem(site, pages, files, name, link)
            if problem is not None:
                issues.append(f"{name}: {problem}")
    if source_dir is not None:
        source = Path(source_dir)
        if not source.is_dir():
            raise SiteCheckError(f"{source} is not a directory")
        issues.extend(_card_problems(source, pages))
    return SiteReport(len(pages), tuple(issues))


def _link_problem(
    site: Path, pages: dict[str, _Page], files: dict[str, str | None], page: str, link: str
) -> str | None:
    parts = urlsplit(link.strip())
    if parts.scheme or parts.netloc or parts.path.startswith("/"):
        return None
    target = page
    if parts.path:
        joined = posixpath.normpath(posixpath.join(posixpath.dirname(page), unquote(parts.path)))
        if joined == ".." or joined.startswith("../"):
            return f"{link} leaves the site"
        if joined not in files:
            files[joined] = _published_file(site, joined)
        found = files[joined]
        if found is None:
            return f"{link} names {joined}, which the site does not contain"
        target = found
    fragment = unquote(parts.fragment)
    if fragment and target in pages and fragment not in pages[target].ids:
        return f"{link} names no anchor #{fragment} on {target}"
    return None


def _published_file(site: Path, path: str) -> str | None:
    """The file a site path serves: the file itself, or a directory's ``index.html``."""

    if (site / path).is_dir():
        path = posixpath.normpath(posixpath.join(path, "index.html"))
    return path if (site / path).is_file() else None


def _card_problems(source: Path, pages: dict[str, _Page]) -> list[str]:
    issues: list[str] = []
    for path in sorted(source.rglob("*.md")):
        if not path.is_file():
            continue
        expected = [html.unescape(node) for node in _SOURCE_CARD.findall(path.read_text(encoding="utf-8", errors="replace"))]
        if not expected:
            continue
        relative = path.relative_to(source).as_posix()
        built = _built_page(relative, pages)
        if built is None:
            issues.append(f"{relative}: no built page holds its {len(expected)} statement card(s)")
            continue
        present = set(pages[built].cards)
        missing = [node for node in expected if node not in present]
        if missing:
            issues.append(
                f"{built}: {len(missing)} of the {len(expected)} statement card(s) in {relative} "
                f"did not survive the build: {', '.join(missing)}"
            )
    return issues


def _built_page(relative: str, pages: dict[str, _Page]) -> str | None:
    """The page MkDocs builds from a source page, with or without directory URLs."""

    stem = posixpath.splitext(relative)[0]
    directory, name = posixpath.split(stem)
    candidates = [stem + ".html", posixpath.join(stem, "index.html")]
    if name in {"README", "index"}:
        candidates.insert(0, posixpath.join(directory, "index.html"))
    return next((candidate for candidate in candidates if candidate in pages), None)


__all__ = ["SiteCheckError", "SiteReport", "check_site"]
