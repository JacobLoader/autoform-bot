from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from autoform_cli import dag_viewer, graph_pages, status
from autoform_cli.graph_views import GraphView, ViewEdge, ViewNode


def test_full_view_payload_is_deterministic_layout_ready_and_data_only(tmp_path: Path) -> None:
    nodes = tuple(
        ViewNode(
            id=f"chapter/node-{index}",
            title="Unsafe <script>" if index == 0 else f"Node {index}",
            kind="node",
            members=(f"chapter/node-{index}",),
            status_counts=((("inventory_checked", 1),) if index == 0 else (("planned", 1),)),
            declaration=None if index == 0 else "theorem",
            catalog="module" if index == 0 else None,
            status_key="planned",
            summary="A reader-facing mathematical summary." if index == 0 else None,
            lean="Project.node" if index == 0 else None,
        )
        for index in range(dag_viewer.MAX_MAP_NODES)
    )
    view = GraphView(
        kind="full",
        title="Full graph",
        nodes=nodes,
        edges=tuple(ViewEdge(source.id, target.id, statement_count=1) for source, target in zip(nodes, nodes[1:])),
    )
    outputs = [tmp_path / "one.json", tmp_path / "two.json"]
    for output in outputs:
        dag_viewer.write_payload(output, view, links={node.id: f"../book.html#{node.id}" for node in nodes})

    assert outputs[0].read_bytes() == outputs[1].read_bytes()
    payload = json.loads(outputs[0].read_text(encoding="utf-8"))
    assert payload["schema"] == "autoform-dag-view/v2"
    # The explorer reads each field once; nothing is duplicated for other readers.
    assert set(payload) == {
        "edge_count",
        "edges",
        "nodes",
        "palette",
        "present_statuses",
        "regions",
        "schema",
        "title",
        "view",
    }
    assert set(payload["nodes"][0]["layout"]) == {"column", "height", "row", "width", "x", "y"}
    assert len(payload["nodes"]) == dag_viewer.MAX_MAP_NODES
    assert payload["edge_count"] == dag_viewer.MAX_MAP_NODES - 1
    assert payload["view"] == {
        "book": None,
        "breadcrumbs": [],
        "kind": "full",
        "presentation": "dag",
        "summary": None,
    }
    assert payload["present_statuses"] == ["planned", "inventory_checked"]
    assert payload["nodes"][0]["title"] == "Unsafe <script>"
    assert payload["nodes"][0]["status"] == "inventory_checked"
    assert payload["nodes"][0]["member_count"] == 1
    assert "members" not in payload["nodes"][0]
    assert payload["nodes"][0]["status_counts"] == [["inventory_checked", 1]]
    assert payload["nodes"][0]["summary"] == "A reader-facing mathematical summary."
    assert payload["nodes"][0]["lean"] == "Project.node"
    assert payload["nodes"][0]["isolated"] is False
    assert payload["palette"]["inventory_checked"]["label"] == "inventory checked"
    assert payload["palette"]["inventory_checked"]["neutral"] is True
    assert max(node["layout"]["column"] for node in payload["nodes"]) > 0
    positions = {(node["layout"]["x"], node["layout"]["y"]) for node in payload["nodes"]}
    assert len(positions) == len(nodes)
    assert all(
        payload["nodes"][index]["layout"]["x"] < payload["nodes"][index + 1]["layout"]["x"]
        for index in range(len(nodes) - 1)
    )

    script = dag_viewer.viewer_script()
    assert "innerHTML" not in script
    assert "textContent" in script
    assert "requestAnimationFrame" in script
    assert 'statusCounts.has("inventory_pending")' in script
    assert '"Inventory statuses are neutral:' in script


