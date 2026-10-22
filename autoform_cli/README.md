# Blueprint format and CLI

The Autoform CLI validates, visualizes, and publishes the multilevel dependency
graph embedded in `blueprint/roadmap/`. The Markdown book is the graph: no
separate authored or generated graph file exists.

This is an agent-facing interface. Normal project work starts from Autoform's
skills in the user's preferred agent window; those agents invoke these commands
as needed.

## Articles and containment

Every Markdown file below `blueprint/roadmap/` is an article node. A
`README.md` represents its directory and strictly contains the articles below
it; the nearest ancestor `README.md` is the single parent. This supports any
number of levels, from book to chapter to section to declaration. Ordinary
files use their path without `.md` as a stable ID; `README.md` uses its
directory path, with the root article named `roadmap`.

The H1 is the article's human title. Container prose supplies the exposition,
and a standalone list item linking to a formalizable leaf places it at that
position in the published chapter. Leaves without a placement slot appear under
an explicit “Additional formalization targets” section; a module catalog
without one appears under “Module inventories” instead. Keep the root article a
short preface and table of contents, not an inventory of every milestone.

Frontmatter records checked facts:

```markdown
---
article_id: af_5b0e4d3c2a1f09e8d7c6b5a4
declaration: theorem
origin: cited
statement: formalized
proof: formalized
lean: MyProject.separatingHyperplane
---

# Separating hyperplane theorem

State the intended result and proof sketch here.

## Depends on

- [Convex set](convex.md)

## Proof depends on

- [Supporting hyperplane](supporting-hyperplane.md)

## Sources

- [Chapter 2](../../sources/convexity.md#separation)
```

