"""Warn about library declarations whose docstrings cite the blueprint's sources and that nothing names.

A declaration whose docstring cites the paper a project formalizes almost always
proves part of it. ``autoform check --lean-root`` names each one that no
implementation note, source page or project Lean file names, so a skipped
library search shows up. The warnings never change the exit status.
"""

from __future__ import annotations

import os
import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .. import status
from ..graph import IMPLEMENTATION_NOTES_DIR, Graph
from ..lean import _CONTINUATION_IDENTIFIER, index_failure_message, resolve_lean_root, snapshot_project_sources
from ..markdown import resolved_path
from .index import INDEX_FILE, LibraryIndex, LibraryIndexError, parse_index
from .listing import indexed_packages
from .locate import LibraryError, WorkspaceError, checkout_paths, find_package, read_workspace
from .verify import _index_bytes, load_library

#: A new-style identifier (2307.05244) or an old-style one (math/0210149, math.AG/0210149) after an
#: arxiv.org URL or an "arXiv" label, which Markdown emphasis or a table cell may separate from it.
#: A version suffix stays outside the match.
_ARXIV = re.compile(
    r"(?:arxiv\.org/(?:abs|pdf|html|e-print|src)/|(?<![a-z0-9])arxiv[\s:*_|`]*)"
    r"(?:(?P<new>\d{4}\.\d{4,5})|(?P<archive>[a-z][a-z-]{0,15})(?:\.[a-z]{2})?/(?P<number>\d{7}))(?!\d)",
    re.IGNORECASE,
)
#: A DOI after a doi.org URL or a "DOI" label. A URL may percent-encode the slash after the
#: registrant, and a DOI ends at a URL's query or fragment and at the `]` of link text.
_DOI = re.compile(
    r"(?:doi\.org/|(?<![a-z0-9])doi[\s:*_|]*)(?P<doi>10\.\d{4,9}(?:/|%2F)[^\s\"'<>`\]?#]+)", re.IGNORECASE
)
_ARXIV_DOI = "10.48550/arxiv."
#: Larger linked files are not pages Roadmap writes about a source.
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
        while doi[end - 1] in ".,;:}*" or (doi[end - 1] == ")" and unmatched > 0):
            unmatched -= doi[end - 1] == ")"
            end -= 1
        doi = doi[:end]
        # arXiv's own DOIs name the paper its identifier does, with or without a version.
        rest = re.sub(r"v\d+$", "", doi[len(_ARXIV_DOI) :])
        paper = _ARXIV.fullmatch("arXiv:" + rest) if doi.lower().startswith(_ARXIV_DOI) else None
        found.add(f"arXiv {_paper(paper)}" if paper else f"DOI {doi.lower()}")
    return frozenset(found)


def _paper(match: re.Match[str]) -> str:
    return match["new"] or f"{match['archive'].lower()}/{match['number']}"


@dataclass(frozen=True, slots=True)
class _Hit:
    library: str
    module: str
    name: str
    #: The sources it cites that unproved articles reach, the most reached first.
    sources: tuple[str, ...]
    #: Whether its own docstring cites them, rather than only its module's.
    own: bool


def library_citation_warnings(graph: Graph, lean_root: str | Path) -> list[str]:
    """Warn about usable libraries' complete declarations whose docstrings cite a source the blueprint cites.

    A declaration counts as named when an implementation note or a page the articles' ``## Sources``
    link names it in full, or a project Lean file names its last component. A hit only in a module's
    docstring is reported once for the module, which naming the module or any of its hits silences.
    """

    citing, pages = _blueprint_sources(graph)
    if not citing:
        return []
    try:
        workspace = read_workspace(lean_root)
        packages = indexed_packages(lean_root)
    except WorkspaceError as error:
        if not os.path.isfile(os.path.join(os.path.expanduser(os.fspath(lean_root)), "lake-manifest.json")):
            return []  # a Lean root without a Lake manifest locks no shared library
        return [
            f"the Lake manifest cannot be read, so no shared library was compared with the blueprint's sources: {error}"
        ]
    except (OSError, RuntimeError, ValueError):
        return []  # build_linker reports a Lean root it cannot use

    warnings, hits = [], []
    for package in packages:
        try:
            # Matching is cheap and hashing a library's sources is not, so only a library with a hit is verified.
            if not _hits(_unverified_index(workspace, package), citing, package):
                continue
            library = load_library(workspace, package)
        except LibraryError as error:
            warnings.append(
                f"library {package}: its index cannot be used, so its declarations were not compared "
                f"with the blueprint's sources: {error.reason}"
            )
            continue
        hits.extend(_hits(library.index, citing, library.name))
    if not hits:
        return warnings

    prose = _prose_names([*_note_texts(graph.blueprint_dir), *pages])
    lean_names: set[str] = set()
    lean_components: set[str] = set()
    if any(hit.name not in prose for hit in hits):
        try:
            snapshot = snapshot_project_sources(resolve_lean_root(lean_root))
        except OSError as error:
            unknown = sum(hit.name not in prose for hit in hits)
            warnings.append(
                f"{unknown} library declaration(s) cite the blueprint's sources, but whether the project's "
                f"Lean files name them is unknown: {index_failure_message(error)}"
            )
            return warnings
        lean_names, lean_components = _lean_names(data.decode("utf-8", "replace") for _, data in snapshot.source_files)

    def named(name: str) -> bool:
        return name in prose or name.rpartition(".")[2] in lean_components

    modules: dict[tuple[str, str], list[_Hit]] = defaultdict(list)
    for hit in sorted(hits, key=lambda hit: (hit.library, hit.name)):
        if not hit.own:
            modules[hit.library, hit.module].append(hit)
        elif not named(hit.name):
            warnings.append(
                f"library {hit.library}: {hit.name}'s docstring cites {_reach(hit.sources, citing)}; no implementation "
                "note, source page or project Lean file names it, so reuse it or record why it does not apply"
            )
    for (library, module), group in sorted(modules.items()):
        if module in prose or module in lean_names or any(named(hit.name) for hit in group):
            continue
        one = len(group) == 1
        members = f"its declaration {group[0].name}" if one else (
            f"any of its {len(group)} declarations, such as {_some(hit.name for hit in group)}"
        )
        warnings.append(
            f"library {library}: module {module}'s docstring cites {_reach(group[0].sources, citing)}; no "
            f"implementation note, source page or project Lean file names the module or {members}, so reuse "
            f"{'it' if one else 'them'} or record why {'it does' if one else 'they do'} not apply"
        )
    return warnings