def test_a_view_too_large_for_the_map_gets_no_layout(tmp_path: Path) -> None:
    """The explorer only browses a view above its map limit, yet each node carried a layout it never drew."""
    nodes = tuple(
        ViewNode(f"n{index}", f"N{index}", "node", (f"n{index}",), (("planned", 1),))
        for index in range(dag_viewer.MAX_MAP_NODES + 1)
    )
    output = tmp_path / "large.json"
    dag_viewer.write_payload(output, GraphView(kind="chapter", title="Large", nodes=nodes, edges=()), links={})

    assert not any("layout" in node for node in json.loads(output.read_text(encoding="utf-8"))["nodes"])
    # The runtime draws a map up to the same limit.
    assert f"MAX_MAP_NODES = {dag_viewer.MAX_MAP_NODES}," in dag_viewer.viewer_script()
    # An atlas that large keeps its overview's count of topics in each region.
    topics = tuple(
        ViewNode(node.id, node.title, "scope", node.members, node.status_counts, area="Algebra") for node in nodes
    )
    dag_viewer.write_payload(output, GraphView(kind="project", title="Large", nodes=topics, edges=()), links={})
    regions = json.loads(output.read_text(encoding="utf-8"))["regions"]
    assert regions == [{"count": dag_viewer.MAX_MAP_NODES + 1, "label": "Algebra"}]


def test_each_inventory_has_a_neutral_colour_of_its_own(tmp_path: Path) -> None:
    """Checked and pending catalogs are drawn apart from each other and from every state.

    Both are neutral, but a ring holding planned targets and both kinds of
    inventory needs three greys, and borrowing a state's colour would read as
    target work.
    """
    statuses = ("planned", "inventory_pending", "inventory_checked")
    view = GraphView(
        kind="chapter",
        title="Library",
        nodes=tuple(
            ViewNode(
                id=f"library/{status}",
                title=status,
                kind="node",
                members=(f"library/{status}",),
                status_counts=((status, 1),),
                catalog=None if status == "planned" else "module",
                status_key="planned",
            )
            for status in statuses
        ),
        edges=(),
    )
    output = tmp_path / "library.json"
    dag_viewer.write_payload(output, view, links={})
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert [node["status"] for node in payload["nodes"]] == list(statuses)
    assert payload["present_statuses"] == ["planned", "inventory_checked", "inventory_pending"]
    pending = payload["palette"]["inventory_pending"]
    assert pending["label"] == "inventory pending"
    assert pending["neutral"] is True
    for inventory in ("inventory_checked", "inventory_pending"):
        for scheme in ("light", "dark"):
            assert all(
                entry[scheme]["stroke"] != payload["palette"][inventory][scheme]["stroke"]
                for key, entry in payload["palette"].items()
                if key != inventory
            )


def test_status_counts_keep_the_legend_order(tmp_path: Path) -> None:
    """Sorted object keys split a ring's finished arcs with grey ones and listed rows out of legend order."""
    counts = (
        ("mathlib", 10),
        ("fully_proved", 50),
        ("proved", 5),
        ("can_prove", 4),
        ("planned", 35),
        ("inventory_checked", 3),
    )
    view = GraphView(kind="project", title="Project", nodes=(ViewNode("scope:a", "A", "scope", (), counts),), edges=())
    output = tmp_path / "project.json"
    dag_viewer.write_payload(output, view, links={})

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["nodes"][0]["status_counts"] == [list(entry) for entry in counts]


def test_a_catalog_carries_a_few_lean_names_and_counts_the_rest(tmp_path: Path) -> None:
    """A catalog lists its keyword-declared public names, which made its payload and inspector line unbounded."""
    names = [f"Mathlib.Algebra.Module.lemma_{index:03d}" for index in range(150)]
    nodes = (
        ViewNode(
            "catalog",
            "Catalog",
            "node",
            ("catalog",),
            (("inventory_checked", 1),),
            catalog="module",
            lean=", ".join(names),
        ),
        ViewNode(
            "leaf", "Leaf", "node", ("leaf",), (("planned", 1),), declaration="theorem", lean=" ".join(names[:20])
        ),
    )
    output = tmp_path / "inventory.json"
    dag_viewer.write_payload(output, GraphView(kind="chapter", title="Inventory", nodes=nodes, edges=()), links={})

    catalog, leaf = json.loads(output.read_text(encoding="utf-8"))["nodes"]
    assert catalog["lean"] == ", ".join(names[:8])
    assert catalog["lean_more"] == 142
    assert len(catalog["lean"].encode()) < 400
    # A declaration leaf names only its own declarations, so it keeps them all.
    assert leaf["lean"] == " ".join(names[:20])
    assert "lean_more" not in leaf