An article's statement is its body from the end of the frontmatter to the first
`##` heading, without the H1 line; `autoform audit` and the published theorem
box both read that span. The article's first H1 (its title), if written below a
`##` section, ends that section and resumes the statement; a later H1 stays in
its section. No heading deeper than `##` ends the statement, and neither does a
`##` line inside a fenced code block or an HTML comment. Close each fence with
its own bare line of the same character, length and indent: on a chapter page
an unclosed fence can pair with a later article's fence and hide everything
between them, so `check` warns about it, the site shows that page as typed (see
[Validation](reference/validation-and-audit.md#validation)), and the audit
reports `unclosed-code-fence`. An HTML comment that never closes, even one
opened in inline code or an indented code block, hides every heading and
dependency link after it: the graph loses those edges, one opened in the
statement puts the rest of the article in the theorem box, and nothing reports
it.

`## Depends on` lists what the article needs in order to be *stated*;
`## Proof depends on` lists what only its *proof* needs. Both are graph edges,
except a link in a code block, fenced or indented, or in an HTML comment. Links
anywhere else are ordinary navigation or citations. Dependencies resolve
relative to the current article and must point at another roadmap article.

The optional `declaration` field marks a formalizable leaf and names its
intended Lean declaration command, such as `def`, `theorem`, `structure`, or
`instance`; Autoform does not constrain the set. Container and exposition
articles omit it. Declarations that introduce data rather than a proposition
carry no separate proof obligation, whatever leading modifiers such as
`noncomputable` they have; an `axiom` does not get this shortcut.

`origin` records provenance for formalizable work: `cited` for a direct source
target, `bridged` for a result introduced between source targets, and
`background` for prerequisite mathematics.

Frontmatter is optional. A container article that only supplies prose and
placement needs none at all; only checked facts are recorded.

The optional `area` field places a container in an authored mathematical
region of its parent's explorer map; on a leaf it only labels the article. Use
mathematical areas such as `Foundations` or `Geometry & Topology`, never
repository or workflow buckets such as `MathlibExt` or `catalog-01`. Autoform
does not guess areas from paths, imports, or titles.

An optional container-only `navigation` role separates mathematical topics
from repository organization:

- `topic` (the default): a mathematical subject or coherent group of results.
- `collection`: a library or other organizational collection; its parent's
  overview shows its children in its place.
- `transparent`: a generated pagination or range container, flattened the
  same way. Both are left out of the outline and ancestor breadcrumbs.
- `source`: a book or other source corpus, shown as itself.
- `module`: mirrors one Lean source module and holds its declarations; shown
  like a topic, sized as the module (see
  [Structure](reference/validation-and-audit.md#structure)).

Roles never change identity, containment, readiness, or edges. An overview
does not draw an edge to a collection it replaces by its contents, so depend on
an article inside the collection instead.

For a taxonomy maintained separately from article files, `blueprint/atlas.json`
may assign the same areas without moving pages:

```json
{"schema":"autoform-atlas/v1","areas":{"Geometry & Topology":["topology","geometry"]}}
```

Every listed value is a roadmap node id. A node takes the first area that
lists it; an `area:` on the node wins. The file never stops a command: `check`
and `render` warn about each ignored entry, or the whole file when it is not
readable `autoform-atlas/v1` JSON, and `audit` reports each as an
`atlas-omission` [warning](reference/validation-and-audit.md#warnings). Render
leaves the file out of the site; a page's link to it keeps only its text.

A narrative leaf may summarize an existing Lean module by setting
`catalog: module` and omitting `declaration`; it is never dispatched as a proof
task. A catalog must be a leaf (`audit` reports `catalog-container`) and links
a declaration ledger under `blueprint/sources/` from `## Sources`: `check`
warns about a catalog that links none and `audit` reports
`catalog-missing-ledger`; a link to a missing ledger fails both, and a hidden
ledger under `sources/` draws a `check` warning and fails only `audit` (see
[Validation](reference/validation-and-audit.md#validation)).

A completed catalog records in `lean:` the full name of every public
declaration the module writes with a declaration keyword, as the Lean source
index records them. Names Lean generates, such as constructors,
structure fields, derived or unnamed instances, and `@[ext]`, `@[simps]`, or
`@[to_additive]` results, and declarations the index cannot see yet, behind
`nonrec` or `meta` or written `class inductive`, go in the ledger as
supporting entries, never in `lean:`; a `private` name never goes in `lean:`.
A completed catalog may assert `statement: formalized` and `proof: formalized`
when the complete module has been checked. Like any prerequisite, a catalog
linked under `## Depends on` or `## Proof depends on` holds its dependents back
until its whole-module assertion is recorded, so a dependent that needs one
result links the declaration article that expounds it.

`check --lean-root` and `audit --lean-root` resolve every name the catalog
lists, and say for a catalog name they do not find that a generated name
belongs in the ledger. They cannot prove that the list omitted no newly added
public declaration; completeness remains an authored assertion.
`audit --lean-root` reports the
[elaboration limits](reference/validation-and-audit.md#elaboration-limits) of a
catalog's declarations as warnings, and a catalog that records
`proof: formalized` gets `lean-target-wanted` for a wanted target it names; the
deprecation, declaration-kind, and node-size checks apply only to declaration
articles.

Versioned implementation notes live at
`blueprint/.implementation-notes/<article_id>.md`, one per article, and survive
article moves. Claims keep workers from editing the same leaf's note;
containers have no claims. Every command that loads the graph rejects
malformed, empty, symlinked, or orphaned notes, so assign the article ID before
creating its note. Any worker may delete a stale note or repair an orphan: move
anything still useful into the surviving article's note and delete the orphan,
or restore a lost `article_id` line if the article still exists. Delete a note
once its article is proved; for a container, once every formalizable
descendant and every `not_ready` leaf beneath it is proved and there is at
least one (a module catalog never counts). `autoform audit` reports a note left
after that point. Render omits the hidden directory from the site and the
publication hash.

## Assertions and derived status

An article asserts only facts a human or agent verified:

| Key | Meaning |
| --- | --- |
| `area: Geometry & Topology` | Authored mathematical region for atlas grouping. |
| `navigation: collection` | Presentation-only container role: `topic`, `collection`, `transparent`, `source`, or `module` (see above). |
| `catalog: module` | A non-dispatchable leaf cataloging one existing Lean module. Its `lean:` lists the module's public keyword-declared names, and it links its declaration ledger under `blueprint/sources/` from `## Sources`; cannot be combined with `declaration` or the `mathlib*` keys. |
| `statement: formalized` | The Lean statement exists and compiles. Requires `lean:`. |
| `statement: retracted` | A revision retracted the statement while `lean:` still names the old declaration, which stays in the build until Formalize restates the article and records `statement: formalized` in its place. Requires `lean:`; invalid with `proof: formalized` or `mathlib: true`. |
| `proof: formalized` | The Lean proof compiles. Requires `statement: formalized` and `lean:`. Under the open policy it may rest on open statements, and the article is then conditional; only the derived `fully_proved` means complete and `sorry`-free. |
| `mathlib: true` | The result is upstreamed into Mathlib. |
| `not_ready: true` | Needs more blueprint work before it can be attempted. |
| `lean: Ns.decl` | Declaration name(s) that discharge the article. |
| `discussion: 42` | Issue number or URL where the article is being discussed. |
| `article_id: af_...` | Durable identity, `af_` plus 24 lowercase hex digits; `autoform work` requires it on unfinished formalizable leaves, `review record` on the article it records, and `review prepare`, `review check`, and `render --review` on every Lean-mapped article but a module catalog. |
| `review_approved: sha256:<64 hex>` | The hash of the complete review surface someone approved for this article. It shows that surface is unchanged, not who approved it. |
| `open_statements: allowed` | Project policy, valid only in `roadmap/README.md`: a theorem's statement may land with a `sorry` proof (see [Open statements](reference/open-statements.md#open-statements)). Absent or `forbidden` keeps the strict policy. |
| `published: false` | Folder setting, valid only in the `README.md` of a folder below `roadmap/`: `check` and `audit` validate the folder and everything in it, but render leaves it out of the site and of the publication hash. No link on a published roadmap article may point into it, whether a dependency, a source or prose; a link from any other page keeps only its text, with a warning. `audit` and render reject coverage evidence that points into it. A folder inside an unpublished one is unpublished too, whatever its own README says. |

CI at an older `AUTOFORM_REF` rejects keys it predates, such as `area:`,
`navigation:`, `catalog:` and `statement: retracted`; see
[Upgrading](../CHANGELOG.md#upgrading-from-050).

Progress is *derived* from the DAG on every run, so it cannot go stale.
Readiness depends on the policy: under the default strict policy CI rejects
every `sorry`, so a theorem's statement lands only with its proof.

| Derived state | Holds when |
| --- | --- |
| `can_state` | Every statement prerequisite is stated and every proof prerequisite is proved. Under the open policy a theorem waits for no proof prerequisite, and a definition, whose body is its proof, waits for them to be stated. |
| `can_prove` | Stated, every statement prerequisite is stated, and every proof prerequisite is proved (strict policy) or stated (open policy). |
| `proved` | The article records `proof: formalized`, is a stated definition, or is in Mathlib. |
| `conditional` | Proved, but the proof rests on an open statement; open policy only. |
| `fully_proved` | Proved, and every prerequisite is fully proved, recursively. |
| `defined` | A definition is written but rests on unfinished work; one whose body rests on an open statement is `conditional` instead. |

A proved theorem that rests on unfinished work is green, not the dark green of
`fully_proved`. A `conditional` ("conditionally proved") article reaches an
open statement, a theorem stated or retracted but not proved (see
[Open statements](reference/open-statements.md#open-statements)), through its
dependencies; an open dependency counts together with whatever its statement
prerequisites reach, and a proved dependency passes on everything it reaches.
The site colours it violet and lists those open statements in an `Assumes`
row. It is never `fully_proved` until every open statement it assumes is
proved.

## Commands

This section is the single source of truth for the command line. Skills
describe what to achieve and link here, and every `autoform` invocation shown
here or in a skill is parse-checked against the real parser.

The commands below are written as they appear on `PATH` once this Python
package is installed. Inside a consumer project the package is not installed,
so resolve `<AUTOFORM_PLUGIN_ROOT>` from the loaded plugin and prefix each one,
running from the project root:

```bash
uv run --project "<AUTOFORM_PLUGIN_ROOT>" autoform check blueprint --lean-root .
```

`autoform --version` prints the installed version, followed by the plugin
checkout's commit when it runs from one, as in `autoform 0.6.0 (745a88599469)`;
a debrief records the same string.

### init

Create a new project's vault, site configuration, and CI. The layout is fixed,
so it is written rather than described; existing files are left alone, which
makes the same command the repair path:

```bash
autoform init . --title "Finite Flat Group Schemes" \
  --repository-url https://github.com/owner/repo
```

An existing root `.gitignore` must be a regular file with one link; `init`
appends the missing Autoform rules to it, and when it cannot verify the append
the error says the file may be partial: inspect it before retrying. Even with
`--force`, `init` refuses before writing anything an entry that differs from a
path it manages only in letter case or Unicode form (a `Blueprint/` Lean
library, `MkDocs.yml`), a managed directory it cannot list, and a root
`Readme.md` or `readme.md`. The vault is always `blueprint/`, so a Lean library
named `Blueprint` needs a different library name (its lakefile `lean_lib`, root
module and imports), not a lowercase rename.

Generated workflows pin `--autoform-ref` or, by default, the HEAD commit of the
Autoform checkout running the command (or of the marketplace checkout an
installed plugin was copied from), when a safe remote has a cached tracking ref
containing it, tracked files are clean, and the templates match it; an explicit
`--autoform-source` gets no default ref. Without a ref the CI workflows are
omitted.

### project

Create or inspect a Lean project and list Autoform's bundled known-good release
pairs:

```bash
autoform project versions
autoform project new ./FiniteFlat --package FiniteFlat
autoform project new ./FiniteFlat430 --package FiniteFlat --lean-toolchain v4.30.0
autoform project new ./Gauss --package Gauss --library atlas
autoform project inspect path/inside/project --json
```

`project new` builds a complete Lean shell (the release's resolved dependency
manifest, blueprint, and site) in a private sibling directory and publishes it
atomically: the target must be absent, nothing is overwritten, and a failed or
concurrent creation leaves no partial target. A failure or interrupt after
staging can leave a hidden `.autoform-new-*` directory in the parent, which the
error mentions; inspect it before removing it. Its `lakefile.toml` sets
`enableArtifactCache = true` and `restoreAllArtifacts = true`, so checkouts on
the same toolchain share builds through Lake's artifact cache while each
module's `.olean` stays in `.lake/build`. Package names cannot shadow Mathlib
libraries such as `Archive` or `Counterexamples`. Workflows are pinned as
[`init`](#init) pins them. Apart from local Git reads, the command runs no
subprocesses, Lake, Lean, or network operations. Its errors name a code:

- `project-parent-inaccessible` or `project-path-is-symlink`: the parent and
  its ancestors must be readable real directories, not links; on macOS, use
  `/private/tmp` rather than the `/tmp` symlink.
- `project-parent-unsafe`: the parent is group- or world-writable and not a
  sticky directory owned by you or root; run `chmod g-w,o-w` on it.
- `project-parent-busy`: another creation held the parent's lock for 30
  seconds; retry once it is done.
- `project-parent-changed`: the parent path stopped naming the locked
  directory. Nothing was published, but an `.autoform-new-*` stage may remain
  in the original directory; inspect it before removing it.
- `project-create-commit-uncertain`: publication started but its outcome could
  not be confirmed; locate the project before retrying.

Creation fails closed, including on Windows, where POSIX descriptor traversal,
advisory locking, directory sync, or atomic no-replace rename is unavailable.

`--lean-toolchain` also accepts `v4.30.0-rc1` and `leanprover/lean4:v4.30.0`;
`--mathlib-rev` requires it, and neither combines with `--release`. A pair equal
to a catalog entry gets that entry's bundled manifest. Any other pair is written
without `lake-manifest.json`, with a `project-release-unlisted` warning: run
`lake update` in the project (it needs network access, locks Mathlib and
downloads its build cache), then commit the manifest. Use the toolchain that Mathlib revision declares in its own
`lean-toolchain`, or Lake may rewrite the project's toolchain or fail to build.
A toolchain older than v4.27.0 gets a `project-lean-below-minimum` warning.
Warnings go to stderr, or with `--json` to the `warnings` array, where such a
pair reports `"release": null`; the exit status stays 0. Successful JSON uses
schema `autoform-project-creation/v1`.

`--library NAME` names an entry of `autoform_cli/project/libraries.json`, which
pins a shared Lean library to a full commit on a listed release. The project is
created on that release with the library's `[[require]]`, and its manifest
already locks the library's packages, so it needs no `lake update`; the first
Lake command clones them, which needs network access. An unknown name is
`project-library-unknown`, and a package name that is one of the library's
module roots or packages is `project-name-invalid`. The JSON result adds
`library: {name, git, rev}`.

`project inspect` is local and read-only: it inspects the nearest enclosing Lean
project without running Lake, Lean, Git, or the network. Automation should use
`--json`, accept only `autoform-project-inspection/v1`, and branch on `ok`,
`compatibility.status`, and `diagnostics[].code`, not message text. `ok` and
compatibility are independent, and `supported` certifies release identity, not
build validity. Exit 0 means `ok: true`, exit 1 an inspection or catalog error,
and exit 2 invalid CLI usage. The [project-inspection reference](project/README.md)
defines the statuses, JSON fields, and diagnostic codes. `project versions`
lists the bundled pairs, the ones `project new` can lock offline.

### Publishing and the dashboard

Publishing a project runs four steps in order: validate, refresh the vault's
dependency summary, render the site source, then strict-build the site.

```bash
uv run --project "<AUTOFORM_PLUGIN_ROOT>" autoform check blueprint --lean-root .
uv run --project "<AUTOFORM_PLUGIN_ROOT>" autoform-visualize blueprint
uv run --project "<AUTOFORM_PLUGIN_ROOT>" autoform render blueprint \
  --output site-src --lean-root . --require-declarations
uv run --with mkdocs --with mkdocs-material --with mkdocs-literate-nav \
  --with pymdown-extensions mkdocs build --strict
```

Drop `--require-declarations` when reviewing work in progress, where a
statement may name a Lean declaration that does not exist yet. On native
Windows, run `check` and `render` without `--lean-root`; the site then has no
code links ([publication contract](reference/runtime-and-publication.md#publication-contract)).
A Lake project in a subdirectory, such as `v1/`, is passed as `--lean-root v1`,
and links name paths from the repository's top level; edit the `--lean-root .`
that the generated `blueprint-pages.yml` passes to `check`, `audit` and
`render` to match.

`autoform dashboard . --site-dir site` then serves the built site on
`127.0.0.1` until you stop it, with a read-only live overlay of current author
claims at `/__autoform/live.json`, which only the loopback server exposes. The
overlay matches claims on an article's node ID or its `article_id`, reports the
`claim_target` each lease used, and is never written into the vault,
publication manifest, or public site. Claim badges update while it runs; re-run
render and the MkDocs build to refresh everything else.

The generated `blueprint-pages.yml` deploys only a commit that the project's
own `.github/workflows/autoform-verify.yml` (matched by file, not name) passed
on a push to `main`, with code links rendered at that commit by `--ref`. A
failed verification deploys nothing, so the last verified site stays up. Pull
requests and manual runs build the site but never deploy, and cannot cancel a
waiting deploy. To redeploy, re-run the Pages run that the newest successful
verify run on `main` started; re-running an older one deploys the older commit.
A project scaffolded before this rule deploys every push: delete
`.github/workflows/blueprint-pages.yml` and run `autoform init` again, which
writes only missing files. No pin has to move: every `AUTOFORM_REF` since 0.5.0
has `render --ref`.

Pages gates on `check` and `render`, and runs `audit` after `check` only as a
report, with `continue-on-error`: the log lists every finding, or
`OK: roadmap audit passed`. An invalid coverage contract fails `render` before
it writes anything, but `MAPPED` rows (each an audit `declared-coverage-gap`;
a new project lists the template's row) and coverage-role issues, which
`render` prints as warnings, still publish. A project scaffolded before the
report step can add, after `check`, a `continue-on-error: true` step running
`autoform audit blueprint --lean-root .` from the same `uvx --from` source. To
block merges on findings, run `autoform audit` in CI without it.

### check

Validate structure, and optionally check that every `lean:` name really exists
in the project's Lean sources:

```bash
autoform check blueprint --lean-root .
```

`check` validates the graph contract ([Validation](reference/validation-and-audit.md#validation)).
With `--lean-root` it resolves names only in the project's own Lean files, not
in Mathlib or other dependencies under `.lake`; when a name is not found, a note
at the end of the output says that a shared library's declaration belongs in
the article's implementation note.

With `--lean-root`, `check` also warns about each declaration of a usable,
checked-out shared library (see `autoform library list`) whose own docstring
cites an arXiv paper or DOI that an unproved article reaches through its
`## Sources` links, or through a blueprint Markdown page such a link names
(pages over 4 MiB are not read). Silence it by naming the declaration in full
in an implementation note, a page under `blueprint/sources/` or one a
`## Sources` link names, or in project Lean, in full or by its last name
component. Declarations citing a source only through their module docstring
share one warning, silenced by naming the module, or in full a citing
declaration; importing the module names it, importing only an umbrella module
above it does not. Reuse such a declaration and name it in the note of each
article using it; when it does not apply, name it on the source's page under
`blueprint/sources/` with why, which outlasts the notes.

`check` also warns when a library's index cannot be read or parsed, when a
library with a citing declaration fails verification against its checkout, and
when the project's Lake files cannot be used. None of these warnings changes the
exit status.

### audit and coverage

```bash
autoform audit blueprint --lean-root .
```

`audit` adds deterministic completeness, provenance, coverage, checked-fact,
and optional Lean-target checks ([Audit contract](reference/validation-and-audit.md#audit-contract)).
It is local and read-only: it neither contacts network services nor writes
findings back into the blueprint. Pass `--json` for stable machine-readable
output. A nonzero exit status means the audit found at least one finding;
[warnings](reference/validation-and-audit.md#warnings) never change it.

The machine-checkable `coverage/README.md` contract contains one
`Area | Coverage | Evidence` table, one disposition per row:

- `MAPPED` is nonterminal.
- `INVENTORIED` is terminal for exact source accounting and links a
  `catalog: module` record, directly or through a containing roadmap scope:
  `coverage-role-mismatch` names a link that reaches none, and
  `unclassified-inventory` the first catalogs no such row reaches.
- `DECOMPOSED` links source-grounded declaration articles, directly or through
  a containing scope. Links that reach only catalogs are a
  `coverage-role-mismatch`; any other link reaching no declaration leaf, such as
  prose or `not_ready` leaves that declare nothing yet, is a
  `decomposed-without-declaration` warning.
- `DEFERRED` and `OUT` record an explicit later milestone or exclusion.

Audit JSON includes canonical rows, the exact coverage source hash, and counts,
which always have an integer `INVENTORIED` key; `publication.json` records only
aggregate counts. To record both axes of one source area, use distinct
axis-qualified `Area` labels, unrelated to an article's `area:` field:
`Repository inventory / MathlibExt` may be `INVENTORIED` while
`Mathematical exposition / MathlibExt` is still `MAPPED`. Duplicate exact area
labels are invalid. A broad inventory row may link a container and classify
every catalog below it.

The contract is read as published Markdown and fails closed; `coverage.py`
gives the edge cases:

- A table in an HTML comment, a code block, or under a `hidden` attribute is not
  the contract. A table that does not publish, such as one a paragraph runs
  into, is rejected, and a published one the audit does not recognise, such as
  one without outer pipes, is named.
- A comment or code block between rows is reported, with the rows stranded
  below it, rather than truncating the contract. A row holding an unclosed
  `<style>`, or evidence with a raw `<table>`, is refused.
- Evidence holding only a code span, a comment, emphasis, an HTML tag, an
  entity, an empty link such as `[ ](notes.md)`, or hidden text is rejected,
  and so is evidence that is only `TODO`, `TBD`, `pending`, `placeholder`, or
  `unknown`, or opens with one as a marker (`TODO: choose a milestone`).
  "Pending Mathlib PR 1234" passes.
- `INVENTORIED` and `DECOMPOSED` evidence needs a complete inline link to an
  existing roadmap article, and each linked scope must contain the claimed role;
  audit reports a row that does not, and `render` warns. Every local link must
  resolve, fragments included.

#### What coverage completeness does and does not claim

`coverage.complete` in audit and `publication.json` means only that no declared
row is still `MAPPED`. `INVENTORIED` closes exact source accounting and
`DECOMPOSED` says the area has source-grounded declaration articles; neither
implies the other. It does **not** claim the rows cover the source
exhaustively, which no local check can judge, nor that linked articles are
formalized or proved.

Target metrics (the denominator, readiness count, declaration-kind totals, and
progress breakdowns in the book and `autoform check`) count non-container
articles carrying `declaration`, never a `catalog: module` record. A scope's
status ring, item count, and dependency-map legend also count `not_ready`
leaves that declare nothing yet, so deferred work holds its scope open, and
each catalog under a neutral status, `inventory checked` once fully proved and
`inventory pending` until then, which never changes the scope's rolled-up
status; a target that depends on a catalog still waits for it.

### skeleton

Extract what a reader must trust for each formalized statement:

```bash
autoform skeleton blueprint --lean-root .
autoform skeleton blueprint --lean-root . --node chapter/main-result
autoform skeleton blueprint --lean-root . --output skeleton.json --packets review-packets --passages review-passages
```

The skeleton of a `lean:` declaration is its elaborated signature, then every
project declaration its *statement* rests on, transitively, quoted from the
sources in dependency order: a definition with its body, a theorem with its
type only. Proof bodies are never emitted, though Lean's axiom analysis reads
them, so a proof edit can change the reported trust context. Each skeleton
reports the axioms the declaration rests on (a `sorry` shows as `sorryAx`) and,
by name, the non-core constants it assumes from Mathlib or another dependency,
whose definitions are the trusted base and are not expanded.

This is the one command that runs Lean: for each module that declares a
selected target it runs a probe with `lake env lean` against the built project,
so a packet reads as it does to a file importing that module, without the
declaration's local notation, `open`, or `set_option`. Lake must first confirm,
without rebuilding, that every probed module is fresh: a missing
`lake-manifest.json`, stale artifacts, or a source tree that changes during
extraction fails the command, and since the check rewrites Lake's `.hash` files,
`.lake` must be writable. The helper module `autoform-skeleton-helper` and its
`AutoformSkeleton` namespace are reserved; a module that takes one, on
`LEAN_PATH` or not, breaks the probes that import it.

A `partial def` in a trusted closure is refused, and so is a declaration with
no source of its own, such as one a metaprogram adds. A `lean:` name is
unresolved when it is absent from the sources or the built environment, when
Lean declares it in another module than the one whose source holds it, when
the sources define it more than once with no single declaration chosen by the
rules under [Validation](reference/validation-and-audit.md#validation), when it
reaches a refused declaration, or when its probe fails on its own (the reason
quotes Lean's output). That affects only its article: the others still
extract, the command exits nonzero, and nothing is written into the vault.
Limits apply per probe, so a declaration that resolves alone can be unresolved
beside its module's other targets. A missing `lake`, a failed freshness check
or helper build, a dependency library rooted at `Init`, `Lean`, or `Std`, or a
blueprint or source tree that changes during extraction stops the whole
command.

`--output` records the `autoform-skeleton/v5` report, with no timestamp or
absolute path. It names the exact blueprint, the target set, and whether it
covers every target or a `--node` selection. Review evidence comes only from a
report that selects every article; the report never copies a theorem proof.

Run skeleton extraction only in a trusted checkout or an operating-system
sandbox. Lake evaluates `lakefile.lean`, and the probe imports project code
whose initializers, macros, and metaprograms may perform arbitrary IO and can
forge probe output. The Lake freshness check, the helper's build, and each
probe have their own 600-second budget; `--timeout SECONDS` sets the helper's
and each probe's. Probes run in parallel, at most eight at a time. These limits
are resource controls, not a security or authenticity boundary.

`--packets DIR` writes one comment-stripped packet per skeleton, named after
its article and declaration, with a manifest of articles and hashes; a blind
auditor gets the hash-named packets of `review prepare` instead. The
destination must be empty or hold Autoform's packet manifest. Each run replaces
the whole managed tree, aborts if the tree changes before commit, and preserves
an old tree that changes later at a reported recovery path. Packet and passage
manifests use their v2 schemas; v1 trees are recognized and replaced. An
unresolved selected declaration blocks all packet and passage output, though
`--output` alone still records the report. Destinations must be disjoint and
not symlinks, on filesystems with hard links and atomic renames. Combined
outputs are staged together and a failed commit restores the previous set, but
a reader may briefly see outputs of different generations.

A packet holds the signature, the same signature printed raw past project
notation, the canonical kernel material, the statement as written (cut before
its value), and the source of every project definition the statement rests on,
with comments and docstrings removed. Source that may hide a comment the probe
cannot find, such as a body using `local notation`, is withheld, as is an
equation-style statement that cannot be parsed outside its file; both are
marked `-- source not shown`, and the article stays resolved. Source text is
not notation-proof; only the kernel material is.

A `## Sources` link to a non-Markdown file inside the blueprint with a
`#L<start>-L<end>` fragment, such as
`../../../sources/lebl-ra/ch-real-nums.tex#L693-L714`, is a locator naming the
statement's source passage; the same link to a Markdown file is a note. A first
local locator that names no readable, regular, UTF-8 lines inside the
blueprint leaves its article's declarations unresolved. `--passages DIR`, which
requires `--packets`, writes each article's passage to its own managed
directory beside `article.lean`, the joint packet of the article's
declarations: a faithfulness judge gets the article packet and passage, an
auditor of one declaration only its packet.

#### Skeleton hashes

All are SHA-256. An article with several `lean:` names has one drift hash and
one review hash over them, null if any is unresolved. In the report,
`trusted`, `assumed`, and `boundary_modules` hold the whole closure, and
`statement_assumed` and `statement_boundary_modules` the part the statement
reaches, which is all the packet shows.

| Hash | Covers | Changes when |
| --- | --- | --- |
| drift hash | Elaborated root, trusted declarations, direct external assumptions and axioms, dependency edges, Lean version, `.olean` identities of the external boundary | Meaning, axioms used, the toolchain, or an external module changes; not spelling or comments |
| statement hash | The same without the axioms and what only they reach | Meaning changes, a proof inside a trusted definition included; not a theorem's own proof |
| evidence hash | The exact packet bytes | The packet text changes |
| article review hash | Joint packet, cited passage and locator, drift hash | Any of those changes |
| `review_approved` | Title, statement as the site shows it, passage and locator, joint and per-declaration packets, TeX macros the statement uses, each valid read-back's model and testimony | Any of those changes; not a proof edit or a Lean or Mathlib bump that leaves the packets unchanged |

None is a stable statement identifier, reviewer authentication, or an approval
key; all are advisory checksums when candidate code controls the checkout.

#### Read-back cards

A read-back is a blind agent's mathematical-English account of one packet,
recorded with `review record`. Cards live at
`blueprint/readbacks/<article_id>/<encoded-declaration>.md` and hold the exact
packet, its evidence hash as `packet:`, the statement hash as `statement:` (a
record, never compared), a `model:` label the coordinator supplies, not
authenticated, and the testimony. Loading rejects missing or unknown fields,
altered packets, identity mismatches, non-canonical cards, and malformed or
empty testimony.

Testimony is plain text with TeX formulas between dollar signs, written by the
rules in `skills/human-review/references/readback.md`. It is refused for
invisible or reordering characters, combining marks stacked over the lines
around or with nothing to sit on, showing no letter or digit, or exceeding
32 KiB or 500 lines; a write also refuses code points unassigned in its
Python's Unicode data. A formula never invalidates testimony: one
`readback.formula_problems` cannot typeset is shown as typed, and render warns
without changing its exit status.

A card file holds at most 4 MiB. A larger, non-UTF-8, or unreadable file, or a
directory or FIFO, at a card path is reported as an invalid card, as is a card
recording another declaration than its path names or whose `.md` is in another
case; linked cards are skipped, and an unlistable directory under `readbacks/`
stops loading. An oversized card must be removed by hand. A write refuses a
link on the way to the card directory, refuses `--expected-card-hash` for a
missing card, and takes the directory's `flock`, giving up after ten seconds;
it is refused before creating anything where `flock` is missing, Windows
included, though cards still load there. A crash can leave a
`.autoform-readback-*.tmp` file, which the loader ignores; the committed card
is the durable copy. Do not edit cards while a write runs. A write gives
`readbacks/` a `.gitattributes` of `* -text`, since a card with CRLF line ends
is invalid, and Git for Windows needs `core.longpaths` for the paths of long
declaration names.

### review

Review a formalized statement with three commands, then publish the review:

```bash
autoform review prepare blueprint --lean-root . --packets review-packets
autoform review record blueprint --packets review-packets \
  --article-id af_0123456789abcdef01234567 --declaration Ns.result \
  --testimony read-back.txt --model muse-spark-1.1
autoform review check blueprint --lean-root .
autoform render blueprint --lean-root . --review
```

`review prepare` extracts every Lean-mapped article from the built tree and
writes one blind packet per declaration under `blind/`, named by its hash, with
a manifest for the coordinator. Each Lean-mapped article must be a
declaration-sized leaf, or review commands refuse it with
`review-article-shape`; module catalogs are not reviewed. An `origin: cited`
article must link an in-vault, non-Markdown snapshot with an exact
`#L<start>-L<end>` range, no article may cite blank lines, and preparation
refuses a citation it cannot show.

`review record` runs no Lean. It refuses a packet whose bytes do not match its
hash, a packet or testimony that is not a regular file (a FIFO is refused
unread), an `article_id` the blueprint no longer has, and refused testimony,
then files the card; replacing a different card needs `--expected-card-hash`.
It warns about each formula a site would show as typed, with its exit status
unchanged. A card from a stale packet is invalid under `review check`, so
prepare and record again.

`review check` derives its evidence from its own extraction, never a committed
file, and fails until every Lean-mapped article has current cards and a
`review_approved` equal to the review hash it prints. Cards and approvals bind
packets, not statement hashes, so a Lean or Mathlib bump that leaves a packet
unchanged keeps both. An approval also binds the macros in
`blueprint/tex-macros.json` the statement uses, directly or through another
macro, so a macro edit stales only those approvals. An edit to the articles,
cited sources, or cards during the run fails with `review-snapshot-changed`;
rerun once the blueprint is idle. `review prepare`, `review check`, and
`render --review` take the same `--timeout SECONDS` as `skeleton`.

`review prepare` and `review record` exit 2 on input they cannot derive, read,
or trust, on refused testimony, and on a card conflict. `review check` exits 1
on findings, and 2 on evidence it cannot derive or a blueprint that changed
during the run.

`render --review` makes the same check from its own extraction and puts a
*Review* disclosure under every formalized statement: the approval state, the
review hash, the cited passage, and for each declaration its card (current,
invalid with reasons, or missing) before the exact packet; the statement hash,
assumptions, and axioms are marked not bound. An edit during extraction fails
with `review-snapshot-changed`. A passage cut from a file the site leaves out,
such as a script, a file under `readbacks/`, or `atlas.json`, is refused with
`review-source-unpublished`. Articles in `published: false` folders are
reviewed but get no disclosure or warning, and module catalogs get none.
`--timeout` is accepted only with `--review`, and a refused review prints its
reasons on stdout and exits 1.

The gate is opt-in: commit `blueprint/.autoform-review` holding
`autoform-review-policy/v1` and a line end; `autoform init` never writes it.
With the marker, generated CI runs `review check` after the Lean build,
without making advisory roadmap or coverage findings merge blockers, and
deleting every card cannot turn it off. Without it, cards or `review_approved`
fail CI.

`review_approved` is a drift checksum, not an authorization: anyone, an agent
included, can paste the hash `review check` prints, and a current approval is
labelled self-approved wherever it is shown. Authorization needs a CODEOWNERS
rule for `/blueprint/` (in `CODEOWNERS.autoform.example`, activated as under
[Open statements](reference/open-statements.md#open-statements)) and a
default-branch ruleset that requires code-owner review, dismisses stale
approvals, and requires approval of the latest push.

Inspect the current Markdown-derived formalization frontier:

```bash
autoform work list . --lean-root .
autoform work list . --lean-root . --json
autoform work context chapter/result . --lean-root . --json
```

`work list` returns only formalizable leaves whose next statement or proof phase
is unblocked, by the same policy-dependent rule as the derived `can_state` and
`can_prove` states, the runtime projection, and the site's Next up card. Under
the strict policy project CI rejects `sorry`, so a theorem's statement lands
with its proof, and an article's statement phase also waits until its `## Proof
depends on` prerequisites are proved. Under `open_statements: allowed` a
theorem's statement phase waits only for the statement prerequisites to be
stated, a definition's also for its proof prerequisites, which its body uses,
and the proof phase for every prerequisite to be stated. `work
context` accepts the path-derived node ID (see Articles and containment) or an
assigned `article_id` and reports the exact article, dependencies, source
targets (except those the Runtime contract leaves out), Lean targets, blockers,
article and graph source revisions, and claim
target. The article revision hashes that article's bytes alone. A Lean target's
`source_file` is relative to `--lean-root`, and null without one, when the
local scan does not find the declaration, or when it finds several with none
chosen (see Validation). The scan skips build output and nested
checkouts, meaning any subdirectory with a `.git` entry, such as a worker's
worktree or a submodule. Blockers are unmet dependency IDs or one of
`roadmap:not-a-formalizable-leaf`, `roadmap:missing-article-id`,
`roadmap:missing-article-revision`, and `roadmap:not-ready`. The claim target
prefers durable `article_id` metadata. `work list` fails explicitly if an
unfinished formalizable leaf lacks one; add the missing IDs with `autoform
migrate article-ids --write`. `work context` may still
select that article by its path ID to
report the migration blocker. An item whose article records `statement:
retracted` is a revision: it carries `revision` true in JSON, and the text of
`work list` adds a `revision:` line and `work context` a `Revision:` line saying
to start from `autoform work impact` (see the [revision
contract](reference/claims-and-revisions.md#revision-contract)). Both commands are read-only projections of
Markdown.

Under the open policy the text output of `work list` starts with an `Open
statements: allowed` line and adds an `assumes:` line under each item that rests
on open statements; `work context` prints `Open statements:` and `Assumes:`
lines. In JSON, `work list` and `work context` use `autoform-work/v2`: the
frontier and every item carry `open_statements`, and every item carries
`assumes`, the open statements its proof rests on (empty under the strict
policy), plus `revision` for an explicit retraction. The runtime projection
carries the same `open_statements` flag, and each node's runtime status adds
`assumes` and `waiting_on`, the prerequisites that keep an unproved node from
its next phase.

List the open statements and the articles that rest on them:

```bash
autoform work assumptions .
autoform work assumptions blueprint --json
```

`work assumptions` prints the policy, one `open:` line per open statement with
its declarations and the open statements it assumes, if any, one
`conditional:` line per conditional article, and one `unproved:` line per other
listed article that assumes open statements, such as a retracted definition
whose body reaches one.
`--json` writes the `autoform-assumptions/v1` contract that CI audits the build
against: every article whose `lean:` names a declaration, stated or not, with
`open`, `assumes`, and `allowed_open_declarations`, the declarations of the
open statements its Lean may reach, plus its own when it is open. A `mathlib:
true` article is listed with state `mathlib`, `open` false, and nothing assumed
or allowed, so CI checks that its names exist and reach no open statement. A
module catalog is never open; under the open policy, one that is not proved
keeps only the names no non-catalog article's `lean:` lists, and is left out
when none remain: that article's state decides whether such a name is open.
Under the strict policy every such article is listed with `open` false and
nothing allowed, and CI checks that its names exist. It reads Markdown only
and needs no Lean build.

Ask what revising an article's Lean declarations would affect before editing
them:

```bash
autoform work impact chapter/result . --lean-root .
autoform work impact chapter/result . --lean-root . --declaration MyProject.helper --json
```

`work impact` runs a bounded Lean probe against a fresh build and reports
statement-impacted and proof-impacted articles, unnamed helpers, missing
Markdown dependency paths, deprecated declarations and their users, whether
the change is contained, and the complete `claim_targets` set. Helpers shared
by several articles contribute every owner's claim; an unowned helper gets a
stable `lean/<slug>-<digest>` target. A revised declaration that no article
names is claimed the same way, under every nearest owner's target or its own
stable key. `unused_statement_dependencies` lists the stated articles whose
Markdown statement rests on the revised declarations, directly or through other
statement dependencies, that are not statement-impacted: the probe follows
names, so a dependent whose Lean inlines a revised definition's body shows no
use although its statement changes meaning. They join `claim_targets` too. A
`mathlib: true` article is left out: its statement is a Mathlib declaration,
which cannot use the revised one, and it cannot record `statement: retracted`.
A revision is contained exactly when the selected article's target is its only
claim target. A Markdown path reaches the revised declarations when it ends at
the revised article, at an article that names one of them, or, when none names
it, at an owner; missing dependency paths are counted the same way. Project
locality is an exact inventory of regular repository source modules, never a
namespace-prefix guess. The inventory skips nested Git checkouts, ignored
directories such as `build`, and symlinked directories, so the probe refuses a
loaded root-package module whose source the inventory lacks, and a module an
`M.*` or `M.+` glob finds that it did not load, which Lake builds even when
nothing imports it, instead of silently leaving out what such a module uses.

The command snapshots and rereads the roadmap around the probe. It retains one
bound Lean source generation, derives module inventory and locations from that
generation's captured bytes, then recaptures through the same binding and
refuses any content or source-identity change. JSON uses `autoform-impact/v1`
and binds its answer to the Markdown `source_revision`, the repository
`lean_source_revision`, and a `build_revision` hash of the normalized Lean
records. The probe imports project modules, so run it only in a trusted checkout
or sandbox. A missing or stale build is reported as for `work import-impact`.
It compares elaborated types and values; changes to notation, attributes,
instance priority, or unreported generated declarations still require human
review.

Report the coordination and review scope of an import edit without forbidding
the edit:

```bash
autoform work import-impact SELECTOR MODULE [TARGET] --lean-root PATH [--json] [--timeout SECONDS] [--module-scope SCOPE]
```

`import-impact` is advisory and does not edit authored roadmap or Lean source;
its Lake freshness check may refresh build hash sidecars. Under the default
scope the probe imports every module of the root libraries, so each must be
built: a missing or stale build exits 2 with the `lake build` command for those
libraries, how many modules were checked, and the first module Lake found
unbuilt. Freshness is
Lake's rehash of this checkout's `.lake` against this checkout's sources, so a
build in another clone or worktree does not make this one fresh.
`SELECTOR` identifies the working article and `MODULE` the module whose
effective header would change.
Lean supplies the loaded module graph; Autoform binds every node to its captured
root source and configured root-package artifact so dependencies cannot shadow
it. The probe imports project modules, so run it only in a trusted checkout or
sandbox. Like `work impact`, it refuses a root-package module the captured
inventory lacks, so `affected_modules` is complete over the root libraries'
loaded Lake roots/globs, not dormant source files outside that build boundary.
It holds `MODULE` and every loaded module that imports it, directly or
transitively, which covers what an added import can affect. Removing an import
can also drop modules from the build: roots and single-module globs bring in
only what they import, transitively, so a module only the removed import
reached is no longer built. The report does not list such modules.

JSON uses `autoform-module-import-impact/v1` and binds the graph with
`module_graph_revision`; `module_scope` is `loaded-root-library-graph`.

`--module-scope import-closure` loads only the root-package modules whose source
may import `MODULE`: a file is a candidate when its text contains every component
of a candidate's name, repeated until no new file matches, and Lean loads what
the candidates import. Only those modules must be built, and stale-build advice
names them. `affected_modules` is still exact. An article owns an affected
declaration when one of its `lean:` names equals the declaration or is a dotted
prefix of it, so `affected_articles` may list more articles than the default
scope does, and `article_local` is always `false`; `affected_unowned_helpers`
keep the default parent-chain rule. `unresolved_articles` leaves out a name it
cannot resolve when the Lean source index places it in a module outside
`affected_modules`, since the import edit cannot affect it. A `.lean` file
outside the captured sources, such as one in `.lake/packages` or a path
dependency, that may import a candidate makes the command exit 2 and asks for
the default scope. The check over-refuses when a component of a candidate's
name is a common word that dependency sources contain; then use the default
scope.

The import edit's `claim_targets` contain only the selected article and a stable
`module_claim_target` resource, `lean-module/<lowercase-slug>-<sha256[:16]>`.
`affected_claim_targets` are downstream warnings, not pre-emptive ownership
requirements; `claim_keys` and `affected_claim_keys` match the JSON from
`autoform claim list --worker-id WORKER`, and given the corresponding
`claim_targets` or `affected_claim_targets` as targets it lists only those
claims.
`unresolved_articles` reports local
declarations absent from the loaded environment without globally blocking
unrelated edits, while every `affected_unowned_helpers` entry includes its own
claim target and key.

`article` is the selected article (`id`, `article_id`, `claim_target`), and
`module_claim_key` is the claim key of `module_claim_target`.
`affected_articles` lists each article that names, or owns through the parent
chain, a declaration in an affected module, with those `modules`;
`selected_affected` says whether the selected article is one of them.
`article_local` holds only when it is, `affected_claim_targets` is empty, and
no other article has unresolved declarations, like `contained` in
`work impact`.

Imports are allowed regardless of reported breadth. Follow the
[Formalize import workflow](../skills/formalize/SKILL.md#import-edits) for
baseline evidence, conflict checks, claim lifecycle, and post-build review.

Ask whether the blueprint already holds a result before adding an article or
a Lean helper:

```bash
autoform search . "separating hyperplane" --lean-root .
autoform search . "non-ambiguous" --lean-root . --json --limit 20
autoform search blueprint "interlacing" --state proved --state fully_proved
autoform library list .
autoform library index . --lib MathlibExt
```

`search` takes the project or blueprint directory, then one quoted query; both
are required. A query that starts with `-` goes last, after `--`. It exits 0
with or without hits. See the [search contract](reference/search.md#search-contract).

Plan durable article identity metadata, and add it:

```bash
autoform migrate article-ids blueprint --json
autoform migrate article-ids blueprint --check
autoform migrate article-ids blueprint --write
```

`article_id` accepts opaque values in the form `af_` plus 24 lowercase hex
digits. The planner validates uniqueness, proposes deterministic IDs for
missing articles, and includes exact source hashes; without `--write` it is
strictly read-only. `--write` adds each planned ID as the first frontmatter
line of the article that lacks one, or as a frontmatter block of its own, and
changes nothing else. It writes an article only while its bytes still have
the planned hash, checks every article before writing the first, and refuses
an article that changed or became a symlink after planning; after such a
refusal, running it again completes the plan. The runtime and
`autoform work` expose assigned IDs immediately.

Coordinate temporary cross-machine ownership without modifying the book:

```bash
export AUTOFORM_WORKER_ID="agent-name"
autoform claim acquire af_5b0e4d3c2a1f09e8d7c6b5a4
autoform claim renew af_5b0e4d3c2a1f09e8d7c6b5a4
autoform claim release af_5b0e4d3c2a1f09e8d7c6b5a4
autoform claim acquire af_5b0e4d3c2a1f09e8d7c6b5a4 af_0123456789abcdef01234567
autoform claim list af_5b0e4d3c2a1f09e8d7c6b5a4 af_0123456789abcdef01234567
```

Claims are optional: use them when other people or sessions may work on the same
project at the same time, or when the user asks. A single Formalize run needs
none, because its lead keeps its workers apart. A claim excludes only workers
that also claim, so on a shared project every worker uses them. Claim an article
by the `claim_target` that `work context` reports. The board hashes whatever
string it is given, so a claim on an article's path ID and one on its
`article_id` do not exclude each other. Each concurrent agent needs its own
worker ID, because a second acquire by the same owner succeeds. Where shell
state does not persist between commands, as in agent tool calls, pass it with
`--worker-id` on every command instead of exporting `AUTOFORM_WORKER_ID` once.
Leases expire after 1500 seconds unless `--ttl` sets another length. Renew well
within that, and confirm a claim is still held with `renew`, not `acquire`,
which also succeeds once a lease has expired or been released. Several targets
in one command change all-or-nothing; see the [claim contract](reference/claims-and-revisions.md#claim-contract).

Pass several targets to `acquire`, `renew`, or `release` when one change needs
shared ownership. The board reads the set once and sends one atomic push with a
lease for every ref, so either every target changes or none does. A remote that
cannot push atomically is refused, and duplicate or malformed targets fail
before any push. To avoid deadlock, acquire the complete set in one command;
never hold a partial set while waiting for another target.

Claims are fail-closed compare-and-swap leases under
`refs/autoform-claims/` on the Git `origin`; pass `--repo` for another claim
board. A failed acquire or renew means the caller cannot prove ownership and
must stop before committing or pushing protected work. Claims do not prove
mathematical correctness and do not replace branch-level Git CAS.

Ask the agent that led a Setup, Roadmap, or Formalize run what got in its way,
and draft an AutoformBot issue from the answer:

```bash
autoform debrief orchestrator form . --skill formalize
autoform debrief orchestrator record . --skill formalize < /tmp/answer.json
```

Orchestrator debriefs are on by default: `form` prints the form unless
`AUTOFORM_DEBRIEF` is `0`, `false`, `no`, or `off`, or the platform cannot store
the answer, and otherwise says the step is disabled. The form asks separately
for friction caused by the user's local setup, independent of AutoformBot
(`local_setup_friction`), and for friction or issues with AutoformBot itself
(`autoform_friction`). `record` reads one JSON object answering the form from
`--answer` or standard input, refuses anything else, and stores a new versioned
record under `runs/` in the debrief store described below, together with the
installed AutoformBot version. A directory without a roadmap, as during Setup,
is accepted as the project. When `autoform_friction` is not empty, `record` also
writes a draft issue for `facebookresearch/autoform-bot` to `issues/` in the
store and prints its absolute path. The draft ends, below a `---` footer that is
not part of the issue, with a link to GitHub's new-issue form pre-filled with
the draft as it was recorded, so edits belong in the form. When the draft is too
long for a link, the link fills in only the title, and the footer and `record`'s
output say so. The draft holds only the AutoformBot friction and the
environment, with the project path replaced by `$PROJECT` and home directories
by `~`. Nothing is sent: the user reviews, edits, and submits the issue. With
`--json`, `record` prints one object, `{"run_id": ..., "path": ..., "issue":
null | {"path": ..., "url": ..., "url_has_body": true | false}}`.

Ask the agent that just finished a formalization attempt what infrastructure
would have made it cheaper, and keep its answer:

```bash
autoform debrief subagent form af_5b0e4d3c2a1f09e8d7c6b5a4 . --phase proof
autoform debrief subagent record af_5b0e4d3c2a1f09e8d7c6b5a4 . --phase proof \
  --worker-id agent-name < /tmp/answer.json
autoform debrief subagent render .
```

Subagent debriefs are opt-in: `form` prints the form only when
`AUTOFORM_SUBAGENT_DEBRIEF=1` on a platform that can store the answer, and
otherwise says the step is disabled. It fills in the attempt's outcome from the
runtime: the phase succeeded when the article's statement (for `statement`) or
proof (for `proof`) is now recorded as formalized. Pass `--note` with the reason
when it did not. `record` reads one JSON object answering the form from
`--answer` or standard input, refuses anything else, re-reads the outcome from
the runtime rather than trusting the caller, and stores a new versioned record;
it never edits the project. Like the claim commands, it requires `--worker-id`
or `AUTOFORM_WORKER_ID`. With `--json` it prints one object,
`{"attempt_id": ..., "outcome": "succeeded" | "not-succeeded", "path": ...}`,
where `path` is the stored record. `render` rebuilds `views/` inside the store
from the validated records, escaping all agent text and deleting reports whose
record is gone; the records stay the source of truth.

Both kinds of debrief share one store. Records are bounded, normalised, and
created exclusively without following symbolic links, so a record is complete
or absent and never overwritten; platforms that cannot retain directory
descriptors, such as Windows, refuse to read or write them. They live under
`autoform/debriefs/` in the repository's Git common directory, which every
worktree shares and Git does not track; outside Git they fall back to
`$XDG_STATE_HOME/autoform/debriefs/<project>-<hash>/`. Set
`AUTOFORM_DEBRIEF_DIR` to an absolute path outside the Git working tree to
choose another store.

Refresh the vault's dependency summary, `blueprint/dependencies.md`:

```bash
autoform-visualize blueprint
```

The summary is plain Markdown built from the explorer's project map, so it
reads the same in Obsidian, to an agent, and on GitHub where the repository
tracks it (the scaffolded vault ignores it). It holds a table of statuses with
their meanings; one row per chapter with its items, its work ready to pick up,
and the chapters it depends on and is used by, marking a dependency only a
proof needs; the articles themselves while the roadmap has at most 120; and how
to open the explorer, which draws the whole graph. Its front matter carries
`kind: graph` and `autoform_generated: true`. It replaces a missing page, one it
wrote, or the Mermaid page earlier versions wrote, and refuses any other page
with exit status 2.

Build the publishable site source — a book overview, aggregate progress,
statement boxes with collapsed dependency details, a multi-scale dependency
explorer, and direct links to Lean declarations at the current commit:

```bash
autoform render blueprint --output site-src --lean-root . --require-declarations
```

`render` never writes into the vault. Once the roadmap has articles to draw, it
makes the landing page the full-page project explorer, whose hierarchy rail
opens with the project's title, what is formalized and what is unblocked, the
coverage contract, and a link into the book (on phones these sit in the details
sheet). It places a compact progress summary after each chapter's opening prose, keeps `structure.md` as a
short page that opens the explorer, which shows the vault's hierarchy, and
shows a source icon when a `lean:` declaration resolves to a repository
permalink; a catalog
instead links its first eight names in its Lean row and counts the rest. Its
`dependencies.md` opens a full-viewport application and rolls dependencies
through the article hierarchy, with bounded project, chapter, and nested-scope
projections. Global search loads a layout-free index and jumps to the smallest
useful scope. That index, `dependencies/index.json`, the project payload
`dependencies.json`, and every other payload under `dependencies/` are internal
to the bundled viewer, and their schemas may change. The compatibility `dependencies/full.md`
route renders only the project shell and never fits the whole repository into
one canvas. Every generated site projection uses the same deterministic
JSON-derived Canvas and semantic-DOM explorer with search, filters, pan/zoom,
and hash-routed node neighborhoods, so none inherits Mermaid's text, edge, or
SVG-size ceilings. Authored Mermaid remains supported in the vault and book.
The site draws an authored diagram in Mermaid's strict mode, with labels as
plain text, and loads Mermaid only on a page that has one: click callbacks and
HTML in labels do not work there, while a link to a URL does, through
Mermaid's URL sanitizer.
A persistent hierarchy rail keeps the current ancestry and immediate contents
visible, except on phones and, up to 1,100 px wide, under open details, while
the head shows the trail. The project overview groups readable topic cards by
authored mathematical area and reveals only a selected topic's direct
dependency neighborhood; its detail drawer overlays the map instead of
shrinking it. Scope headings are named once, except on the compatibility
`dependencies/full.html` route: its project-title breadcrumb repeats the
heading because it is the only link back to the project map.
Breadcrumbs return through the explorer hierarchy to the book (to the home page
for a roadmap with neither a root article nor root leaves), and every formal
statement links to the smallest explorer scope containing that item. Render
writes no Mermaid graph of its own, so every diagram on the site is one an
article holds. The explorer shows a title as typed, and a link render
writes from file and folder names, such as the book's previous and next links
and the links between statements, is percent-encoded, so a name can make no
link a `javascript:` URL; a Markdown link render moves keeps its decoded
spelling and starts with `./` when its first segment, a folder's or a file's
name, holds a colon, for the same reason. Point
`mkdocs.yml` at `docs_dir: site-src` and enable `md_in_html` plus a
`pymdownx.superfences` mermaid fence; see the [setup
template](templates/mkdocs.yml). The
generated `javascripts/blueprint-mermaid.js` loads Mermaid itself, so the
configuration lists that script but not the Mermaid library.

This shared-explorer layout replaces the `dependencies/nodes/*.html` focus
pages of earlier sites: a statement's dependency link is now
`<scope>.html#node=<id>`, and an old focus-page link no longer resolves. Only a
legacy `dependencies/full.html#node=<id>` link redirects, through the global
index, to the smallest bounded scope containing that node. The [publication
contract](reference/runtime-and-publication.md#publication-contract) gives the schema and when render replaces an
earlier site.

`render` also writes `javascripts/mathjax.js`, the site's MathJax
configuration, on every build; `mkdocs.yml` lists it before the MathJax
bundle, as `autoform init` writes both. It expects MathJax 3.2.2, the release
its TeX settings were checked against, loads it itself when no bundle is
listed, and leaves formulas as typed under any other release. Another script
in `mkdocs.yml` cannot replace that configuration: an assignment to
`window.MathJax`, such as the snippet Material's documentation gives, is
ignored with an error in the browser console. The articles on a page share
one TeX input, with the packages base, ams, noundefined, boldsymbol,
mathtools, braket, mhchem, and amscd (`CD` diagrams), and the project's macros
from `blueprint/tex-macros.json`, written as MathJax's `tex.macros` is: a name
maps to a body, `[body, arguments]`, or `[body, arguments, default]`. So that
no formula changes another or colors a
symbol like the site's status marks, that input turns off `\label`,
`\mmlToken`, `\DeclareMathOperator`, the paired-delimiter and tag-form
commands of mathtools, and `\mathtoolsset`: each shows in red and does nothing,
however a formula or a macro reaches it, as `\newcommand`, `\def`, `\require`,
and any other command those packages do not define already do. The other
packages MathJax would load on demand stay off: cancel, bbox, and enclose take
a color, as color does; html sets classes, styles, and links; unicode picks
fonts; action adds tooltips and toggles; newcommand and extpfeil define
commands; and verb and bussproofs are not loaded either. So `\cancel`,
`\bbox`, `\color`, `\href`, `\unicode`, and the rest show in red too. A macro may not
take one of their names; `check` and `render` warn about a macro they leave
out. They judge and build the script from
the copy of `tex-macros.json` that `render` reads once and publishes beside it,
so an edit made during a render reaches neither. Each read-back card is
typeset with a TeX input of its own that knows only base, ams, and
noundefined, so nothing an article, another card, or the project's macros
define reaches it. The articles' input, and `check`, read only the formulas
the site's Markdown marks, such as
`$...$` or `$$...$$` in an article. Other text, such as a
statement's title in its heading, a `discussion:` value, the lead on the home
page, the navigation, and a table of contents, is shown as typed, TeX and all.
Every formula paints only within its own line and the block that holds it,
with either renderer and any theme, so no article formula can cover a card, a
mark, or the text beside it. An inline formula wider than its paragraph is cut
at the paragraph's edge, so write one that wide as a display, which scrolls,
as does a card too wide for the page.

A project scaffolded before `render` wrote that file keeps a
`blueprint/javascripts/mathjax.js` and needs no edits: `render` replaces it
with its own, with a warning if the copy was edited since `autoform init`
wrote it, since those edits are lost; move its macros to `tex-macros.json` and
delete it.

`render` writes `stylesheets/blueprint.css`, `javascripts/blueprint-mermaid.js`,
`javascripts/blueprint-live.js`, `javascripts/blueprint-dag.js`, and
`assets/autoform.svg` over the vault's copies the same way, and writes
`SUMMARY.md`, `structure.md`, `publication.json`, the `dependencies.md` and
`dependencies.json` explorer files and the `dependencies/` explorer pages, and
the chapter pages it consolidates. A
directory holding a file at any of these paths, or a file where one of their
folders goes, stops `render` with the path it is at, before anything is
written; `check` warns about it. The stale `dependencies.html`, `graph.html`,
and `progress.md` at the vault's root are kept out of the site, and a
directory named `graph.html` or `progress.md` is published as the vault's own
(one named `dependencies.html` is too, but MkDocs builds that page from
`dependencies.md`, so the build fails). A `tex-macros.json` directory that
holds files leaves the site without project macros, with a warning.

Besides its Markdown pages, a vault publishes only files a browser shows or
offers to save and runs nothing in: images (`.png`, `.jpg`, `.jpeg`, `.gif`,
`.webp`, `.avif`, `.bmp`, `.ico`), `.pdf`, and plain-text `.txt`, `.csv`,
`.json`, `.bib`, `.tex`, and `.lean` files, whatever the case of the suffix.
Render copies them into the site as they are. Any other file under
`blueprint/`, such as an `.html` page, an `.svg`, a script, or a stylesheet,
would be the site's own markup once a reader followed a link to it, so the
site leaves it out, and `check` and `render` warn about it by its path: write
it as Markdown, save it as an image, a PDF, or plain text, or keep it outside
`blueprint/`. An Obsidian `.canvas` file is left out without a warning, as
`.obsidian` is. A Markdown page that is not UTF-8 is left out with a warning too.
A link to anything the site leaves out keeps only its text, so the strict
build finds nothing missing: such a file, a hidden path outside `sources/`, or
a page in a `published: false` folder. `check` and `render` warn about each
such link to a hidden path or an unpublished folder, naming the page.
A copy of one of the files render writes, listed above, is not published;
render's own is.

### Upgrading from an earlier Autoform

What an existing repository meets when it moves to this version:

1. CI at an older `AUTOFORM_REF` rejects `catalog:` and `area:` as unsupported
   frontmatter keys and `INVENTORIED` as an unknown coverage disposition, so
   move the pin before using them. Older refs assign no areas from
   `blueprint/atlas.json` but publish the file, so a project with unpublished
   folders moves the pin before adding it.
2. A `DECOMPOSED` link that reaches only prose or leaves marked `not_ready`
   that declare nothing yet is now a `decomposed-without-declaration` audit
   warning, which `render` also prints; neither fails.
3. Coverage JSON is `autoform-coverage/v2`: `INVENTORIED` is a new terminal
   disposition, and `counts` always holds an `INVENTORIED` key. `audit`'s
   coverage line always shows an inventoried count.
4. `publication.json` is `autoform-publication/v3`. The first render replaces a
   v2 site and refuses a v1 one, and the dashboard reports an older site as
   stale until then; the [publication contract](reference/runtime-and-publication.md#publication-contract) gives
   the rules.
5. The runtime is `autoform-runtime/v4`, which gives each node a nullable
   `catalog`.
6. `audit --json` carries a `warnings` list beside `findings`, and the text
   output adds `warning:` lines; neither changes the exit status.
7. `check`'s status line counts only leaves that carry `declaration`, so
   containers, prose leaves and `not_ready` leaves that declare nothing yet
   drop out of it, and with `--lean-root` it counts the distinct `lean:` names
   it resolved rather than the articles naming them. A `blueprint/atlas.json`
   that is not `autoform-atlas/v1`, which earlier versions ignored, now draws a
   warning from `check`, `render` and `audit`; it fails nothing.
8. Old `dependencies/nodes/*.html` links no longer resolve: only
   `dependencies/full.html#node=<id>` redirects, and a statement's dependency
   link is now `<scope>.html#node=<id>`.
9. Setup leaves an existing `mkdocs.yml` alone. A large site can add Material's
   `navigation.prune` feature by hand, as the scaffolded configuration does.
10. A declaration whose name carries an explicit universe binder on its
    keyword's line, as in `def f.{u}`, is now read as `f`, as it already was
    when the name sat on the next line. A `lean:` name for such a declaration
    now resolves, and an alias of one is read through its target for limits,
    kind and size. A name declared that way in one file and plainly in another
    is now `defined more than once` in `check` and `lean-target-ambiguous` in
    `audit`, where earlier versions passed.
11. Every `autoform search --json` hit now carries a nullable `catalog`,
    `module` for a module catalog, while the schema stays
    `autoform-search/v1`: `autoform-search/v2` already names the `--library`
    output. A consumer that rejects unknown keys must accept the new one.
12. `autoform-visualize` writes a plain-Markdown dependency summary to
    `blueprint/dependencies.md` in place of the Mermaid graph. It replaces a
    missing page, its own, or the Mermaid page earlier versions wrote, and
    refuses any other page with exit status 2. Its `--link-extension` option
    is gone: the summary is read in the vault, so its links name the Markdown
    files.
13. The site draws authored Mermaid diagrams in strict mode, with plain-text
    labels, and only on pages that have one, so click callbacks and HTML in
    labels stop working; links to URLs still work. The site no longer appends
    the status palette's `classDef` lines, so a class such as
    `A:::fully_proved` is no longer coloured. A `mkdocs.yml` that loads
    Mermaid from the CDN keeps working, and may drop that line once CI's
    `AUTOFORM_REF` includes this change: a render pinned before it needs the
    line to draw any diagram.

## Contracts

Each area's contract has its own page:

- [Validation and audit](reference/validation-and-audit.md): what `check` and `audit` refuse or warn about.
- [Search](reference/search.md): `autoform search`, and searching a library the project depends on.
- [Open statements](reference/open-statements.md): conditional results and the open-statement policy.
- [Claims and revisions](reference/claims-and-revisions.md): leases and revising a published statement.
- [Runtime and publication](reference/runtime-and-publication.md): `doctor`, the runtime file and the published site.
