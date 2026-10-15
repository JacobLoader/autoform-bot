from __future__ import annotations

import functools
import os
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from autoform_cli import dag_viewer
from autoform_cli.graph_views import GraphView, ViewEdge, ViewNode
from autoform_cli.render import render_site
from autoform_cli.scaffold import scaffold_project

# CI sets this, so a missing browser fails the job instead of skipping every case.
_REQUIRED = os.environ.get("AUTOFORM_REQUIRE_BROWSER_TESTS") == "1"
if _REQUIRED:
    import playwright.sync_api as playwright
else:
    playwright = pytest.importorskip(
        "playwright.sync_api",
        reason="the optional browser extra is required for WebKit regression tests",
    )


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass


@contextmanager
def _served(directory: Path) -> Iterator[str]:
    handler = functools.partial(_QuietHandler, directory=str(directory))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


@pytest.fixture(scope="session")
def webkit_browser() -> Iterator[object]:
    with playwright.sync_playwright() as runtime:
        try:
            browser = runtime.webkit.launch()
        except playwright.Error as error:
            if _REQUIRED or "Executable doesn't exist" not in str(error):
                raise
            pytest.skip("WebKit is not installed; run `playwright install webkit`")
        yield browser
        browser.close()


@contextmanager
def _page(browser: object, **options: object) -> Iterator[object]:
    """Open a page in a context of its own, close it, and fail on any uncaught page error."""
    context = browser.new_context(**options)
    errors: list[str] = []
    page = context.new_page()
    page.on("pageerror", lambda error: errors.append(str(error)))
    try:
        yield page
    finally:
        context.close()
    assert errors == []


@pytest.fixture()
def desktop_page(webkit_browser: object) -> Iterator[object]:
    with _page(webkit_browser, viewport={"width": 1280, "height": 900}) as page:
        yield page


@pytest.fixture()
def mobile_page(webkit_browser: object) -> Iterator[object]:
    # Reduced motion keeps the sheet from sliding while a test measures it.
    with _page(
        webkit_browser,
        viewport={"width": 390, "height": 844},
        is_mobile=True,
        has_touch=True,
        reduced_motion="reduce",
    ) as page:
        yield page