def test_isolated_inventory_does_not_spread_the_connected_dag(tmp_path: Path) -> None:
    node_ids = ["root", "result", *(f"isolated-{index}" for index in range(100))]
    nodes = tuple(
        ViewNode(
            id=node_id,
            title=node_id,
            kind="node",
            members=(node_id,),
            status_counts=(("planned", 1),),
            declaration="theorem",
            status_key="planned",
        )
        for node_id in node_ids
    )
    view = GraphView(
        kind="full",
        title="Mixed graph",
        nodes=nodes,
        edges=(ViewEdge("root", "result", statement_count=1),),
    )

    output = tmp_path / "mixed.json"
    dag_viewer.write_payload(output, view, links={})
    payload = json.loads(output.read_text(encoding="utf-8"))
    columns = {node["id"]: node["layout"]["column"] for node in payload["nodes"]}

    assert columns["root"] == 0
    assert columns["result"] == 1
    assert columns["isolated-0"] >= 3


def test_high_level_topics_use_a_readable_grouped_knowledge_atlas(tmp_path: Path) -> None:
    nodes = tuple(
        ViewNode(
            id=f"chapter-{index}",
            title=f"Chapter {index}",
            kind="scope",
            members=tuple(f"chapter-{index}/item-{item}" for item in range(index + 1)),
            status_counts=(("planned", index + 1),),
            status_key="planned",
            area="Foundations" if index < 10 else "Applications",
        )
        for index in range(33)
    )
    view = GraphView(kind="project", title="Project", nodes=nodes, edges=())
    output = tmp_path / "atlas.json"
    dag_viewer.write_payload(output, view, links={})
    payload = json.loads(output.read_text(encoding="utf-8"))
    layouts = [node["layout"] for node in payload["nodes"]]

    assert payload["view"]["presentation"] == "atlas"
    assert {(region["label"], region["count"]) for region in payload["regions"]} == {
        ("Applications", 23),
        ("Foundations", 10),
    }
    assert len({(layout["x"], layout["y"]) for layout in layouts}) == len(nodes)
    # The same fields a DAG's layout has, which are all the explorer reads.
    assert all(set(layout) == {"column", "height", "row", "width", "x", "y"} for layout in layouts)
    assert all(layout["width"] > layout["height"] for layout in layouts)
    assert min(layout["width"] for layout in layouts) >= 220
    assert min(layout["height"] for layout in layouts) >= 88


def test_atlas_regions_that_differ_only_in_case_keep_one_order(tmp_path: Path) -> None:
    """Identical inputs publish identical bytes, whatever the hash seed of the render."""
    areas = ("algebra", "Algebra", "ALGEBRA", "aLGEBRA", "AlgebrA", "alGEBRA")
    view = GraphView(
        kind="project",
        title="Project",
        nodes=tuple(ViewNode(f"scope:{area}", area, "scope", (), (("planned", 1),), area=area) for area in areas),
        edges=(),
    )
    output = tmp_path / "atlas.json"
    dag_viewer.write_payload(output, view, links={})

    regions = json.loads(output.read_text(encoding="utf-8"))["regions"]
    assert [region["label"] for region in regions] == sorted(areas)


def test_a_view_of_topics_and_leaves_is_a_dag_not_an_atlas(tmp_path: Path) -> None:
    """Catalogs carry no edges, so a chapter holding them beside its sections is edgeless but not all topics."""
    nodes = (
        ViewNode("scope:section", "Section", "scope", ("section/a",), (("planned", 1),), area="Topology"),
        ViewNode("heine-borel", "Heine-Borel theorem", "node", ("heine-borel",), (("planned", 1),)),
        ViewNode("catalog", "Existing module", "node", ("catalog",), (("inventory_checked", 1),), catalog="module"),
    )
    output = tmp_path / "chapter.json"
    dag_viewer.write_payload(output, GraphView(kind="chapter", title="Chapter", nodes=nodes, edges=()), links={})
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert payload["view"]["presentation"] == "dag"
    assert payload["regions"] == []
    assert {node["layout"]["width"] for node in payload["nodes"]} == {196}