def _unverified_index(workspace, package: str) -> LibraryIndex:
    """``package``'s index as its checkout holds it, before ``load_library`` checks it against the sources."""

    try:
        _checkout, root = checkout_paths(workspace, find_package(workspace, package))
        return parse_index(_index_bytes(root / INDEX_FILE))
    except (OSError, LibraryIndexError):
        return load_library(workspace, package).index  # raises the reason `library list` gives


def _hits(index: LibraryIndex, citing: dict[str, set[str]], library: str) -> list[_Hit]:
    def ordered(sources: frozenset[str]) -> tuple[str, ...]:
        return tuple(sorted(sources, key=lambda source: (-len(citing[source]), source)))

    module_sources = {module.name: cited_sources(module.module_doc) & citing.keys() for module in index.modules}
    hits = []
    for declaration in index.declarations:
        # A wanted result is no proof to reuse, and nobody writes an automatic name.
        if declaration.status != "complete" or declaration.auto_named:
            continue
        own = cited_sources(declaration.docstring) & citing.keys()
        if cited := own or module_sources[declaration.module]:
            hits.append(_Hit(library, declaration.module, declaration.name, ordered(cited), bool(own)))
    return hits


def _reach(sources: tuple[str, ...], citing: dict[str, set[str]]) -> str:
    articles = set().union(*(citing[source] for source in sources))
    more = len(sources) - 1
    cited = sources[0] + (f" and {more} more source{'s' if more > 1 else ''} the blueprint cites" if more else "")
    reach = "1 unproved article reaches" if len(articles) == 1 else f"{len(articles)} unproved articles reach"
    return f"{cited}, which {reach}, including {min(articles)}"


def _some(names: Iterable[str]) -> str:
    first = list(names)[:3]
    return first[0] if len(first) == 1 else f"{', '.join(first[:-1])} and {first[-1]}"


def _blueprint_sources(graph: Graph) -> tuple[dict[str, set[str]], list[str]]:
    """The sources unproved articles reach, each with those articles, and the text of every linked page.

    An article reaches what its ``## Sources`` links cite, and what a Markdown page under the blueprint
    that a link names cites, since Roadmap records source locations in ``blueprint/sources/``. A proved
    article reaches nothing: it needs no search. Every linked page is also a place that can name a
    declaration, where a record that it does not apply outlives the implementation notes audit deletes.
    """

    citing: dict[str, set[str]] = defaultdict(set)
    pages: dict[Path, tuple[str, frozenset[str]]] = {}  # many articles link one source page
    blueprint = graph.blueprint_dir.resolve()
    derived = status.derive(graph)
    for node in graph.nodes.values():
        for target in node.sources:
            page = _linked_page(node.path, target, blueprint)
            if page is not None and page not in pages:
                text = _page_text(page)
                pages[page] = (text, cited_sources(text))
            if derived[node.id].proved:
                continue
            for source in cited_sources(target) | (pages[page][1] if page is not None else frozenset()):
                citing[source].add(node.id)
    return citing, [text for text, _sources in pages.values()]


def _linked_page(article: Path, target: str, blueprint: Path) -> Path | None:
    """The Markdown file under the blueprint a local link in ``article`` names, or ``None`` for any other link."""

    try:
        split = urlsplit(target)
    except ValueError:
        return None
    if split.scheme or split.netloc or not split.path:
        return None
    page = resolved_path(article.parent / unquote(split.path))
    if page is None or not page.is_relative_to(blueprint) or page.suffix.lower() != ".md":
        return None
    return page if os.path.isfile(page) else None


def _page_text(path: Path) -> str:
    try:
        if path.stat().st_size > _PAGE_LIMIT:
            return ""
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


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


def _prose_names(texts: Iterable[str]) -> set[str]:
    """The full Lean names ``texts`` write, which prose may follow with ``'s``, ``?`` or ``!``."""

    names = set()
    for text in texts:
        for token in _CONTINUATION_IDENTIFIER.findall(text):
            names.update((token, token.rstrip("!?"), token.removesuffix("'s")))
    return names


def _lean_names(texts: Iterable[str]) -> tuple[set[str], set[str]]:
    """The names Lean ``texts`` write, and their components: after ``open Nat`` a file names ``Nat.foo`` as ``foo``.

    Taking any ``foo`` for ``Nat.foo`` can leave a declaration unreported, but it never reports one
    that a Lean file names.
    """

    names: set[str] = set()
    components: set[str] = set()
    for text in texts:
        for token in _CONTINUATION_IDENTIFIER.findall(text):
            names.add(token)
            components.update(token.split("."))
    return names, components


__all__ = ["cited_sources", "library_citation_warnings"]