@pytest.fixture(scope="module")
def explorer_url(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    tmp_path = tmp_path_factory.mktemp("explorer")
    core_nodes = (
        ViewNode(
            id="chapter/foundation",
            title="Foundation",
            kind="node",
            members=("chapter/foundation",),
            status_counts=(("fully_proved", 1),),
            declaration="def",
            status_key="fully_proved",
        ),
        ViewNode(
            id="chapter/middle",
            title="Middle lemma",
            kind="node",
            members=("chapter/middle",),
            status_counts=(("can_prove", 1),),
            declaration="lemma",
            status_key="can_prove",
        ),
        ViewNode(
            id="chapter/target",
            title="Target theorem",
            kind="node",
            members=("chapter/target",),
            status_counts=(("planned", 1),),
            declaration="theorem",
            status_key="planned",
        ),
    )
    nodes = core_nodes + tuple(
        ViewNode(
            id=f"inventory/auxiliary-{index}",
            title=f"Auxiliary inventory {index}",
            kind="node",
            members=(f"inventory/auxiliary-{index}",),
            status_counts=(("planned", 1),),
            declaration="lemma",
            status_key="planned",
        )
        for index in range(60)
    )
    view = GraphView(
        kind="full",
        title="Standalone dependency explorer",
        nodes=nodes,
        edges=(
            ViewEdge(nodes[0].id, nodes[1].id, statement_count=1),
            ViewEdge(nodes[1].id, nodes[2].id, statement_count=1),
        ),
    )
    links = {node.id: f"articles.html#{node.id}" for node in nodes}
    dag_viewer.write_payload(tmp_path / "graph.json", view, links=links)
    remote = ViewNode(
        id="remote/deep-theorem",
        title="Remote theorem",
        kind="node",
        members=("remote/deep-theorem",),
        status_counts=(("planned", 1),),
        declaration="theorem",
        status_key="planned",
    )
    dag_viewer.write_search_index(
        tmp_path / "search.json",
        GraphView(kind="full", title="Search", nodes=(*nodes, remote), edges=()),
        context_links={
            **{node.id: f"articles.html#{node.id}" for node in nodes},
            remote.id: "other.html#node=remote%2Fdeep-theorem",
        },
    )
    (tmp_path / "viewer.js").write_text(dag_viewer.viewer_script(), encoding="utf-8")

    fallback_links = tuple((node.title, links[node.id]) for node in core_nodes)
    explorer = dag_viewer.render_container(
        "graph.json",
        script_href="viewer.js",
        fallback_links=fallback_links,
        fallback_total=len(nodes),
        layout="embedded",
        search_href="search.json",
    )
    failed_explorer = dag_viewer.render_container(
        "missing.json",
        script_href="viewer.js",
        fallback_links=fallback_links,
        fallback_total=len(nodes),
        layout="embedded",
        search_href="search.json",
    )
    app_explorer = dag_viewer.render_container(
        "graph.json",
        script_href="viewer.js",
        fallback_links=fallback_links,
        fallback_total=len(nodes),
        layout="app",
        search_href="search.json",
    )
    page_shell = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Autoform explorer regression fixture</title>
  <style>
    body { margin: 0; font-family: sans-serif; }
    .page-spacer { height: 48rem; }
    .fixture { max-width: 76rem; margin: 0 auto; padding: 1rem; }
  </style>
</head>
<body>
  <div class="page-spacer" data-page-spacer="before"></div>
  <main class="fixture">{explorer}</main>
  <div class="page-spacer" data-page-spacer="after"></div>
</body>
</html>
"""
    app_shell = (
        page_shell.replace('<div class="page-spacer" data-page-spacer="before"></div>', "")
        .replace('<div class="page-spacer" data-page-spacer="after"></div>', "")
        .replace('class="fixture"', 'class="fixture" style="max-width:none;padding:0"')
    )
    (tmp_path / "index.html").write_text(page_shell.replace("{explorer}", explorer), encoding="utf-8")
    (tmp_path / "failure.html").write_text(page_shell.replace("{explorer}", failed_explorer), encoding="utf-8")
    (tmp_path / "duplicate.html").write_text(
        page_shell.replace("{explorer}", explorer + '\n<script defer src="viewer.js"></script>'),
        encoding="utf-8",
    )
    (tmp_path / "other.html").write_text("<!doctype html><title>Remote scope</title>", encoding="utf-8")
    (tmp_path / "app.html").write_text(app_shell.replace("{explorer}", app_explorer), encoding="utf-8")
    dense_nodes = tuple(
        ViewNode(
            id=f"dense/chapter-{index}",
            title=f"Dense chapter {index}",
            kind="scope",
            members=(f"dense/chapter-{index}/item",),
            status_counts=(("planned", 1),),
            status_key="planned",
        )
        for index in range(33)
    )
    dense_views = {
        "chain": GraphView(
            kind="project",
            title="Connected chain",
            nodes=dense_nodes,
            edges=tuple(
                ViewEdge(dense_nodes[index].id, dense_nodes[index + 1].id, statement_count=1)
                for index in range(len(dense_nodes) - 1)
            ),
        ),
        "star": GraphView(
            kind="project",
            title="Connected star",
            nodes=dense_nodes,
            edges=tuple(
                ViewEdge(dense_nodes[0].id, dense_nodes[index].id, statement_count=1)
                for index in range(1, len(dense_nodes))
            ),
        ),
    }
    flat_nodes = tuple(
        ViewNode(
            id=f"flat/item-{index}",
            title=f"Flat item {index}",
            kind="node",
            members=(f"flat/item-{index}",),
            status_counts=(("planned", 1),),
            status_key="planned",
        )
        for index in range(1_000)
    )
    dense_views["flat"] = GraphView(kind="chapter", title="Flat scope", nodes=flat_nodes, edges=())
    mixed_nodes = tuple(
        ViewNode(
            id=node_id,
            title=node_id,
            kind="node",
            members=(node_id,),
            status_counts=(("planned", 1),),
            status_key="planned",
        )
        for node_id in ("mixed/a", "mixed/b", "mixed/isolate-1", "mixed/isolate-2")
    )
    dense_views["mixed"] = GraphView(
        kind="chapter",
        title="Mixed scope",
        nodes=mixed_nodes,
        edges=(ViewEdge("mixed/a", "mixed/b", statement_count=1),),
    )
    atlas_nodes = (
        ViewNode(
            id="atlas/topology",
            title="Topology",
            kind="scope",
            members=tuple(f"atlas/topology/item-{index}" for index in range(80)),
            status_counts=(("fully_proved", 60), ("planned", 20)),
            status_key="planned",
            summary="Topology studies continuity, deformation, and invariants preserved by continuous maps.",
            area="Geometry & Topology",
        ),
        ViewNode(
            id="atlas/algebra",
            title="Algebra",
            kind="scope",
            members=tuple(f"atlas/algebra/item-{index}" for index in range(40)),
            status_counts=(("fully_proved", 40),),
            status_key="fully_proved",
            summary="Algebra organizes structures and the maps that preserve them.",
            area="Algebra",
        ),
        ViewNode(
            id="atlas/analysis",
            title="Analysis",
            kind="scope",
            members=tuple(f"atlas/analysis/item-{index}" for index in range(20)),
            status_counts=(("can_prove", 20),),
            status_key="can_prove",
            summary="Analysis studies limits, approximation, measure, and functional spaces.",
            area="Analysis & Probability",
        ),
    )
    dense_views["atlas"] = GraphView(kind="project", title="Knowledge atlas", nodes=atlas_nodes, edges=())
    for name, dense_view in dense_views.items():
        links = (
            {node.id: f"other.html#node={node.id}" for node in dense_view.nodes}
            if name == "atlas"
            else {}
        )
        dag_viewer.write_payload(tmp_path / f"{name}.json", dense_view, links=links)
        host = dag_viewer.render_container(f"{name}.json", script_href="viewer.js", layout="app")
        (tmp_path / f"{name}.html").write_text(
            app_shell.replace("{explorer}", host),
            encoding="utf-8",
        )

    with _served(tmp_path) as url:
        yield url


@pytest.fixture(scope="module")
def site_url(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    """Serve a blueprint as render and MkDocs publish it, under Material's styles and scripts."""
    from mkdocs.commands.build import build
    from mkdocs.config import load_config

    project = tmp_path_factory.mktemp("site") / "project"
    scaffold_project(project, title="Explorer fixture")
    roadmap = project / "blueprint/roadmap"
    (roadmap / "README.md").write_text(
        "# Fixture roadmap\n\n- [Algebra](algebra/README.md)\n- [Topology](topology/README.md)\n",
        encoding="utf-8",
    )
    for chapter in ("Algebra", "Topology"):
        folder = roadmap / chapter.lower()
        folder.mkdir()
        (folder / "README.md").write_text(
            f"# {chapter}\n\n- [Base](base.md)\n- [Result](result.md)\n",
            encoding="utf-8",
        )
        (folder / "base.md").write_text(
            "---\ndeclaration: def\n---\n\n# Base\n\nThe base object.\n\n## Depends on\n\nNo prerequisites.\n",
            encoding="utf-8",
        )
        (folder / "result.md").write_text(
            "---\ndeclaration: theorem\n---\n\n# Result\n\nThe main result.\n\n## Depends on\n\n- [Base](base.md)\n",
            encoding="utf-8",
        )
    render_site(project / "blueprint", project / "site-src")
    build(load_config(config_file=str(project / "mkdocs.yml")))
    with _served(project / "site") as url:
        yield url


def _offline(page: object, site_url: str) -> object:
    """Keep a built site's CDN scripts and web fonts off the network."""
    page.route(lambda url: not url.startswith(site_url), lambda route: route.abort())
    return page


def _open_ready(page: object, explorer_url: str) -> None:
    page.goto(f"{explorer_url}/index.html")
    page.locator(".bp-dag-stage").wait_for()
    page.locator("[data-autoform-node-id]").first.wait_for()
    playwright.expect(page.locator("main")).to_have_count(1)


def _load_search_index(page: object) -> object:
    """Focus the search box and wait until the whole-roadmap index has loaded."""
    search = page.locator(".bp-dag-search")
    search.focus()
    playwright.expect(search).to_have_attribute("placeholder", "Search 64 roadmap entries")
    return search


def test_mobile_node_interaction_and_selected_sheet_collapse(mobile_page: object, explorer_url: str) -> None:
    page = mobile_page
    _open_ready(page, explorer_url)

    node = page.locator('[data-autoform-node-id="chapter/middle"]')
    node.tap()

    playwright.expect(node).to_have_attribute("data-selected", "true")
    playwright.expect(page.locator(".bp-dag-inspector h2")).to_have_text("Middle lemma")
    handle = page.locator(".bp-dag-sheet-handle")
    inspector_inner = page.locator(".bp-dag-inspector-inner")
    playwright.expect(handle).to_have_attribute("aria-expanded", "true")
    playwright.expect(handle).to_have_attribute("aria-controls", "bp-dag-inspector-content-1")
    assert inspector_inner.get_attribute("aria-hidden") is None
    assert inspector_inner.get_attribute("inert") is None
    assert "node=chapter%2Fmiddle" in page.url

    handle.tap()
    playwright.expect(handle).to_have_attribute("aria-expanded", "false")
    playwright.expect(inspector_inner).to_have_attribute("aria-hidden", "true")
    playwright.expect(inspector_inner).to_have_attribute("inert", "")
    assert not page.locator(".bp-dag-viewer").evaluate(
        "element => element.classList.contains('bp-dag-sheet-open')"
    )
    handle.focus()
    page.keyboard.press("Tab")
    assert not page.evaluate(
        "document.querySelector('.bp-dag-inspector-inner').contains(document.activeElement)"
    )


def test_app_layout_fills_the_browser_viewport(desktop_page: object, explorer_url: str) -> None:
    page = desktop_page
    page.set_viewport_size({"width": 1440, "height": 900})
    page.goto(f"{explorer_url}/app.html")
    page.locator(".bp-dag-stage").wait_for()
    viewer = page.locator('.bp-dag-viewer[data-layout="app"]')
    box = viewer.bounding_box()
    assert box is not None
    assert box["x"] <= 1
    assert box["y"] <= 1
    assert box["width"] >= 1430
    assert box["height"] >= 890
    stage = page.locator(".bp-dag-stage").bounding_box()
    assert stage is not None
    assert stage["width"] >= 1000


@pytest.mark.parametrize("page_name", ("chain", "star"))
def test_connected_project_maps_open_at_readable_scale(
    desktop_page: object, explorer_url: str, page_name: str
) -> None:
    page = desktop_page
    page.set_viewport_size({"width": 1440, "height": 900})
    page.goto(f"{explorer_url}/{page_name}.html")
    node = page.locator(".bp-dag-node").first
    node.wait_for()
    box = node.bounding_box()
    assert box is not None
    assert box["height"] >= 44
    playwright.expect(page.locator(".bp-dag-density")).to_contain_text("Readable window")


def test_atlas_bubbles_open_authored_mathematical_context(
    desktop_page: object, explorer_url: str
) -> None:
    page = desktop_page
    page.set_viewport_size({"width": 1440, "height": 900})
    page.goto(f"{explorer_url}/atlas.html")
    topic = page.locator('[data-autoform-node-id="atlas/topology"]')
    topic.wait_for()
    assert page.locator(".bp-dag-viewer").evaluate(
        "element => element.classList.contains('bp-dag-atlas')"
    )
    playwright.expect(page.locator(".bp-dag-inspector h2")).to_have_text("Knowledge atlas")
    # Every topic of an edgeless atlas is isolated, so hiding them would empty the map.
    playwright.expect(page.locator(".bp-dag-isolated")).to_be_hidden()
    playwright.expect(page.locator(".bp-dag-inspector")).to_contain_text("Geometry & Topology")
    # Each status row carries the swatch and meaning the hidden page legend held.
    playwright.expect(
        page.locator('.bp-dag-inspector .bp-dag-swatch[title="Proved, and every prerequisite is fully proved too."]')
    ).to_have_count(1)
    playwright.expect(page.locator(".bp-dag-inspector")).to_contain_text(
        "No cross-topic dependency links are authored"
    )
    assert "50%" in topic.evaluate("element => getComputedStyle(element).borderRadius")
    assert "conic-gradient" in topic.evaluate("element => getComputedStyle(element).backgroundImage")
    topic.click()
    playwright.expect(page.locator(".bp-dag-inspector h2")).to_have_text("Topology")
    playwright.expect(page.locator(".bp-dag-summary")).to_contain_text(
        "continuity, deformation, and invariants"
    )
    playwright.expect(page.get_by_role("link", name="Explore topic")).to_be_visible()


def test_oversized_flat_scope_defaults_to_browse(desktop_page: object, explorer_url: str) -> None:
    page = desktop_page
    page.set_viewport_size({"width": 1440, "height": 900})
    page.goto(f"{explorer_url}/flat.html")
    inventory = page.locator(".bp-dag-inventory")
    inventory.wait_for()
    playwright.expect(inventory).to_be_visible()
    playwright.expect(page.locator(".bp-dag-mode-button").first).to_be_disabled()
    playwright.expect(page.locator(".bp-dag-inventory-summary")).to_contain_text(
        "map unavailable above 120 items"
    )
    playwright.expect(page.locator(".bp-dag-node")).to_have_count(0)


def test_mobile_browse_pagination_stays_above_the_collapsed_sheet(
    mobile_page: object, explorer_url: str
) -> None:
    page = mobile_page
    page.goto(f"{explorer_url}/flat.html")
    more = page.locator(".bp-dag-inventory > .bp-dag-load-more")
    more.wait_for()
    more.scroll_into_view_if_needed()
    box = more.bounding_box()
    handle_box = page.locator(".bp-dag-sheet-handle").bounding_box()
    assert box is not None and handle_box is not None
    assert box["y"] + box["height"] <= handle_box["y"]
    more.tap()
    playwright.expect(page.locator(".bp-dag-inventory-summary")).to_contain_text("200 of 1000 listed")


def test_mobile_isolates_do_not_overlap_the_connected_dag(mobile_page: object, explorer_url: str) -> None:
    page = mobile_page
    page.goto(f"{explorer_url}/mixed.html")
    connected = page.locator('[data-autoform-node-id="mixed/a"]')
    isolated = page.locator('[data-autoform-node-id="mixed/isolate-1"]')
    connected.wait_for()
    isolated.wait_for()
    a, b = connected.bounding_box(), isolated.bounding_box()
    assert a is not None and b is not None
    assert a["y"] + a["height"] <= b["y"] or b["y"] + b["height"] <= a["y"]
    playwright.expect(page.locator(".bp-dag-isolated")).to_be_visible()


def test_plain_wheel_scrolls_the_page_instead_of_being_trapped(desktop_page: object, explorer_url: str) -> None:
    page = desktop_page
    page.set_viewport_size({"width": 1280, "height": 720})
    _open_ready(page, explorer_url)
    stage = page.locator(".bp-dag-stage")
    stage.scroll_into_view_if_needed()
    box = stage.bounding_box()
    assert box is not None
    before = page.evaluate("window.scrollY")

    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.mouse.wheel(0, 420)

    page.wait_for_function("before => window.scrollY > before", arg=before)
    assert page.evaluate("window.scrollY") > before


def test_search_keyboard_navigation_and_focus(desktop_page: object, explorer_url: str) -> None:
    page = desktop_page
    _open_ready(page, explorer_url)
    search = _load_search_index(page)
    search.fill("middle")
    playwright.expect(search).to_have_attribute("aria-expanded", "true")

    search.press("ArrowDown")
    result = page.locator(".bp-dag-result").first
    playwright.expect(result).to_be_focused()
    result.press("Escape")
    playwright.expect(search).to_be_focused()
    playwright.expect(search).to_have_attribute("aria-expanded", "false")

    search.fill("target")
    search.press("Enter")
    playwright.expect(page.locator('[data-autoform-node-id="chapter/target"]')).to_be_focused()
    assert "node=chapter%2Ftarget" in page.url


def test_global_search_jumps_to_the_smallest_context(desktop_page: object, explorer_url: str) -> None:
    page = desktop_page
    _open_ready(page, explorer_url)
    search = page.locator(".bp-dag-search")
    search.fill("Remote theorem")
    result = page.locator(".bp-dag-result", has_text="Remote theorem")
    result.wait_for()
    result.click()
    page.wait_for_url("**/other.html#node=remote%2Fdeep-theorem")


def test_legacy_node_hash_resolves_through_the_global_index(desktop_page: object, explorer_url: str) -> None:
    page = desktop_page
    page.goto(f"{explorer_url}/app.html#node=remote%2Fdeep-theorem")
    page.wait_for_url("**/other.html#node=remote%2Fdeep-theorem")

    navigations: list[str] = []
    page.on("request", lambda request: navigations.append(request.url) if request.is_navigation_request() else None)
    with page.expect_response("**/search.json"):
        page.goto(f"{explorer_url}/app.html#node=unknown%2Fitem")
    # The placeholder changes in the same promise chain, just before the redirect decision.
    playwright.expect(page.locator(".bp-dag-search")).to_have_attribute("placeholder", "Search 64 roadmap entries")
    # One more task lets a redirect that decision started reach the network.
    page.evaluate("() => new Promise(done => setTimeout(done))")
    assert page.url.endswith("app.html#node=unknown%2Fitem")
    assert len(navigations) == 1


def test_paginated_search_and_arrow_navigation_restore_focus(
    desktop_page: object, explorer_url: str
) -> None:
    page = desktop_page
    _open_ready(page, explorer_url)
    foundation = page.locator('[data-autoform-node-id="chapter/foundation"]')
    foundation.focus()
    foundation.press("ArrowRight")
    playwright.expect(page.locator('[data-autoform-node-id="chapter/middle"]')).to_be_focused()

    search = _load_search_index(page)
    search.fill("auxiliary")
    more = page.locator(".bp-dag-search-results .bp-dag-load-more")
    playwright.expect(more).to_have_text("Show 48 more of 48")
    more.focus()
    more.press("Enter")
    playwright.expect(page.locator(".bp-dag-result").nth(12)).to_be_focused()


def test_direct_list_view_has_current_shown_and_hidden_counts(
    desktop_page: object, explorer_url: str
) -> None:
    page = desktop_page
    page.goto(f"{explorer_url}/index.html#view=list&status=fully_proved")
    page.locator(".bp-dag-inventory").wait_for()
    playwright.expect(page.locator(".bp-dag-stats")).to_contain_text("1 of 63 shown")
    playwright.expect(page.locator(".bp-dag-hidden-button")).to_have_text("+62 hidden")


def test_reselect_does_not_duplicate_history_and_back_restores_selection(
    desktop_page: object, explorer_url: str
) -> None:
    page = desktop_page
    _open_ready(page, explorer_url)
    foundation = page.locator('[data-autoform-node-id="chapter/foundation"]')
    target = page.locator('[data-autoform-node-id="chapter/target"]')
    initial_length = page.evaluate("history.length")

    foundation.click()
    after_first_selection = page.evaluate("history.length")
    foundation.click()
    assert page.evaluate("history.length") == after_first_selection == initial_length + 1

    target.click()
    assert page.evaluate("history.length") == initial_length + 2
    page.evaluate("history.back()")
    page.wait_for_function("location.hash.includes('chapter%2Ffoundation')")
    playwright.expect(page.locator(".bp-dag-inspector h2")).to_have_text("Foundation")
    playwright.expect(foundation).to_have_attribute("data-selected", "true")


def test_hiding_the_selected_status_clears_selection(
    desktop_page: object, explorer_url: str
) -> None:
    page = desktop_page
    _open_ready(page, explorer_url)
    page.locator('[data-autoform-node-id="chapter/target"]').click()
    assert "node=chapter%2Ftarget" in page.url

    page.locator(".bp-dag-filter-summary").click()
    page.locator('.bp-dag-filter-popover input[value="planned"]').uncheck()

    assert "node=" not in page.url
    assert "bp-dag-has-selection" not in (page.locator(".bp-dag-viewer").get_attribute("class") or "")


def test_no_javascript_keeps_the_linked_fallback(webkit_browser: object, explorer_url: str) -> None:
    with _page(webkit_browser, java_script_enabled=False) as page:
        page.goto(f"{explorer_url}/index.html")

        fallback = page.locator(".bp-dag-fallback")
        playwright.expect(fallback).to_be_visible()
        playwright.expect(fallback.locator("li")).to_have_count(3)
        playwright.expect(fallback.get_by_role("link", name="Download the complete graph data")).to_have_attribute(
            "href", "graph.json"
        )


def test_fetch_failure_restores_the_linked_fallback(desktop_page: object, explorer_url: str) -> None:
    page = desktop_page
    page.goto(f"{explorer_url}/failure.html")

    playwright.expect(page.locator(".bp-dag-error")).to_contain_text("HTTP 404")
    fallback = page.locator(".bp-dag-fallback")
    playwright.expect(fallback).to_be_visible()
    playwright.expect(fallback.get_by_role("link", name="Middle lemma")).to_have_attribute(
        "href", "articles.html#chapter/middle"
    )


def test_duplicate_script_include_mounts_one_explorer(
    desktop_page: object, explorer_url: str
) -> None:
    page = desktop_page
    page.goto(f"{explorer_url}/duplicate.html")
    page.locator(".bp-dag-stage").wait_for()
    playwright.expect(page.locator(".bp-dag-head")).to_have_count(1)


@pytest.mark.parametrize("viewport", ({"width": 390, "height": 844}, {"width": 844, "height": 390}))
def test_a_published_canvas_covers_exactly_its_stage(
    desktop_page: object, site_url: str, viewport: dict[str, int]
) -> None:
    """Site CSS once gave the canvas a 30rem floor, stretching drawings away from short stages' nodes."""
    page = _offline(desktop_page, site_url)
    page.set_viewport_size(viewport)
    page.goto(f"{site_url}/dependencies.html")
    page.locator(".bp-dag-node").first.wait_for()
    canvas = page.locator(".bp-dag-canvas").bounding_box()
    stage = page.locator(".bp-dag-stage").bounding_box()
    assert canvas is not None and stage is not None
    assert abs(canvas["height"] - stage["height"]) < 1
    assert abs(canvas["width"] - stage["width"]) < 1


def test_the_published_landing_map_leaves_one_finger_scrolling_to_the_page(
    mobile_page: object, site_url: str
) -> None:
    page = _offline(mobile_page, site_url)
    page.goto(f"{site_url}/index.html")
    canvas = page.locator(".bp-dag-canvas")
    canvas.wait_for()
    assert canvas.evaluate("element => getComputedStyle(element).touchAction") != "none"


def test_the_published_atlas_hides_the_isolate_toggle(desktop_page: object, site_url: str) -> None:
    page = _offline(desktop_page, site_url)
    page.goto(f"{site_url}/dependencies.html")
    page.locator(".bp-dag-node").first.wait_for()
    playwright.expect(page.locator(".bp-dag-isolated")).to_be_hidden()


def test_published_explorer_controls_keep_their_own_styles_under_material(
    desktop_page: object, site_url: str
) -> None:
    """Material's typeset rules stacked the breadcrumb and drew the status filter as an admonition."""
    page = _offline(desktop_page, site_url)
    page.goto(f"{site_url}/dependencies/chapters/algebra.html")
    page.locator(".bp-dag-node").first.wait_for()

    crumbs = page.locator(".bp-dag-breadcrumb li")
    playwright.expect(crumbs).to_have_count(3)
    assert len({round(crumbs.nth(index).bounding_box()["y"]) for index in range(3)}) == 1
    summary = page.locator(".bp-dag-filter-summary")
    background = page.locator(".bp-dag-viewer").evaluate("element => getComputedStyle(element).backgroundColor")
    assert summary.evaluate("element => getComputedStyle(element).backgroundColor") == background
    assert summary.evaluate("element => getComputedStyle(element).borderLeftStyle") == "solid"
    page.locator(".bp-dag-search").fill("Result")
    results = page.locator(".bp-dag-results")
    results.wait_for()
    assert results.evaluate("element => getComputedStyle(element).listStyleType") == "none"
    assert results.locator("li").first.evaluate("element => getComputedStyle(element).marginLeft") == "0px"


def _assert_site_chrome_is_reachable(page: object) -> None:
    """The header, heading and navigation are visible, and each is the element a click would hit."""
    for chrome in (
        page.locator(".md-header"),
        page.get_by_role("heading", level=1),
        page.get_by_role("link", name="Open textbook chapter").first,
    ):
        playwright.expect(chrome).to_be_visible()
        chrome.click(trial=True, timeout=5_000)


def test_a_published_app_page_without_script_keeps_the_site_chrome(webkit_browser: object, site_url: str) -> None:
    """The full-viewport layout belongs to the script, so it cannot cover the page before it runs."""
    with _page(webkit_browser, java_script_enabled=False) as page:
        _offline(page, site_url)
        page.goto(f"{site_url}/dependencies/chapters/algebra.html")
        # Checked first: without script, the trial click on the textbook link follows it.
        loading = page.locator(".bp-dag-loading")
        playwright.expect(loading).to_be_attached()
        playwright.expect(loading).to_be_hidden()
        _assert_site_chrome_is_reachable(page)


def test_a_published_app_page_restores_the_site_chrome_when_its_data_fails(
    desktop_page: object, site_url: str
) -> None:
    page = _offline(desktop_page, site_url)
    page.route("**/algebra.json", lambda route: route.fulfill(status=404, body=""))
    page.goto(f"{site_url}/dependencies/chapters/algebra.html")
    playwright.expect(page.locator(".bp-dag-error")).to_contain_text("HTTP 404")
    _assert_site_chrome_is_reachable(page)
    assert "bp-dag-app-page" not in (page.locator("body").get_attribute("class") or "")


def test_a_published_chapter_explorer_links_its_textbook_chapter_and_keeps_its_heading(
    desktop_page: object, site_url: str
) -> None:
    """Script hides the page heading and navigation behind the explorer, so the explorer carries them."""
    page = _offline(desktop_page, site_url)
    page.goto(f"{site_url}/dependencies/chapters/algebra.html")
    page.locator(".bp-dag-node").first.wait_for()
    playwright.expect(page.locator(".bp-dag-book")).to_have_attribute("href", "../../roadmap/algebra/index.html")
    playwright.expect(page.locator(".bp-dag-book")).to_be_visible()
    playwright.expect(page.get_by_role("heading", level=1)).to_have_text("Algebra dependencies")