def test_an_explorer_page_is_named_for_how_the_explorer_draws_it() -> None:
    """The heading followed the edges, so an edgeless chapter of results was a "knowledge map" drawn as cards."""
    results = GraphView("chapter", "Results dependency map", (ViewNode("a", "A", "node", ("a",), (("planned", 1),)),), ())
    topics = tuple(ViewNode(f"scope:{name}", name, "scope", (), (("planned", 1),), area="Algebra") for name in "xy")
    atlas = GraphView("chapter", "Topics dependency map", topics, (ViewEdge("scope:x", "scope:y", statement_count=1),))

    assert graph_pages._dependency_heading(results) == "Results dependencies"
    assert graph_pages._dependency_heading(atlas) == "Topics knowledge map"
    assert graph_pages._dependency_heading(results, "Top level") == "Top level dependencies"


def test_explorer_marks_isolates_but_keeps_them_in_the_complete_inventory(tmp_path: Path) -> None:
    nodes = tuple(
        ViewNode(
            id=node_id,
            title=node_id.upper(),
            kind="node",
            members=(node_id,),
            status_counts=(("planned", 1),),
            status_key="planned",
        )
        for node_id in ("a", "b", "isolated")
    )
    view = GraphView(
        kind="full",
        title="Full graph",
        nodes=nodes,
        edges=(ViewEdge("a", "b", statement_count=1),),
    )

    output = tmp_path / "graph.json"
    dag_viewer.write_payload(output, view, links={})
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert {node["id"] for node in payload["nodes"] if node["isolated"]} == {"isolated"}
    script = dag_viewer.viewer_script()
    assert "inventoryNodes" in script
    assert '" · items without edges included"' in script


def test_explorer_host_is_escaped_responsive_and_accessible() -> None:
    container = dag_viewer.render_container(
        'unsafe" data-x="oops',
        script_href='scripts/viewer" onload="oops.js',
        fallback_links=(
            ("Unsafe <node>", 'roadmap/a" onclick="oops'),
            ("Unsafe protocol", "javascript:alert(1)"),
        ),
        fallback_total=5,
    )
    script = dag_viewer.viewer_script()

    assert 'data-graph-src="unsafe%22%20data-x%3D%22oops"' in container
    assert 'src="scripts/viewer%22%20onload%3D%22oops.js"' in container
    assert "Dependency explorer fallback." in container
    assert "Unsafe &lt;node&gt;" in container
    assert 'href="roadmap/a&quot; onclick=&quot;oops"' in container
    assert "javascript:alert" not in container
    assert "Showing 1 of 5 linked nodes" in container
    assert "<style data-autoform-dag-style>" in container
    assert "@media (max-width: 680px)" in container
    assert "@media (prefers-reduced-motion: reduce)" in container
    assert "100svh" in container
    assert "100dvh" in container
    assert 'refs.canvas.setAttribute("aria-hidden", "true")' in script
    assert 'refs.stage.setAttribute("role", "region")' in script
    assert 'toolbar.setAttribute("role", "group")' in script
    assert 'refs.navigation = element("aside", "bp-dag-navigation")' in script
    assert 'refs.navigation.setAttribute("aria-label", "Wiki hierarchy")' in script
    assert 'renderNavigation()' in script
    # MathJax typesets the rail and the details, which carry authored TeX, and no other container.
    assert "if (!M || !M.typesetPromise) return;" in script
    assert "typeset(refs.navigationInner); refs.navigationInner.textContent" in script
    assert "typeset(refs.inspector); refs.inspectorInner.textContent" in script
    assert script.count("typeset(refs.") == 2
    # Relation rows that Show more appends to the details are typeset in their list.
    assert 'more.addEventListener("click", function () { appendNextBatch(); typeset(list); });' in script
    assert 'refs.announcement.setAttribute("aria-live", "polite")' in script
    assert "control.dataset.autoformNodeId = node.id" in script
    assert "new ResizeObserver(resize)" in script
    assert "state.pointers.size === 2" in script
    assert "event.type === \"pointerup\" && wasSingle && !state.moved" in script
    assert "touch-action: none; cursor: grab;" in container
    assert 'url.origin === window.location.origin' in script
    assert 'w: node.width, h: node.height' in script
    assert 'spotlight.before.has(edge.source) && spotlight.before.has(edge.target)' in script
    assert 'spotlight.after.has(edge.source) && spotlight.after.has(edge.target)' in script
    assert "if (atlas && !state.selected) edgeIndexes.clear()" in script
    assert "(incident.get(state.selected.id) || []).forEach" in script
    assert "if (!state.activeDirty) return" in script
    assert "if (query === state.searchCacheQuery) return state.searchCache" in script
    assert 'data.schema !== "autoform-dag-view/v2"' in script
    assert 'ctx.fillText("×" + count' in script
    assert "Title prefix" in script and "Id prefix" in script and "Word prefix" in script
    assert "Exact Lean name" in script and "Statement match" in script and "All terms match" in script


