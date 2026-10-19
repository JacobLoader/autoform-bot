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


# Module scope: Playwright's event loop stays running while the browser is open,
# and asyncio.run() in later test modules refuses to start under it.
@pytest.fixture(scope="module")
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
            # Long enough to fill a phone's sheet to its height cap.
            summary=" ".join(
                ["The target theorem gathers the foundation and the middle lemma into one statement."] * 6
            ),
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
        kind="chapter",
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
        lean="Remote.Namespace.deepTheorem",
        summary="A spectral gap statement for the remote fixture.",
    )
    dag_viewer.write_search_index(
        tmp_path / "search.json",
        GraphView(kind="full", title="Search", nodes=(*nodes, remote), edges=()),
        context_links={
            # Index records link explorer contexts, never the articles the view links.
            **{node.id: f"index.html#node={node.id}" for node in nodes},
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
        search_href="search.json",
    )
    failed_explorer = dag_viewer.render_container(
        "missing.json",
        script_href="viewer.js",
        fallback_links=fallback_links,
        fallback_total=len(nodes),
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
  </style>
</head>
<body>
  <main>{explorer}</main>
</body>
</html>
"""
    (tmp_path / "index.html").write_text(page_shell.replace("{explorer}", explorer), encoding="utf-8")
    (tmp_path / "failure.html").write_text(page_shell.replace("{explorer}", failed_explorer), encoding="utf-8")
    (tmp_path / "duplicate.html").write_text(
        page_shell.replace("{explorer}", explorer + '\n<script defer src="viewer.js"></script>'),
        encoding="utf-8",
    )
    (tmp_path / "other.html").write_text("<!doctype html><title>Remote scope</title>", encoding="utf-8")
    (tmp_path / "app.html").write_text(page_shell.replace("{explorer}", explorer), encoding="utf-8")
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
            status_counts=(("fully_proved", 60), ("can_prove", 20)),
            status_key="can_prove",
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
        # Only module inventories: a topic with no target rolls up to planned.
        ViewNode(
            id="atlas/library",
            title="Library",
            kind="scope",
            members=(),
            status_counts=(("inventory_checked", 5),),
            status_key="planned",
            area="Algebra",
        ),
    )
    atlas_areas = (
        "Algebra & Number Theory",
        "Analysis & Probability",
        "Discrete Mathematics & Computation",
        "Foundations & Logic",
        "Geometry & Topology",
    )
    atlas_nodes += tuple(
        ViewNode(
            id=f"atlas/auxiliary-{index}",
            title=f"Auxiliary topic {index}",
            kind="scope",
            members=tuple(f"atlas/auxiliary-{index}/item-{item}" for item in range(10 + index * 7)),
            status_counts=(("planned", 10 + index * 7),),
            status_key="planned",
            area=atlas_areas[index % len(atlas_areas)],
        )
        for index in range(26)
    )
    dense_views["atlas"] = GraphView(
        kind="project",
        title="Knowledge atlas",
        nodes=atlas_nodes,
        edges=(
            ViewEdge("atlas/algebra", "atlas/topology", statement_count=3),
            ViewEdge("atlas/analysis", "atlas/topology", statement_count=2),
        ),
    )
    dense_views["topics"] = GraphView(
        kind="chapter",
        title="Topics and results",
        nodes=(
            ViewNode("topics/compactness", "Compactness", "scope", ("topics/compactness/a",), (("planned", 1),)),
            ViewNode("topics/heine-borel", "Heine-Borel theorem", "node", ("topics/heine-borel",), (("planned", 1),)),
            ViewNode("topics/tychonoff", "Tychonoff theorem", "node", ("topics/tychonoff",), (("planned", 1),)),
            # Ten names, the first holding ", " inside guillemets, of which the explorer shows eight.
            ViewNode(
                "topics/library",
                "Topology library",
                "node",
                ("topics/library",),
                (("inventory_checked", 1),),
                catalog="module",
                lean=", ".join(["Topology.«open, closed»", *(f"Topology.lemma{index}" for index in range(2, 11))]),
            ),
        ),
        edges=(),
    )
    dense_views["empty"] = GraphView(kind="project", title="Fresh roadmap", nodes=(), edges=())
    for name, dense_view in dense_views.items():
        links = (
            {node.id: f"other.html#node={node.id}" for node in dense_view.nodes}
            if name == "atlas"
            else {}
        )
        dag_viewer.write_payload(tmp_path / f"{name}.json", dense_view, links=links)
        host = dag_viewer.render_container(f"{name}.json", script_href="viewer.js")
        (tmp_path / f"{name}.html").write_text(
            page_shell.replace("{explorer}", host),
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


def _open_site(page: object, site_url: str, path: str) -> object:
    """Open a page of the built site, offline, once its explorer has drawn a node."""
    _offline(page, site_url)
    page.goto(f"{site_url}/{path}")
    page.locator(".bp-dag-node").first.wait_for()
    return page


def _open_ready(page: object, explorer_url: str) -> None:
    page.goto(f"{explorer_url}/index.html")
    page.locator(".bp-dag-stage").wait_for()
    page.locator("[data-autoform-node-id]").first.wait_for()
    playwright.expect(page.locator("main")).to_have_count(1)


def _load_search_index(page: object, entries: int = 64) -> object:
    """Focus the search box and wait until the whole-roadmap index of *entries* records has loaded."""
    search = page.locator(".bp-dag-search")
    search.focus()
    playwright.expect(search).to_have_attribute("placeholder", f"Search {entries} roadmap entries")
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
    viewer = page.locator(".bp-dag-viewer")
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


def test_atlas_hierarchy_keeps_topics_readable_and_details_out_of_the_way(
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
    navigation = page.locator(".bp-dag-navigation")
    playwright.expect(navigation).to_be_visible()
    playwright.expect(navigation).to_contain_text("Knowledge atlas")
    playwright.expect(navigation).to_contain_text("Geometry & Topology")
    playwright.expect(page.locator(".bp-dag-inspector")).to_be_hidden()
    # The closed drawer still holds the overview. Topics count once, by their least-complete item,
    # unlike the rings' items, and each status row carries the swatch and meaning the hidden page legend held.
    playwright.expect(page.locator(".bp-dag-inspector h3", has_text="status")).to_have_text(
        "Topics by least-complete status"
    )
    playwright.expect(
        page.locator('.bp-dag-inspector .bp-dag-swatch[title="Proved, and every prerequisite is fully proved too."]')
    ).to_have_count(1)
    stage_width = page.locator(".bp-dag-stage").bounding_box()["width"]
    topic_box = topic.bounding_box()
    assert topic_box is not None and topic_box["height"] >= 62 and topic_box["width"] >= 150
    assert "50%" not in topic.evaluate("element => getComputedStyle(element).borderRadius")
    ring = topic.evaluate("element => getComputedStyle(element).backgroundImage")
    assert "conic-gradient" in ring
    # The ring follows the legend's state order: finished green before ready-to-prove blue.
    assert ring.index("rgb(34, 119, 58)") < ring.index("rgb(0, 100, 224)")
    # The region is canvas text, which assistive technology never reads.
    assert "Geometry & Topology" in (topic.get_attribute("aria-label") or "")
    topic.click()
    playwright.expect(page.locator(".bp-dag-inspector h2")).to_have_text("Topology")
    playwright.expect(page.locator(".bp-dag-inspector .bp-dag-kicker")).to_have_text("Scope · Geometry & Topology")
    playwright.expect(page.locator(".bp-dag-inspector h3", has_text="in this scope")).to_have_text(
        "80 items in this scope"
    )
    playwright.expect(page.locator(".bp-dag-summary")).to_contain_text(
        "continuity, deformation, and invariants"
    )
    playwright.expect(page.get_by_role("link", name="Explore topic")).to_be_visible()
    playwright.expect(page.locator('[data-autoform-node-id="atlas/algebra"]')).to_have_attribute(
        "data-relation", "prerequisite"
    )
    selected_stage_width = page.locator(".bp-dag-stage").bounding_box()["width"]
    assert abs(selected_stage_width - stage_width) < 2
    playwright.expect(navigation.locator('[data-navigation-node-id="atlas/topology"]')).to_have_attribute(
        "aria-current", "true"
    )
    # A topic made only of module inventories says so instead of its rolled-up planned status.
    # The open drawer overlays the map, so this card is chosen without the pointer.
    page.locator('[data-autoform-node-id="atlas/library"]').dispatch_event("click")
    playwright.expect(page.locator(".bp-dag-status-pill")).to_have_text("inventory only")
    # Contents names each topic's region, which the map paints only on the canvas.
    page.get_by_role("button", name="Contents").click()
    topology = page.locator(".bp-dag-inventory-row").filter(has=page.get_by_text("atlas/topology", exact=True))
    playwright.expect(topology.locator(".bp-dag-inventory-meta")).to_contain_text("Geometry & Topology")


def test_a_view_of_topics_and_results_draws_readable_result_cards(desktop_page: object, explorer_url: str) -> None:
    """An edgeless view with a topic drew its results as 76px atlas squares showing a few characters."""
    page = desktop_page
    page.goto(f"{explorer_url}/topics.html")
    title = page.locator('[data-autoform-node-id="topics/heine-borel"] .bp-dag-node-title')
    title.wait_for()
    assert not page.locator(".bp-dag-viewer").evaluate("element => element.classList.contains('bp-dag-atlas')")
    assert title.evaluate("element => element.scrollWidth <= element.clientWidth")
    meta = page.locator('[data-autoform-node-id="topics/compactness"] .bp-dag-node-meta')
    playwright.expect(meta).to_have_text("1 item · 0 internal links")
    # A drawn DAG counts its nodes by status; only an atlas counts topics by their least-complete item.
    playwright.expect(page.locator(".bp-dag-inspector h3")).to_have_text("Nodes by status")
    page.locator('[data-autoform-node-id="topics/library"]').click()
    playwright.expect(page.locator(".bp-dag-lean")).to_contain_text("Topology.lemma8 and 2 more")


def test_a_roadmap_without_articles_says_so(desktop_page: object, explorer_url: str) -> None:
    """An empty project view said that no node matched controls the reader never touched."""
    page = desktop_page
    page.goto(f"{explorer_url}/empty.html")
    empty = page.locator(".bp-dag-empty")
    playwright.expect(empty).to_be_visible()
    playwright.expect(empty).to_have_text("This roadmap has no articles yet.")


def test_a_click_on_empty_map_space_keeps_the_readers_zoom(desktop_page: object, explorer_url: str) -> None:
    """Every click on empty space re-fitted the camera, with or without a selection to clear."""
    page = desktop_page
    # Wide enough beside the hierarchy rail that the map fits at a readable scale and zooms about its centre.
    page.set_viewport_size({"width": 1440, "height": 900})
    page.goto(f"{explorer_url}/mixed.html")
    page.locator("[data-autoform-node-id]").first.wait_for()
    page.get_by_role("button", name="Zoom in").click()
    frames = "() => new Promise(done => requestAnimationFrame(() => requestAnimationFrame(done)))"
    transforms = "() => Array.from(document.querySelectorAll('.bp-dag-node'), node => node.style.transform)"

    def click_empty_space() -> None:
        empty = page.evaluate(
            """() => {
              const stage = document.querySelector(".bp-dag-stage").getBoundingClientRect();
              for (let y = stage.top + 8; y < stage.bottom; y += 16)
                for (let x = stage.left + 8; x < stage.right; x += 16)
                  if (document.elementFromPoint(x, y)?.classList.contains("bp-dag-canvas")) return [x, y];
              return null;
            }"""
        )
        assert empty is not None
        page.mouse.click(*empty)
        page.evaluate(frames)
        page.evaluate(frames)

    page.evaluate(frames)
    before = page.evaluate(transforms)
    click_empty_space()
    assert page.evaluate(transforms) == before

    # Clearing a selection keeps the zoom too; only clearing a path filter re-fits the map.
    node = page.locator('[data-autoform-node-id="mixed/b"]')
    node.click()
    playwright.expect(node).to_have_attribute("data-selected", "true")
    page.get_by_role("button", name="Zoom in").click()
    page.evaluate(frames)
    before = node.evaluate("node => node.style.transform")
    click_empty_space()
    playwright.expect(node).to_have_attribute("data-selected", "false")
    assert node.evaluate("node => node.style.transform") == before


def test_oversized_flat_scope_defaults_to_contents(desktop_page: object, explorer_url: str) -> None:
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


def test_choosing_from_contents_keeps_the_readers_place_and_focus(desktop_page: object, explorer_url: str) -> None:
    """Each choice from the list scrolled it to its top, and closing the details dropped focus to the page."""
    page = desktop_page
    page.goto(f"{explorer_url}/flat.html")
    page.locator(".bp-dag-inventory > .bp-dag-load-more").click()
    scroll = page.locator(".bp-dag-inventory-scroll")
    row = page.locator(".bp-dag-inventory-row").nth(150)
    row.scroll_into_view_if_needed()
    # Off centre, since focus scrolls a row it reveals to the centre and must not pass for a kept place.
    offset = scroll.evaluate("element => { element.scrollTop += 40; return element.scrollTop; }")
    assert offset > 0

    row.click()
    playwright.expect(row).to_have_attribute("aria-current", "true")
    assert scroll.evaluate("element => element.scrollTop") == offset
    close = page.get_by_role("button", name="Close details")
    close.press("Enter")
    playwright.expect(row).to_be_focused()
    playwright.expect(row).to_have_attribute("aria-current", "true")
    assert scroll.evaluate("element => element.scrollTop") == offset

    # Escape in the details clears the selection and returns focus to its row too.
    row.click()
    close.press("Escape")
    playwright.expect(page.locator(".bp-dag-has-selection")).to_have_count(0)
    playwright.expect(row).to_be_focused()
    assert scroll.evaluate("element => element.scrollTop") == offset

    # Back restores the selection and brings its row into view.
    scroll.evaluate("element => { element.scrollTop = 0; }")
    page.evaluate("history.back()")
    playwright.expect(row).to_have_attribute("aria-current", "true")
    playwright.expect(row).to_be_in_viewport()


def test_a_node_chosen_on_a_phone_lands_above_the_open_sheet(mobile_page: object, explorer_url: str) -> None:
    """Centring in the whole stage put the chosen node under the sheet its selection opens."""
    page = mobile_page
    _open_ready(page, explorer_url)
    search = page.locator(".bp-dag-search")
    search.fill("target")
    search.press("Enter")
    node = page.locator('[data-autoform-node-id="chapter/target"]')
    playwright.expect(node).to_be_focused()
    box, sheet = node.bounding_box(), page.locator(".bp-dag-inspector").bounding_box()
    assert box is not None and sheet is not None
    assert box["y"] + box["height"] <= sheet["y"]


def test_mobile_contents_pagination_stays_above_the_collapsed_sheet(
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


def test_a_plain_wheel_pans_the_full_page_explorer(desktop_page: object, explorer_url: str) -> None:
    """The full-page explorer leaves nothing else to scroll, and a plain wheel or trackpad scroll did nothing there."""
    page = desktop_page
    page.goto(f"{explorer_url}/app.html")
    node = page.locator('[data-autoform-node-id="chapter/middle"]')
    node.wait_for()
    frames = "() => new Promise(done => requestAnimationFrame(() => requestAnimationFrame(done)))"
    page.evaluate(frames)
    before = node.bounding_box()
    stage = page.locator(".bp-dag-stage").bounding_box()
    assert before is not None and stage is not None

    page.mouse.move(stage["x"] + stage["width"] / 2, stage["y"] + stage["height"] / 2)
    page.mouse.wheel(0, -120)
    page.evaluate(frames)
    after = node.bounding_box()
    assert after is not None
    # Scrolling up moves the map down, at the same zoom.
    assert after["y"] > before["y"]
    assert abs(after["height"] - before["height"]) < 0.5

    # Control with the wheel zooms by the size of the step, where it once took a fixed 13% step.
    scale = r"node => Number(/scale\(([^)]+)\)/.exec(node.style.transform)[1])"
    unzoomed = node.evaluate(scale)
    page.keyboard.down("Control")
    page.mouse.wheel(0, -10)
    page.keyboard.up("Control")
    page.evaluate(frames)
    assert 1.0 < node.evaluate(scale) / unzoomed < 1.1


def test_search_keyboard_navigation_and_focus(desktop_page: object, explorer_url: str) -> None:
    page = desktop_page
    _open_ready(page, explorer_url)
    search = _load_search_index(page)
    results = page.locator(".bp-dag-search-results")
    announcement = page.locator(".bp-dag-sr-only")
    # A search box takes no aria-expanded; the result count is announced instead.
    assert search.get_attribute("aria-expanded") is None
    search.fill("no such node")
    playwright.expect(announcement).to_have_text("No results")
    search.fill("middle")
    playwright.expect(results).to_be_visible()
    # The target's statement mentions the middle lemma, so it matches too.
    playwright.expect(announcement).to_have_text("2 results")

    search.press("ArrowDown")
    result = page.locator(".bp-dag-result").first
    playwright.expect(result).to_be_focused()
    result.press("Escape")
    playwright.expect(search).to_be_focused()
    playwright.expect(results).to_be_hidden()
    # Focus moving from the results to a control outside them closes them too.
    search.press("ArrowDown")
    playwright.expect(result).to_be_focused()
    page.get_by_role("button", name="Contents").focus()
    playwright.expect(results).to_be_hidden()

    search.fill("target")
    search.press("Enter")
    playwright.expect(page.locator('[data-autoform-node-id="chapter/target"]')).to_be_focused()
    assert "node=chapter%2Ftarget" in page.url


def test_a_search_result_in_this_view_selects_the_drawn_node(desktop_page: object, explorer_url: str) -> None:
    """Index records carry no layout, so choosing one blanked the map and linked back to the explorer."""
    page = desktop_page
    _open_ready(page, explorer_url)
    search = _load_search_index(page)
    for query, node_id in (("target", "chapter/target"), ("middle", "chapter/middle")):
        search.fill(query)
        if query == "target":
            search.press("Enter")
        else:
            page.locator(".bp-dag-result", has_text="Middle lemma").click()
        node = page.locator(f'[data-autoform-node-id="{node_id}"]')
        playwright.expect(node).to_have_attribute("data-selected", "true")
        # Focus may scroll the page, so both boxes are read once it has moved.
        playwright.expect(node).to_be_focused()
        box, stage = node.bounding_box(), page.locator(".bp-dag-stage").bounding_box()
        assert box is not None and stage is not None
        assert stage["x"] <= box["x"] and box["x"] + box["width"] <= stage["x"] + stage["width"]
        assert stage["y"] <= box["y"] and box["y"] + box["height"] <= stage["y"] + stage["height"]
        assert page.locator(".bp-dag-node").count() > 1
        playwright.expect(page.get_by_role("link", name="Open article")).to_have_attribute(
            "href", f"articles.html#{node_id}"
        )


def test_a_result_neither_drawn_here_nor_safely_linked_selects_nothing(
    desktop_page: object, explorer_url: str
) -> None:
    """Such a record went to chooseNode, which selected a node the map does not draw."""
    page = desktop_page

    def add_unlinked_record(route: object) -> None:
        index = route.fetch().json()
        index["nodes"].append(
            {"id": "elsewhere/unlinked", "kind": "node", "status": "planned", "title": "Unlinked result", "url": None}
        )
        route.fulfill(json=index)

    page.route("**/search.json", add_unlinked_record)
    _open_ready(page, explorer_url)
    search = _load_search_index(page, 65)
    search.fill("Unlinked")
    url = page.url
    page.locator(".bp-dag-result", has_text="Unlinked result").click()
    page.evaluate("() => new Promise(done => requestAnimationFrame(() => requestAnimationFrame(done)))")
    playwright.expect(page.locator(".bp-dag-has-selection")).to_have_count(0)
    assert page.url == url


def test_a_contents_query_lists_only_this_scope(desktop_page: object, explorer_url: str) -> None:
    """Whole-roadmap matches belong to the search dropdown, not under "Contents of this scope".

    The dropdown opened on every keystroke and covered the list being filtered,
    so in Contents it opens only when asked: by Down from the search box, or the
    summary's button, which a touch screen can reach.
    """
    page = desktop_page
    _open_ready(page, explorer_url)
    search = _load_search_index(page)
    page.get_by_role("button", name="Contents").click()
    search.fill("theorem")
    playwright.expect(page.locator(".bp-dag-inventory-title")).to_have_text(["Target theorem"])
    results = page.locator(".bp-dag-search-results")
    playwright.expect(results).to_be_hidden()
    search.press("ArrowDown")
    playwright.expect(page.locator(".bp-dag-result").first).to_be_focused()
    page.keyboard.press("Escape")
    playwright.expect(results).to_be_hidden()
    page.get_by_role("button", name="search the whole roadmap").click()
    playwright.expect(results.locator(".bp-dag-result", has_text="Remote theorem")).to_be_visible()


def test_global_search_jumps_to_the_smallest_context(desktop_page: object, explorer_url: str) -> None:
    page = desktop_page
    _open_ready(page, explorer_url)
    search = page.locator(".bp-dag-search")
    search.fill("Remote.Namespace.deepTheorem")
    playwright.expect(page.locator(".bp-dag-result-reason").first).to_have_text("Exact Lean name")
    search.fill("spectral gap")
    playwright.expect(page.locator(".bp-dag-result", has_text="Remote theorem")).to_be_visible()
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


def _release(page: object, held: list[object]) -> None:
    """Let the oldest held request through once Playwright has delivered it."""
    for _ in range(100):
        if held:
            held.pop(0).continue_()
            return
        page.evaluate("0")
    raise AssertionError("the held request never arrived")


def test_a_late_search_index_keeps_focus_and_leaves_a_closed_panel_closed(
    desktop_page: object, explorer_url: str
) -> None:
    """The index callback rebuilt the dropdown, dropping focus to the page and reopening a closed panel."""
    page = desktop_page
    held: list[object] = []
    page.route("**/search.json", lambda route: held.append(route))
    _open_ready(page, explorer_url)
    search = page.locator(".bp-dag-search")
    results = page.locator(".bp-dag-search-results")
    search.fill("auxiliary")
    more = results.locator(".bp-dag-load-more")
    more.focus()
    more.press("Enter")
    thirteenth = page.locator(".bp-dag-result").nth(12)
    playwright.expect(thirteenth).to_be_focused()
    _release(page, held)
    playwright.expect(search).to_have_attribute("placeholder", "Search 64 roadmap entries")
    playwright.expect(thirteenth).to_be_focused()
    page.mouse.click(2, 2)
    playwright.expect(results).to_be_hidden()

    page.reload()
    page.locator("[data-autoform-node-id]").first.wait_for()
    search.fill("auxiliary")
    search.press("Escape")
    playwright.expect(results).to_be_hidden()
    _release(page, held)
    playwright.expect(search).to_have_attribute("placeholder", "Search 64 roadmap entries")
    playwright.expect(results).to_be_hidden()


def test_direct_list_view_has_current_shown_and_hidden_counts(
    desktop_page: object, explorer_url: str
) -> None:
    page = desktop_page
    page.goto(f"{explorer_url}/index.html#view=list&status=fully_proved")
    page.locator(".bp-dag-inventory").wait_for()
    playwright.expect(page.locator(".bp-dag-stats")).to_contain_text("1 of 63 shown")
    playwright.expect(page.locator(".bp-dag-hidden-button")).to_have_text("+62 hidden")


def test_hidden_items_without_edges_stay_hidden_after_a_reload(desktop_page: object, explorer_url: str) -> None:
    """The location records only that they are hidden, so a reload has to read that back."""
    page = desktop_page
    _open_ready(page, explorer_url)
    isolates = page.get_by_role("checkbox", name="Show items without edges")
    isolates.uncheck()
    page.wait_for_function("location.hash === '#isolates=0'")

    page.reload()
    page.locator("[data-autoform-node-id]").first.wait_for()
    playwright.expect(isolates).not_to_be_checked()
    playwright.expect(page.locator(".bp-dag-hidden-button")).to_have_text("+60 hidden")


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

    page.get_by_role("button", name="Close details").click()
    target.click()
    # Focus follows the click two frames later; waiting for it keeps it from
    # landing during the arrow keys below.
    playwright.expect(target).to_be_focused()
    assert page.evaluate("history.length") == initial_length + 2
    page.evaluate("history.back()")
    page.wait_for_function("location.hash.includes('chapter%2Ffoundation')")
    playwright.expect(page.locator(".bp-dag-inspector h2")).to_have_text("Foundation")
    playwright.expect(foundation).to_have_attribute("data-selected", "true")

    # Arrow keys browse without a history entry per step, so one Back undoes them all.
    middle = page.locator('[data-autoform-node-id="chapter/middle"]')
    foundation.focus()
    foundation.press("ArrowRight")
    playwright.expect(middle).to_be_focused()
    middle.press("ArrowRight")
    playwright.expect(target).to_be_focused()
    page.evaluate("history.back()")
    page.wait_for_function("!location.hash.includes('node=')")

    # From an unselected map the first arrow key adds the entry, so Back returns to the map, not the page before.
    page.goto("about:blank")
    _open_ready(page, explorer_url)
    foundation.focus()
    foundation.press("ArrowRight")
    playwright.expect(middle).to_be_focused()
    middle.press("ArrowRight")
    playwright.expect(target).to_be_focused()
    page.evaluate("history.back()")
    page.wait_for_function("!location.hash.includes('node=')")
    assert page.url == f"{explorer_url}/index.html"


def test_hiding_the_selected_status_clears_selection(
    desktop_page: object, explorer_url: str
) -> None:
    page = desktop_page
    _open_ready(page, explorer_url)
    page.locator('[data-autoform-node-id="chapter/target"]').click()
    assert "node=chapter%2Ftarget" in page.url

    summary = page.locator(".bp-dag-filter-summary")
    popover = page.locator(".bp-dag-filter-popover")
    summary.click()
    # Each status row carries its colour; Escape and a press outside both close the popover.
    playwright.expect(popover.locator(".bp-dag-swatch")).to_have_count(3)
    popover.locator("input").first.press("Escape")
    playwright.expect(popover).to_be_hidden()
    playwright.expect(summary).to_be_focused()
    summary.click()
    page.mouse.click(2, 2)
    playwright.expect(popover).to_be_hidden()

    summary.click()
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
    desktop_page.set_viewport_size(viewport)
    page = _open_site(desktop_page, site_url, "dependencies.html")
    canvas = page.locator(".bp-dag-canvas").bounding_box()
    stage = page.locator(".bp-dag-stage").bounding_box()
    assert canvas is not None and stage is not None
    assert abs(canvas["height"] - stage["height"]) < 1
    assert abs(canvas["width"] - stage["width"]) < 1


def test_the_published_landing_page_is_one_full_page_explorer_opened_by_its_hero(
    desktop_page: object, site_url: str
) -> None:
    """The page stacked a hero, a framed map card and the explorer's own title over a boxed map."""
    page = _open_site(desktop_page, site_url, "index.html")
    box = page.locator(".bp-dag-viewer").bounding_box()
    assert box is not None and (box["width"], box["height"]) == (1280, 900)
    playwright.expect(page.locator(".md-header")).to_be_hidden()
    intro = page.locator(".bp-dag-navigation .bp-dag-intro")
    playwright.expect(intro).to_be_visible()
    headings = page.get_by_role("heading", level=1)
    playwright.expect(headings).to_have_count(1)
    playwright.expect(headings).to_have_text("Explorer fixture")
    playwright.expect(page.locator(".bp-dag-navigation-title")).to_have_count(0)
    playwright.expect(intro.get_by_role("link", name="Read the book")).to_have_attribute("href", "roadmap/index.html")
    # The rail lists the project's chapters under the hero.
    playwright.expect(page.locator(".bp-dag-navigation-link", has_text="Algebra")).to_be_visible()
    # Only autoform dashboard serves the live overlay; this local server answers 404, so no panel opens.
    with page.expect_response(lambda response: response.url.endswith("/__autoform/live.json")):
        page.reload()
    page.locator(".bp-dag-navigation .bp-dag-intro").wait_for()
    playwright.expect(page.locator("#bp-live-activity")).to_have_count(0)


def test_on_a_phone_the_landing_hero_opens_in_the_details_sheet(mobile_page: object, site_url: str) -> None:
    """Phones hide the hierarchy rail, so the hero moves into the details sheet and a hidden heading names the page."""
    page = _open_site(mobile_page, site_url, "index.html")
    playwright.expect(page.locator(".bp-dag-navigation")).to_be_hidden()
    handle = page.locator(".bp-dag-sheet-handle")
    playwright.expect(handle).to_have_text("Explorer fixture")
    playwright.expect(page.locator(".bp-dag-inspector .bp-dag-intro")).to_have_count(1)
    headings = page.get_by_role("heading", level=1)
    playwright.expect(headings).to_have_count(1)
    handle.click()
    playwright.expect(page.locator(".bp-dag-inspector .bp-hero-title")).to_be_visible()
    # The open sheet's visible title is not a second heading.
    playwright.expect(headings).to_have_count(1)


def test_on_a_phone_the_status_filter_and_search_results_open_in_view(mobile_page: object, site_url: str) -> None:
    """The Status popover opened past the screen's left edge, and the toolbar's popovers painted under the sheet."""
    # The selection opens the sheet over the lower half of the screen.
    page = _open_site(mobile_page, site_url, "dependencies/chapters/algebra.html#node=algebra%2Fresult")

    def lengthen_the_index(route: object) -> None:
        index = route.fetch().json()
        index["nodes"] += [
            {"id": f"more/result-{n}", "kind": "node", "status": "planned", "title": f"Result {n}", "url": None}
            for n in range(20)
        ]
        route.fulfill(json=index)

    page.route("**/dependencies/index.json", lengthen_the_index)

    page.locator(".bp-dag-filter-summary").tap()
    popover = page.locator(".bp-dag-filter-popover")
    playwright.expect(popover).to_be_visible()
    box, viewport = popover.bounding_box(), page.viewport_size
    assert box is not None and viewport is not None
    assert 0 <= box["x"] and box["x"] + box["width"] <= viewport["width"]
    assert 0 <= box["y"] and box["y"] + box["height"] <= viewport["height"]
    assert popover.locator("input").first.evaluate(
        """input => {
          const box = input.getBoundingClientRect();
          return document.elementFromPoint(box.x + box.width / 2, box.y + box.height / 2) === input;
        }"""
    )

    search = _load_search_index(page, 27)
    search.fill("Result")
    # The lowest result the dropdown shows lies over the sheet, so it is the one to hit.
    lowest = page.evaluate(
        """() => {
          const sheet = document.querySelector(".bp-dag-inspector").getBoundingClientRect();
          const list = document.querySelector(".bp-dag-search-results").getBoundingClientRect();
          const centre = box => [box.x + box.width / 2, box.y + box.height / 2];
          const result = Array.from(document.querySelectorAll(".bp-dag-result"))
            .filter(result => centre(result.getBoundingClientRect())[1] < list.bottom)
            .pop();
          const [x, y] = centre(result.getBoundingClientRect());
          return [y > sheet.top, result.contains(document.elementFromPoint(x, y))];
        }"""
    )
    assert lowest == [True, True]


@pytest.mark.parametrize("width", (800, 1100, 1440))
def test_a_node_chosen_on_a_wider_screen_lands_beside_the_open_details(
    desktop_page: object, site_url: str, width: int
) -> None:
    """Centring in the whole stage put the chosen node, which also takes focus, under the drawer its selection opens."""
    page = desktop_page
    page.set_viewport_size({"width": width, "height": 900})
    # The drawer slides in; without motion it is measured where it stops.
    page.emulate_media(reduced_motion="reduce")
    _open_site(page, site_url, "dependencies/chapters/algebra.html#node=algebra%2Fresult")
    settled = "() => new Promise(done => setTimeout(() => requestAnimationFrame(() => requestAnimationFrame(done))))"

    def assert_beside_the_details(node: object) -> None:
        playwright.expect(node).to_have_attribute("data-selected", "true")
        page.evaluate(settled)
        box = node.bounding_box()
        drawer = page.locator(".bp-dag-inspector").bounding_box()
        stage = page.locator(".bp-dag-stage").bounding_box()
        assert box is not None and drawer is not None and stage is not None
        assert box["x"] + box["width"] <= drawer["x"] or drawer["x"] + drawer["width"] <= box["x"]
        assert stage["x"] <= box["x"] and box["x"] + box["width"] <= stage["x"] + stage["width"]

    result = page.locator('[data-autoform-node-id="algebra/result"]')
    assert_beside_the_details(result)
    # An arrow key from closed details centred the next node before its selection opened them.
    page.get_by_role("button", name="Close details").click()
    playwright.expect(result).to_be_focused()
    stacked = page.locator(".bp-dag-stage").evaluate("stage => stage.clientWidth <= 620")
    page.keyboard.press("ArrowUp" if stacked else "ArrowLeft")
    base = page.locator('[data-autoform-node-id="algebra/base"]')
    playwright.expect(base).to_be_focused()
    assert_beside_the_details(base)


def test_the_rail_under_the_open_details_leaves_the_tab_order(desktop_page: object, site_url: str) -> None:
    """Up to 1,200px open details cover the rail, and Tab still walked its links under the drawer."""
    page = desktop_page
    page.set_viewport_size({"width": 1000, "height": 900})
    page.emulate_media(reduced_motion="reduce")
    _open_site(page, site_url, "dependencies/chapters/algebra.html#node=algebra%2Fresult")
    result = page.locator('[data-autoform-node-id="algebra/result"]')
    playwright.expect(result).to_have_attribute("data-selected", "true")
    playwright.expect(page.locator(".bp-dag-navigation")).to_be_hidden()
    page.get_by_role("button", name="Fit shown nodes").focus()
    page.keyboard.press("Tab")
    playwright.expect(result).to_be_focused()
    # Closing the details uncovers the rail and brings it back.
    page.get_by_role("button", name="Close details").click()
    playwright.expect(page.locator(".bp-dag-navigation-link").first).to_be_visible()


def test_contents_start_right_of_the_open_details(desktop_page: object, site_url: str) -> None:
    """Up to 1,200px open details covered the start of every Contents row, its heading and the selected marker."""
    page = desktop_page
    page.set_viewport_size({"width": 1000, "height": 900})
    page.emulate_media(reduced_motion="reduce")
    # The list view never draws a map node, so the list itself is what to wait for.
    _offline(page, site_url)
    page.goto(f"{site_url}/dependencies/chapters/algebra.html#node=algebra%2Fresult&view=list")
    playwright.expect(page.locator(".bp-dag-inventory")).to_be_visible()
    playwright.expect(page.locator('.bp-dag-inventory-row[aria-current="true"]')).to_contain_text("Result")
    drawer = page.locator(".bp-dag-inspector").bounding_box()
    assert drawer is not None
    edge = drawer["x"] + drawer["width"]
    for item in (".bp-dag-inventory-head h2", ".bp-dag-inventory-row", ".bp-dag-inventory-title"):
        box = page.locator(item).first.bounding_box()
        assert box is not None and box["x"] >= edge, item
    # Closed details give the list the whole stage again.
    page.get_by_role("button", name="Close details").click()
    main = page.locator(".bp-dag-main").bounding_box()
    inventory = page.locator(".bp-dag-inventory").bounding_box()
    assert main is not None and inventory is not None and abs(inventory["x"] - main["x"]) < 1


def _paints_over_the_details(page: object, items: str, container: str) -> bool | None:
    """Whether the first of *items* shown in *container* over the open details is what a click there would hit.

    None means that no such item lies over the details.
    """
    return page.evaluate(
        """([items, container]) => {
          const drawer = document.querySelector(".bp-dag-inspector").getBoundingClientRect();
          const shown = document.querySelector(container).getBoundingClientRect();
          const inside = (box, [x, y]) => box.left < x && x < box.right && box.top < y && y < box.bottom;
          const centre = item => {
            const box = item.getBoundingClientRect();
            return [box.x + box.width / 2, box.y + box.height / 2];
          };
          const item = Array.from(document.querySelectorAll(items))
            .find(item => inside(drawer, centre(item)) && inside(shown, centre(item)));
          return item ? item.contains(document.elementFromPoint(...centre(item))) : null;
        }""",
        [items, container],
    )


def test_the_toolbars_popovers_paint_over_the_open_details(desktop_page: object, site_url: str) -> None:
    """The head stacked under the details drawer, which covered the Status popover and the search results."""
    page = desktop_page
    page.set_viewport_size({"width": 1000, "height": 900})
    page.emulate_media(reduced_motion="reduce")

    def every_status(route: object) -> None:
        payload = route.fetch().json()
        payload["nodes"] += [
            {"id": f"more/{key}", "kind": "node", "status": key, "status_counts": [[key, 1]], "title": f"More {key}"}
            for key in payload["palette"]
        ]
        route.fulfill(json=payload)

    def lengthen_the_index(route: object) -> None:
        index = route.fetch().json()
        index["nodes"] += [
            {"id": f"more/result-{n}", "kind": "node", "status": "planned", "title": f"Result {n}", "url": None}
            for n in range(20)
        ]
        route.fulfill(json=index)

    # A row per status makes the popover reach well down over the drawer.
    page.route("**/algebra.json", every_status)
    page.route("**/dependencies/index.json", lengthen_the_index)
    _open_site(page, site_url, "dependencies/chapters/algebra.html#node=algebra%2Fresult")
    playwright.expect(page.locator(".bp-dag-inspector h2")).to_have_text("Result")

    page.locator(".bp-dag-filter-summary").click()
    playwright.expect(page.locator(".bp-dag-filter-popover")).to_be_visible()
    assert _paints_over_the_details(page, ".bp-dag-check", ".bp-dag-filter-popover") is True
    page.locator(".bp-dag-filter-summary").click()

    search = _load_search_index(page, 27)
    for width in (1000, 800):
        page.set_viewport_size({"width": width, "height": 900})
        search.fill("")
        search.fill("Result")
        playwright.expect(page.locator(".bp-dag-search-results")).to_be_visible()
        assert _paints_over_the_details(page, ".bp-dag-result", ".bp-dag-search-results") is True


def test_a_short_phones_explorer_keeps_its_sheet_handle_on_screen(mobile_page: object, site_url: str) -> None:
    """A 28rem floor, 560px under Material's root font, pushed the sheet's handle below a short window."""
    page = mobile_page
    page.set_viewport_size({"width": 390, "height": 480})
    _open_site(page, site_url, "dependencies/chapters/algebra.html")
    viewer = page.locator(".bp-dag-viewer").bounding_box()
    handle = page.locator(".bp-dag-sheet-handle").bounding_box()
    assert viewer is not None and handle is not None
    assert viewer["height"] <= 480
    assert 0 <= handle["y"] and handle["y"] + handle["height"] <= 480


def test_a_phones_chapter_explorer_gives_its_breadcrumb_a_line_of_its_own(mobile_page: object, site_url: str) -> None:
    """The textbook link and kind pill shared the crumbs' line, cutting the chapter's name and Book's target short."""
    page = _open_site(mobile_page, site_url, "dependencies/chapters/algebra.html")
    current = page.locator('.bp-dag-breadcrumb [aria-current="page"]')
    playwright.expect(current).to_have_text("Algebra")
    assert current.evaluate("element => element.scrollWidth <= element.clientWidth")
    book = page.locator(".bp-dag-breadcrumb li").first.bounding_box()
    assert book is not None and book["width"] >= 24


def test_the_explorer_draws_its_breadcrumb_once(desktop_page: object, site_url: str) -> None:
    """On desktop the head and the hierarchy rail both drew the trail."""
    page = _open_site(desktop_page, site_url, "dependencies/chapters/algebra.html")
    playwright.expect(page.locator(".bp-dag-navigation-path li")).to_have_count(3)
    playwright.expect(page.locator(".bp-dag-navigation-path")).to_be_visible()
    playwright.expect(page.locator(".bp-dag-breadcrumb")).to_be_hidden()
    # The textbook link shares the head's row and stays.
    playwright.expect(page.locator(".bp-dag-book")).to_be_visible()
    # Up to 1,200px open details cover the rail, so the head draws the trail again.
    page.set_viewport_size({"width": 1000, "height": 800})
    _open_site(page, site_url, "dependencies/chapters/algebra.html#node=algebra%2Fresult")
    playwright.expect(page.locator(".bp-dag-inspector")).to_be_visible()
    playwright.expect(page.locator(".bp-dag-breadcrumb")).to_be_visible()
    # Phones hide the rail, so there the head draws the trail.
    page.set_viewport_size({"width": 390, "height": 844})
    playwright.expect(page.locator(".bp-dag-navigation")).to_be_hidden()
    playwright.expect(page.locator(".bp-dag-breadcrumb")).to_be_visible()
    # The landing page's rail holds the hero instead of a trail, so its head keeps the trail on desktop too.
    page.set_viewport_size({"width": 1280, "height": 900})
    _open_site(page, site_url, "index.html")
    playwright.expect(page.locator(".bp-dag-navigation .bp-dag-intro")).to_be_visible()
    playwright.expect(page.locator(".bp-dag-breadcrumb")).to_be_visible()


def test_the_published_atlas_hides_the_isolate_toggle(desktop_page: object, site_url: str) -> None:
    page = _open_site(desktop_page, site_url, "dependencies.html")
    playwright.expect(page.locator(".bp-dag-isolated")).to_be_hidden()


def test_published_explorer_controls_keep_their_own_styles_under_material(
    desktop_page: object, site_url: str
) -> None:
    """Material's typeset rules stacked the breadcrumb and drew the status filter as an admonition."""
    page = _open_site(desktop_page, site_url, "dependencies/chapters/algebra.html")

    summary = page.locator(".bp-dag-filter-summary")
    background = page.locator(".bp-dag-viewer").evaluate("element => getComputedStyle(element).backgroundColor")
    assert summary.evaluate("element => getComputedStyle(element).backgroundColor") == background
    assert summary.evaluate("element => getComputedStyle(element).borderLeftStyle") == "solid"
    page.locator(".bp-dag-search").fill("Result")
    results = page.locator(".bp-dag-results")
    results.wait_for()
    assert results.evaluate("element => getComputedStyle(element).listStyleType") == "none"
    assert results.locator("li").first.evaluate("element => getComputedStyle(element).marginLeft") == "0px"
    # The hierarchy rail's lists took Material's bullets, indents and block flow, and its title Material's light h1.
    for rail_list in (page.locator(".bp-dag-navigation-path"), page.locator(".bp-dag-navigation-list").first):
        assert rail_list.evaluate("element => getComputedStyle(element).listStyleType") == "none"
        assert rail_list.evaluate("element => getComputedStyle(element).display") == "grid"
        assert rail_list.locator("li").first.evaluate("element => getComputedStyle(element).marginLeft") == "0px"
    title = page.locator(".bp-dag-navigation-title")
    assert title.evaluate("element => getComputedStyle(element).fontWeight") == "650"
    # The head draws the breadcrumb only where phones hide the rail.
    page.set_viewport_size({"width": 390, "height": 844})
    crumbs = page.locator(".bp-dag-breadcrumb li")
    playwright.expect(crumbs).to_have_count(3)
    playwright.expect(crumbs.first).to_be_visible()
    assert len({round(crumbs.nth(index).bounding_box()["y"]) for index in range(3)}) == 1
    page.set_viewport_size({"width": 1280, "height": 900})

    # The atlas overview's heading, in the details drawer, took Material's large, light h2 and its margin.
    page.goto(f"{site_url}/dependencies.html")
    heading = page.locator(".bp-dag-inspector-inner > h2").evaluate(
        """heading => {
          const style = getComputedStyle(heading), root = getComputedStyle(document.documentElement);
          return [style.fontWeight, parseFloat(style.marginTop) < parseFloat(root.fontSize)];
        }"""
    )
    assert heading == ["700", True]


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
    page = _open_site(desktop_page, site_url, "dependencies/chapters/algebra.html")
    playwright.expect(page.locator(".bp-dag-book")).to_have_attribute("href", "../../roadmap/algebra/index.html")
    playwright.expect(page.locator(".bp-dag-book")).to_be_visible()
    # A section's explorer carries the same link to its own page, so it names no chapter.
    playwright.expect(page.locator(".bp-dag-book")).to_have_text("Open the textbook page")
    playwright.expect(page.get_by_role("heading", level=1)).to_have_text("Algebra dependencies")


def test_slash_on_the_published_landing_page_opens_the_explorer_search(desktop_page: object, site_url: str) -> None:
    """The landing page is the full-page explorer, so "/" opens its search, as on every explorer page."""
    page = _open_site(desktop_page, site_url, "index.html")
    page.keyboard.press("/")
    playwright.expect(page.locator(".bp-dag-search")).to_be_focused()


def test_slash_inside_the_explorer_opens_its_search_but_an_input_keeps_its_keys(
    desktop_page: object, explorer_url: str
) -> None:
    """Focus inside the explorer lets "/" open its search, but no shortcut takes a key from an input."""
    page = desktop_page
    _open_ready(page, explorer_url)
    page.locator("[data-autoform-node-id]").first.focus()
    page.keyboard.press("/")
    playwright.expect(page.locator(".bp-dag-search")).to_be_focused()
    isolates = page.get_by_role("checkbox", name="Show items without edges")
    isolates.focus()
    page.keyboard.press("Control+K")
    playwright.expect(isolates).to_be_focused()


def test_the_explorer_typesets_the_math_it_draws_in_its_rail_and_details(desktop_page: object, site_url: str) -> None:
    """MathJax typesets the page once when it starts, so authored TeX the explorer draws later stayed raw."""
    page = desktop_page
    # The site's mathjax.js assigns its configuration to window.MathJax, and offline the CDN script that
    # would replace it is aborted, so a stub behind an accessor stands in for MathJax once started.
    page.add_init_script(
        """
        window.typesetContainers = [];
        const stub = {
          startup: {promise: Promise.resolve()},
          typesetClear() {},
          typesetPromise(elements) {
            elements.forEach((element) =>
              window.typesetContainers.push({name: element.classList[0], text: element.textContent}));
            return Promise.resolve();
          },
        };
        Object.defineProperty(window, "MathJax", {configurable: true, get: () => stub, set() {}});
        """
    )
    _open_site(page, site_url, "dependencies/chapters/algebra.html")
    # The rail is empty until its first render, so text in the typeset container means it ran after the render.
    page.wait_for_function(
        "window.typesetContainers.some(({name, text}) => name === 'bp-dag-navigation-inner' && text.trim())"
    )
    page.evaluate("window.typesetContainers = []")
    page.locator('[data-autoform-node-id="algebra/result"]').click()
    playwright.expect(page.locator(".bp-dag-inspector-inner h2")).to_have_text("Result")
    # The whole drawer is typeset, so the phone sheet's handle, which repeats the title, is too.
    page.wait_for_function(
        "window.typesetContainers.some(({name, text}) => name === 'bp-dag-inspector' && text.includes('Result'))"
    )
    # Map cards and search results are not typeset.
    assert {entry["name"] for entry in page.evaluate("window.typesetContainers")} == {"bp-dag-inspector"}
