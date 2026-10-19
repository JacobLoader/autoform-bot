"""Warn about shared-library declarations that cite the blueprint's own sources but that nothing in the project names.

A declaration whose docstring cites the paper a project formalizes almost always
proves part of it. ``autoform check --lean-root`` names each one that neither an
implementation note nor a project Lean file names, so a skipped library search
shows up. It only warns: tools inform and never break a codebase.
"""

from __future__ import annotations

import os
import re
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .. import status
from ..graph import IMPLEMENTATION_NOTES_DIR, Graph
from ..lean import index_failure_message, resolve_lean_root, snapshot_project_sources
from ..markdown import resolved_path
from .listing import indexed_packages
from .locate import LibraryError, read_workspace
from .verify import load_library

# A new-style identifier (2307.05244) or an old-style one (math/0210149, math.AG/0210149)
# after an arxiv.org URL or an "arXiv" label. A version suffix stays outside the match.
_ARXIV = re.compile(
    r"(?:arxiv\.org/(?:abs|pdf|html|e-print|src)/|\barxiv:?\s*`?)"
    r"(?:(?P<new>\d{4}\.\d{4,5})|(?P<archive>[a-z][a-z-]{0,15})(?:\.[a-z]{2})?/(?P<number>\d{7}))(?![\d/])",
    re.IGNORECASE,
)
# A DOI URL may percent-encode the slash after the registrant; a DOI written as link text ends at its `]`.
_DOI = re.compile(r"(?:doi\.org/|\bdoi:?\s*)(?P<doi>10\.\d{4,9}(?:/|%2F)[^\s\"'<>`\]]+)", re.IGNORECASE)
_ARXIV_DOI = "10.48550/arxiv."
#: A source page is notes about a source, so a larger file is not one.
_PAGE_LIMIT = 4 * 1024 * 1024


def cited_sources(text: str | None) -> frozenset[str]:
    """The arXiv papers and DOIs ``text`` cites, each spelled one way: ``arXiv 2307.05244`` or ``DOI 10.1000/x``."""

    if not text:
        return frozenset()
    found = set()
    for match in _ARXIV.finditer(text):
        found.add(f"arXiv {_paper(match)}")
    for match in _DOI.finditer(text):
        doi = unquote(match["doi"])
        # A DOI may hold parentheses, so only an unmatched closing one is the sentence's.
        end, unmatched = len(doi), doi.count(")") - doi.count("(")
        while doi[end - 1] in ".,;:}" or (doi[end - 1] == ")" and unmatched > 0):
            unmatched -= doi[end - 1] == ")"
            end -= 1
        doi = doi[:end]
        # arXiv's own DOIs name the paper its identifier does.
        paper = _ARXIV.fullmatch("arXiv:" + doi[len(_ARXIV_DOI) :]) if doi.lower().startswith(_ARXIV_DOI) else None
        found.add(f"arXiv {_paper(paper)}" if paper else f"DOI {doi.lower()}")
    return frozenset(found)


def _paper(match: re.Match[str]) -> str:
    return match["new"] or f"{match['archive'].lower()}/{match['number']}"


def library_citation_warnings(graph: Graph, lean_root: str | Path) -> list[str]:
    """Name each usable library's complete declarations that cite a source the blueprint cites and nothing names."""

    citing = _blueprint_sources(graph)
    if not citing:
        return []
    try:
        workspace = read_workspace(lean_root)
        packages = indexed_packages(lean_root)
    except (OSError, RuntimeError, ValueError):
        return []  # no Lake workspace to compare, or a Lean root check reports itself

    warnings = []
    candidates: list[tuple[str, str, str, list[str]]] = []
    for package in packages:
        try:
            library = load_library(workspace, package)
        except LibraryError as error:
            warnings.append(
                f"library {package}: its index cannot be used, so its declarations were not compared "
                f"with the blueprint's sources: {error.reason}"
            )
            continue
        module_sources = {module.name: cited_sources(module.module_doc) for module in library.index.modules}
        for declaration in library.index.declarations:
            if declaration.status != "complete":
                continue  # a wanted result is a placeholder, not a proof to reuse
            fields = (
                ("docstring", cited_sources(declaration.docstring)),
                ("module docstring", module_sources[declaration.module]),
            )
            for field, sources in fields:
                cited = sorted(sources & citing.keys(), key=lambda source: (-len(citing[source]), source))
                if cited:
                    candidates.append((library.name, declaration.name, field, cited))
                    break
    if not candidates:
        return warnings

    # Notes first: they are small, and a named declaration needs no Lean source read.
    unnamed = _unnamed([name for _, name, _, _ in candidates], _note_texts(graph.blueprint_dir))
    if unnamed:
        try:
            snapshot = snapshot_project_sources(resolve_lean_root(lean_root))
        except OSError as error:
            warnings.append(
                f"{len(unnamed)} library declaration(s) cite the blueprint's sources, but whether the project's "
                f"Lean files name them is unknown: {index_failure_message(error)}"
            )
            return warnings
        unnamed = _unnamed(sorted(unnamed), (data.decode("utf-8", "replace") for _, data in snapshot.source_files))

    for library, name, field, cited in sorted(candidates):
        if name not in unnamed:
            continue
        sources = ", and ".join(_cited_by(source, len(citing[source])) for source in cited)
        warnings.append(
            f"library {library} declares {name}, whose {field} cites {sources}; "
            "no implementation note or project Lean file names it"
        )
    return warnings