def test_explorer_pages_relations_and_clamps_zoom() -> None:
    script = dag_viewer.viewer_script()

    assert "Math.min(visible + RELATION_PAGE, ids.length)" in script
    assert "ids.slice(visible, next)" in script
    assert "clamp(old * factor, MIN_SCALE, 4)" in script


def test_explorer_styles_keep_one_family_one_type_scale_and_one_micro_label() -> None:
    """The rail and drawer headings were set in Georgia, among twenty rem sizes and unloaded weights."""
    style = dag_viewer._STYLE
    assert "serif" not in style.replace("sans-serif", "")
    assert set(re.findall(r"font-size: ([^;]+);", style)) <= {"11px", "12px", "13px", "14px", "17px", "22px"}
    assert set(re.findall(r"font-weight: ([^;]+);", style)) <= {"400", "500", "600", "700"}
    uppercase = [rule.split("{")[0].strip() for rule in style.splitlines() if "text-transform: uppercase" in rule]
    assert uppercase == [
        ".bp-dag-filter-popover legend, .bp-dag-viewer.bp-dag-viewer .bp-dag-navigation-group h2",
    ]


def test_explorer_names_its_scope_once_and_lists_only_its_ancestors_above_it() -> None:
    """A kind pill, a rail kicker, the h1, the trail's last crumb and a home link all named the scope or the book."""
    script, style = dag_viewer.viewer_script(), dag_viewer._STYLE
    for retired in ("bp-dag-view-kind", "bp-dag-navigation-kicker", "bp-dag-navigation-home"):
        assert retired not in script and retired not in style
    assert "Current scope" not in script and "Library atlas" not in script
    # The rail's one-line trail drops the current crumb, which the h1 right under it names.
    rail = 'trailList(trail.slice(0, -1), "bp-dag-navigation-path")'
    assert rail in script
    assert script.index(rail) < script.index('element("h1", "bp-dag-navigation-title"')
    assert ":is(.bp-dag-breadcrumb, .bp-dag-navigation-path) li + li::before { content: \"/\";" in style


def test_explorer_chrome_is_sized_in_px_not_in_materials_growing_rem() -> None:
    """Material's root font is 20px, 22px from 1600px, so a rem rail was 407px wide at 1600 by 900."""
    style = dag_viewer._STYLE
    assert not re.findall(r"\d+(?:\.\d+)?rem\b", style)
    assert "--dag-navigation-width: 288px;" in style
    # Beside the 288px rail the 12px-inset 384px drawer leaves 405px from 1101px; below, it covers the rail.
    assert "width: min(384px, calc(100% - 24px));" in style
    assert "@media (max-width: 1100px) {\n  .bp-dag-viewer { --dag-navigation-width: 248px; }" in style
    assert "left: calc(408px - var(--dag-navigation-width));" in style


def test_explorer_head_is_one_row_where_the_rail_always_shows() -> None:
    """Over the rail the hidden breadcrumb left a head row holding only the textbook link."""
    style = dag_viewer._STYLE
    one_row = style.split("@media (min-width: 1101px) {\n", 1)[1].split("\n}", 1)[0]
    assert ".bp-dag-context { display: contents; }" in one_row
    assert ".bp-dag-viewer:has(.bp-dag-navigation-path) .bp-dag-breadcrumb { display: none; }" in one_row
    assert ".bp-dag-book { order: 1; }" in one_row
    # Up to 1,100px open details cover the rail, so the head keeps a row where the trail then appears.
    assert (
        "@media (min-width: 681px) and (max-width: 1100px) { "
        ".bp-dag-viewer:has(.bp-dag-navigation-path) .bp-dag-breadcrumb { visibility: hidden; } }"
    ) in style
    assert ".bp-dag-viewer.bp-dag-has-selection.bp-dag-sheet-open .bp-dag-breadcrumb { visibility: visible; }" in style


