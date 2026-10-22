# Changelog

Notable changes to Autoform, newest first. A release's version is the one in
`pyproject.toml`; `uv.lock`, the Claude, Muse and Codex manifests, and this
file's newest release heading carry the same one (`tests/test_release.py`
checks), and `autoform --version` prints it. Add a line under **Unreleased**
with each change worth knowing about, and give the section its version and
date when the release is tagged.

## Unreleased

## 0.6.0 (2026-10-22)

What has landed since 0.5.0, across 236 merged pull requests, grouped by
theme. Each group names the pull requests to read for detail.

### Added

- **Formalization frontier.** A Markdown roadmap now schedules the work:
  `autoform work` lists ready leaves, gives one leaf's context, and measures
  the impact of a revision or an import (#92, #136, #183). Proofs may import
  other articles' modules when that impact is measured. `work impact` also
  reports unused statement dependencies (#150), works beside Lean files whose
  names are not identifiers (#182), and on a stale build names the root
  libraries to build instead of printing Lake's whole output (#427).
- **Skeletons.** `autoform skeleton` extracts what a reader must trust for each
  formalized statement, from elaborated terms, one Lean probe per root module,
  run in parallel (#12, #213, #214).
- **Search and reuse.** `autoform search` finds articles by title, Lean name or
  statement before an agent adds one (#171, #208, #375, #376, #392).
  `autoform library` lists the Lean libraries a project depends on and writes
  the index a library publishes, ATLAS among them; `autoform search --library`
  searches that index, and the skills reuse its results: Roadmap searches each
  intermediate result a proof uses, and records a reused library declaration
  in the implementation note, leaving `lean:` unset (#204, #278, #311, #343,
  #366, #373, #379, #400, #408). `autoform library index` runs its probe on
  Lean v4.34.1 and v4.35.0 (#440).
- **Dependency explorer.** One explorer replaces the site's generated Mermaid
  dependency maps, the full theorem DAG page among them. It runs on the landing
  page and on every project, chapter and scope page. It opens on chapter cards
  and drills through authored scopes, with search, status filters, a details
  drawer and addressable `#node=` focus. Old `/dependencies/full.html#node=`
  links still resolve. Authored `area:` values or `blueprint/atlas.json` group
  topic cards into regions, and overview containers can set a `navigation:`
  role. Authored Mermaid diagrams still render (#90). A design pass gave it one
  type scale and quieter chrome (#411).
- **Module catalogs.** A `catalog: module` leaf inventories an existing Lean
  module. It lists the module's public names in `lean:` and links a
  declaration ledger under `blueprint/sources/`. It is never dispatched, and it
  counts in its own inventory metric rather than in the roadmap's completion.
  `audit` reports catalog and coverage-role problems, and `audit --json` gains
  a `warnings` list that leaves `clean` and the exit status alone (#90).
- **Site check.** `autoform site check SITE_DIR [--source DOCS_DIR]` reads a
  built site and warns about dead internal links and assets, anchors that
  match no id and malformed links; the explorer's `#node=` routes are not
  anchors and are skipped. With `--source`, it also warns about statement
  cards the build dropped. It exits 0 whatever it finds (#401, #438).
- **Projects.** `autoform project new`, `inspect` and `versions` create and
  inspect Lean projects from a pinned release catalog (#14, #96, #211).
- **Article ids.** `autoform migrate article-ids --write` writes each planned
  id into its article's frontmatter (#191).
- **Dashboard.** `autoform dashboard` serves the built site on a loopback port,
  with a read-only overlay of current claims (#91).
- **Implementation notes.** Each article's implementation handoff is a hidden
  file, `blueprint/.implementation-notes/<article_id>.md`, so articles keep to
  frontmatter and informal mathematics. Every command that loads the graph
  rejects a malformed, empty, symlinked or orphaned note, and `audit` reports
  one left behind after its article is proved (#172, #296).
- **Unpublished folders.** A folder's `README.md` can say `published: false`:
  `check` and `audit` still validate the folder, and render leaves it out
  (#381).
- **CI audit.** The generated verify workflow checks `lean:` targets,
  non-root axioms, a kernel replay and elaboration limits, without running
  project code in its probe (#156, #190, #247, #264). It accepts a Batteries
  wanted target (`theorem_wanted` and its kin) whose article is not yet proved
  (#395).
- **Roadmap audit report.** The generated Pages workflow runs `autoform audit`
  after `check` and lists its findings in the step's log, without failing the
  build or stopping a deploy (#437).
- **Statement status.** Open statements and conditional proofs (#138). Under
  `open_statements: allowed`, the skills state a cited open prerequisite as a
  `theorem` with a `sorry` proof, not with `theorem_wanted` (#398).
- **Read-back rubric.** Agent Review judges an auditor's read-back of blind
  skeleton packets against the source passage (#53).
- **Feedback.** `autoform debrief`: forms agents fill in about their work. The
  draft's issue link holds the draft as it was recorded, and `record` says when
  a draft is too long for a link to carry more than its title (#195, #414,
  #425).
- **Version.** `autoform --version` prints the installed version and, from a
  plugin checkout, its commit (#397).
- **Muse Code.** The README covers installing the plugin in Muse Code beside
  Claude Code and Codex (#428).

### Changed

- **Commands inform; they do not break a codebase.** A new check warns and
  keeps the exit status instead of failing a repository that passed before
  (#325, #335, #361), a rule AGENTS.md now states (#394).
- **Claims are optional.** A single Formalize run keeps its own workers apart,
  and builds take no claim (#298, #324, #420). `claim acquire`, `renew` and
  `release` take several targets, all or nothing (#135). A stale lock file in
  the board is reported as one, not as a lost race (#291). `claim list` reads
  the board with one fetch, so a large or busy board lists quickly, and it no
  longer fails while peers renew (#427).
- **Publication.** Render publishes a site transactionally (#165), scales
  linearly (#289, #339), checks the site it replaces without reading it into
  memory (#365), and links files by the spelling Git committed (#301, #333).
  The generated Pages workflow deploys only the commit whose `autoform verify`
  run passed on `main`; pull requests and manual runs still build the site
  without deploying it (#399). The homepage metric counts progress within the
  scoped roadmap from proof semantics, and a finished scope shows as complete
  (#45, #196).
- **Checks.** The graph loader rejects formalized work the Lean cannot back
  (#158). `check` rejects Sources links that name no file (#287) or a hidden
  path (#321), and container articles that set a declaration (#328); since
  #361, hidden source notes and declaring containers pass with a warning.
  `check` and `audit` now read the blueprint render publishes: hidden paths are
  no part of it, and a dependency on a hidden page, a link that steps through a
  hidden folder, or a link to a generated view fails (#380, #409). Only the
  article graph must be acyclic: a cycle that appears only when articles
  collapse into chapters or scopes passes, and views keep every authored
  dependency (#358, #372). `work` and `search` resolve Sources links as
  `check` does, and `audit` resolves the blueprint as the graph loader does
  (#369). A Sources link with a scheme other than http(s), or a
  `mathlib_file` that is not a portable relative path, passes `check` with a
  warning, and the runtime projection leaves it out (#314, #325). `audit`
  reports an unclosed code fence (#202).
- **Vault dependency page.** `autoform-visualize` writes
  `blueprint/dependencies.md` as a Markdown summary of the explorer's project
  map instead of a Mermaid graph: statuses, one row per chapter with its
  counts, ready work and dependencies, and the articles while the roadmap has
  at most 120. It replaces only a missing page, its own, or the Mermaid page
  earlier versions wrote. Authored Mermaid diagrams draw locked down, and only
  pages that have one load Mermaid (#378).
- **Skills.** Every skill that runs the CLI says how to launch it (#319). A
  direct Roadmap run finishes one complete planning pass (#44). Before a
  revision lands, Roadmap re-checks retraction on the branch Formalize works
  from (#407).

### Removed

- `autoform unused-hypotheses`, in favor of Batteries' `unusedArguments`
  linter (#198, #352).
- `autoform-visualize --link-extension`, since the vault's dependency page is
  read in the vault (#378).
- The language server's diagnostics path (#306), the project routers and
  resident-era REPL pool (#316), and code nothing called (#114, #341, #344).

### Fixed and hardened

- **Lean runtime, REPL and LSP:** bounded transport, isolated public REPL
  calls, diagnostics barriers, and cleanup of leftover Lean processes (#13,
  #105, #106, #107, #111, #256, #283, #288, #322, #331, #338, #354, #360, #382).
- **Process control:** verified descendant cleanup and real exit statuses when
  SIGCHLD is ignored (#118, #168, #315, #334, #370).
- **Lean source capture and indexing:** filesystem-generation snapshots,
  aliases, multiline declarations, public declarations among duplicates,
  repositories of any size, raw strings that end at their first closer, and a
  foreign `publication.json` that no longer crashes capture (#95, #148, #231,
  #257, #308, #312, #340, #345, #348, #357, #363, #364, #371).
- **Render:** statement and proof bodies keep their compact inequalities,
  math, code fences, raw HTML and autolinks (#362). Render publishes without
  code links where Lean sources cannot be captured (native Windows), keeps code
  links when the blueprint lies outside the Lean repository or is uncommitted,
  and handles a link to the page's own folder (#163, #235, #300).
- **Links:** malformed, angle-bracket and query links, code-only labels, links
  that leave the blueprint, the structure page's links, and code links when
  the Lean root is a subdirectory of its repository (#318, #320, #326, #327,
  #355, #406). Malformed links are reported instead of crashing, an invalid
  URL gets its own `malformed-<label>-url` code, and a bad skeleton locator
  fails only its own article (#337, #347). A link from an ordinary page into a
  hidden path or an unpublished folder keeps only its text, with a warning
  (#416). A symlinked roadmap README no longer hangs `check` (#197).
- **Init and skeleton:** `init` refuses case variants of the paths it manages
  (#244), and skeleton reads `lakefile.lean` when both lakefiles exist, as
  Lake does (#189).
- **Security:** credentials stripped from remote URLs, URL queries redacted,
  nonlocal dashboard requests rejected, and every published page treated as
  untrusted: markup the site cannot trust is shown as typed, and a file a
  browser could run is left out, each with a warning (#98, #125, #215, #245).

### Contracts

Public CLI and JSON shapes are contracts. The JSON schema identifiers on main
include `autoform-skeleton/v5`, `autoform-work/v2`, `autoform-runtime/v4`,
`autoform-search/v2`, `autoform-publication/v3` and `autoform-impact/v1`; #90
moved the runtime and publication schemas, and render still replaces a v2
site.

### Dependencies

- `cryptography` bounded on both sides of the Intel Mac split (#56, #57);
  `pyjwt`, `urllib3`, `mcp` and `certifi` bumped (#50, #51, #353, #436). An
  optional `browser` extra (Playwright) runs the explorer's browser tests
  (#90).

## 0.5.0 (2026-08-28)

The release this changelog starts from: Autoform v2.0 (#5).