def _cited_by(source: str, articles: int) -> str:
    if articles == 1:
        return f"{source}, which 1 unproved article cites"
    return f"{source}, which {articles} unproved articles cite"


def _blueprint_sources(graph: Graph) -> dict[str, set[str]]:
    """Map each paper or DOI the unproved articles' ``## Sources`` links cite to the articles citing it.

    A link to a page under the blueprint counts with what the page cites, since
    Roadmap records source locations in ``blueprint/sources/``. A proved article
    no longer counts: it needs no search, and audit asks for its implementation
    note, which may have recorded a library declaration, to be deleted. Nor
    does a module catalog: it inventories existing Lean, so it has no proof to
    search a library for.
    """

    citing: dict[str, set[str]] = defaultdict(set)
    pages: dict[Path, frozenset[str]] = {}  # many articles link one source page
    blueprint = graph.blueprint_dir.resolve()
    derived = status.derive(graph)
    for node in graph.nodes.values():
        if node.catalog is not None or derived[node.id].proved:
            continue
        for target in node.sources:
            page = _linked_page(node.path, target, blueprint)
            if page is not None and page not in pages:
                pages[page] = cited_sources(_page_text(page))
            for source in cited_sources(target) | pages.get(page, frozenset()):
                citing[source].add(node.id)
    return citing


def _linked_page(article: Path, target: str, blueprint: Path) -> Path | None:
    """The blueprint file a local link in ``article`` names, or ``None`` for any other link."""

    try:
        split = urlsplit(target)
    except ValueError:
        return None
    if split.scheme or split.netloc or not split.path:
        return None
    page = resolved_path(article.parent / unquote(split.path))
    return page if page is not None and page.is_relative_to(blueprint) and os.path.isfile(page) else None


def _page_text(path: Path) -> str | None:
    try:
        if path.stat().st_size > _PAGE_LIMIT:
            return None
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _note_texts(blueprint: Path) -> list[str]:
    root = blueprint / IMPLEMENTATION_NOTES_DIR
    try:
        paths = sorted(root.iterdir())
    except OSError:
        return []
    texts = []
    for path in paths:
        # Hidden entries, such as an editor's lock symlink, are never notes.
        if path.name.startswith(".") or path.is_symlink() or not path.is_file():
            continue
        try:
            texts.append(path.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
    return texts


def _unnamed(names: list[str], texts: Iterable[str]) -> set[str]:
    """The ``names`` whose last component no text contains as a whole word.

    After ``open Nat``, a Lean file names ``Nat.foo`` as ``foo``, so the last
    component stands for the name. That can take another ``foo``, or ``foo'``,
    for it and stay silent, but it never claims that nothing names a declaration
    that is named.
    """

    # The same last component under two namespaces stands for both.
    by_last: dict[str, set[str]] = defaultdict(set)
    for name in names:
        by_last[name.rpartition(".")[2]].add(name)
    pattern = re.compile(
        r"(?<!\w)(" + "|".join(re.escape(last) for last in sorted(by_last, key=len, reverse=True)) + r")(?!\w)"
    )
    found: set[str] = set()
    for text in texts:
        found.update(pattern.findall(text))
        if len(found) == len(by_last):
            break
    return {name for last, group in by_last.items() if last not in found for name in group}


__all__ = ["cited_sources", "library_citation_warnings"]