def test_explorer_elevation_is_two_shadows_and_a_selection_ring_that_keeps_the_card_still() -> None:
    """A selected card took a 3px border, shifting its text, and blurred panels sat on five shadows."""
    style = dag_viewer._STYLE
    assert "backdrop-filter" not in style
    assert set(re.findall(r"box-shadow: ([^;]+);", style)) <= {
        "var(--dag-e1)",
        "var(--dag-e2)",
        "none",
        "0 0 0 2px var(--dag-link), var(--dag-e1)",
        "0 0 0 2px color-mix(in srgb, var(--dag-link) 40%, transparent), var(--dag-e1)",
        "0 0 0 3px color-mix(in srgb, var(--dag-link) 18%, transparent)",
        "inset 3px 0 0 var(--dag-link)",
    }
    assert ".bp-dag-node[data-selected=true] { box-shadow: 0 0 0 2px var(--dag-link), var(--dag-e1); }" in style
    assert "border-width" not in style


def _contrast(first: str, second: str) -> float:
    def luminance(colour: str) -> float:
        channels = [int(colour.lstrip("#")[index : index + 2], 16) / 255 for index in (0, 2, 4)]
        linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

    high, low = sorted((luminance(first), luminance(second)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def test_dark_explorer_cards_read_against_the_page_toned_map() -> None:
    """Outlined cards were filled with the dark map's own #18191A, and planned's stroke had 2.1:1 against it."""
    style = dag_viewer._STYLE
    page, surface = "#18191A", "#242526"
    assert "--dag-map: #18191a;" in style and ".bp-dag-main {" in style and "background: var(--dag-map); }" in style
    assert all(state.dark_fill.upper() != page for state in (*status.STATES, *status.INVENTORY_STATES))
    planned = next(state for state in status.STATES if state.key == "planned")
    assert min(_contrast(planned.dark_stroke, page), _contrast(planned.dark_stroke, surface)) >= 3
    # White on the dark link blue, #2D88FF, is 3.5:1; the Open button takes Meta blue there.
    assert "[data-md-color-scheme=slate] .bp-dag-open { background: #0064e0; }" in style
    assert _contrast("#FFFFFF", "#0064E0") >= 4.5
    assert _contrast("#FF7B72", surface) >= 4.5 and "--dag-error: #ff7b72;" in style


def test_explorer_assets_and_ordinary_payload_stay_within_budgets(tmp_path: Path) -> None:
    nodes = tuple(
        ViewNode(
            id=f"chapter/node-{index}",
            title=f"Node {index}",
            kind="node",
            members=(f"chapter/node-{index}",),
            status_counts=(("planned", 1),),
            status_key="planned",
            lean="Project.NodeZero" if index == 0 else None,
            summary="A spectral gap statement." if index == 0 else None,
        )
        for index in range(500)
    )
    view = GraphView(
        kind="full",
        title="Budget fixture",
        nodes=nodes,
        edges=tuple(ViewEdge(nodes[index].id, nodes[index + 1].id, statement_count=1) for index in range(499)),
    )
    output = tmp_path / "budget.json"
    dag_viewer.write_payload(output, view, links={})
    search = tmp_path / "search.json"
    dag_viewer.write_search_index(
        search,
        view,
        context_links={node.id: f"chapters/chapter.html#node={node.id}" for node in nodes},
    )

    # The hierarchy rail is part of the shared runtime, but the dependency-free
    # application still stays below one small uncompressed network response.
    assert len(dag_viewer.viewer_script().encode()) < 66_000
    assert output.stat().st_size < 300_000
    assert search.stat().st_size < 100_000
    search_payload = json.loads(search.read_text(encoding="utf-8"))
    assert search_payload["schema"] == "autoform-dag-search/v1"
    assert "layout" not in search_payload["nodes"][0]
    assert search_payload["nodes"][0]["lean"] == "Project.NodeZero"
    assert search_payload["nodes"][0]["summary"] == "A spectral gap statement."
    assert "lean" not in search_payload["nodes"][1]
    assert "summary" not in search_payload["nodes"][1]


def test_viewer_script_links_are_relative_to_the_rendered_site_root(tmp_path: Path) -> None:
    assert graph_pages._viewer_script_link(tmp_path / "dependencies.md", tmp_path) == "javascripts/blueprint-dag.js"
    assert graph_pages._viewer_script_link(tmp_path / "dependencies/full.md", tmp_path) == "../javascripts/blueprint-dag.js"
    assert (
        graph_pages._viewer_script_link(tmp_path / "dependencies/chapters/large.md", tmp_path)
        == "../../javascripts/blueprint-dag.js"
    )


def test_payload_layout_follows_dependencies_and_keeps_collapsed_cycles_stable(tmp_path: Path) -> None:
    nodes = (
        ViewNode("result", "Result", "node", ("result",), (("planned", 1),)),
        ViewNode("base", "Base", "node", ("base",), (("planned", 1),)),
    )
    acyclic = GraphView(
        kind="full",
        title="Acyclic",
        nodes=nodes,
        edges=(ViewEdge("base", "result", statement_count=1),),
    )
    cyclic = GraphView(
        kind="project",
        title="Collapsed cycle",
        nodes=nodes,
        edges=(
            ViewEdge("base", "result", statement_count=1),
            ViewEdge("result", "base", proof_count=1),
        ),
    )

    def layout(view: GraphView) -> dict[str, tuple[int, int]]:
        output = tmp_path / f"{view.kind}.json"
        dag_viewer.write_payload(output, view, links={})
        payload = json.loads(output.read_text(encoding="utf-8"))
        return {node["id"]: (node["layout"]["x"], node["layout"]["y"]) for node in payload["nodes"]}

    assert layout(acyclic) == {"base": (0, 0), "result": (312, 0)}
    # A collapsed cycle has no topological order, so it keeps source order.
    assert layout(cyclic) == {"result": (0, 0), "base": (312, 0)}


def test_payload_rejects_duplicate_nodes_and_unknown_edges(tmp_path: Path) -> None:
    node = ViewNode("a", "A", "node", ("a",), (("planned", 1),))
    duplicate = GraphView(kind="full", title="Duplicate", nodes=(node, node), edges=())
    unknown = GraphView(
        kind="full",
        title="Unknown",
        nodes=(node,),
        edges=(ViewEdge("missing", "a", statement_count=1),),
    )

    with pytest.raises(ValueError, match="duplicate node ids"):
        dag_viewer.write_payload(tmp_path / "duplicate.json", duplicate, links={})
    with pytest.raises(ValueError, match="unknown node"):
        dag_viewer.write_payload(tmp_path / "unknown.json", unknown, links={})


def test_an_explorer_page_encodes_a_literal_percent_in_its_payload_name(tmp_path: Path) -> None:
    """render_container keeps % for hrefs that arrive encoded, so the page encodes the payload's name."""
    page = tmp_path / "100%25 results.md"
    node = ViewNode("a", "A", "node", ("a",), (("planned", 1),))

    graph_pages._write_page(
        page,
        view=GraphView(kind="chapter", title="Results", nodes=(node,), edges=()),
        statuses={},
        links={},
        heading="Results",
        lead="One result.",
        site_root=tmp_path,
        search_href="index.json",
        breadcrumbs=(),
    )

    assert (tmp_path / "100%25 results.json").is_file()
    assert 'data-graph-src="100%2525%20results.json"' in page.read_text(encoding="utf-8")


def test_interactive_graph_urls_encode_authored_path_delimiters() -> None:
    container = dag_viewer.render_container(
        "hash#chapter.json",
        script_href="../javascripts/blueprint-dag.js?cache#asset",
    )

    assert 'data-graph-src="hash%23chapter.json"' in container
    assert 'src="../javascripts/blueprint-dag.js%3Fcache%23asset"' in container
