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

The H1 is the article's human title. Container
prose supplies the mathematical exposition, and a standalone list item linking
to a formalizable leaf places that definition or result at the exact position in
the published chapter. Leaves without a placement slot appear under an explicit
“Additional formalization targets” section rather than disappearing; a module
catalog without one appears under “Module inventories” instead.

Keep the root roadmap article short: it is the book's preface and table of
contents, not a dump of every planned milestone. Large planning inventories
belong in coverage or progress views; detailed containers should introduce their
mathematics in prose and place statements under meaningful section headings.

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
`##` heading, without the H1 line. The article's first H1 (its title), if
written below a `##` section, ends that section and resumes the statement; a
later H1 stays in its section. No heading deeper than `##` ends it, and neither
does a `##` line inside a fenced code block or an HTML comment. `autoform audit`
and the published theorem box both read that span. A fence closes only on a
bare fence line. A fence that never closes is read as plain text when its
article is inspected alone, so it hides no heading or dependency link there,
but on a chapter page it can pair with a later article's closing fence and hide
everything between them, so `check` warns about one at the margin and the site
shows that page as typed (see [Validation](reference/validation-and-audit.md#validation)). The audit reports a
fence with no closing line as `unclosed-code-fence`. A later bare fence line of
the same character and at
least the opener's length closes it here, though the page asks for the opener's
exact length and indent, so close each fence with its own line. The page can
also pair an unclosed backtick fence line with a later backtick run in the same
paragraph and show the text between them as inline code; a link there is not a
link on the page but is still read as a dependency.

An HTML comment that never closes, even one opened by a `<!--` in inline code
or an indented code block, hides every heading and dependency link after it:
the graph loses those edges, and the part of the article the comment opens in
keeps the rest, so one opened in the statement puts the later sections,
dependency list included, in the theorem box. Nothing reports the comment
itself.

`## Depends on` lists what the article needs in order to be *stated*;
`## Proof depends on` lists what only its *proof* needs. Both are graph edges,
except a link in a code block, fenced or indented, or in an HTML comment. Links
anywhere else are ordinary navigation or citations. Dependencies resolve
relative to the current article and must point at another roadmap article.

The optional `declaration` field marks a formalizable leaf and describes its
intended Lean artifact, for example `def`, `theorem`, `lemma`, `structure`, or
`instance`. Container and exposition articles omit it. Autoform records this
hint but does not constrain the set of Lean declaration commands. Declarations
that introduce data rather than a proposition carry no separate proof
obligation; leading modifiers such as `noncomputable` do not change that, and an
`axiom` does not get this shortcut.

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

Mathematical topics and repository organization are different hierarchies.
An optional container-only `navigation` role makes the difference explicit:

- `topic` (the default): a mathematical subject or coherent group of results.
- `collection`: a library or other organizational collection. Its parent's
  overview shows the collection's children in its place.
- `transparent`: a generated pagination or range container, flattened the
  same way; like a collection, it is left out of the outline and ancestor
  breadcrumbs.
- `source`: a book or other source corpus, shown as itself.
- `module`: a container that mirrors one Lean source module and holds its
  declarations. It is shown like a topic, and its size is the module's (see
  [Structure](reference/validation-and-audit.md#structure)).

An overview, a page with a collection, pagination or source child, draws what
remains after collections and pagination are replaced by their contents.
These roles never change article identity, containment, proof readiness, or
dependency edges. A relation that mentions a collection itself stays attached
to the collection, so the overview that shows the collection's contents in its
place does not draw it, while other pages draw it from the collection's
boundary: depend on an article inside the collection instead.

For a taxonomy maintained separately from article files, `blueprint/atlas.json`
may assign the same areas without moving pages:

```json
{"schema":"autoform-atlas/v1","areas":{"Geometry & Topology":["topology","geometry"]}}
```

Every listed value is a roadmap node id. A node takes the first area that
lists it, and an `area:` authored on the node wins over the file. The file only
assigns areas, so it never stops a command: `check` and `render`
warn about each entry they ignore, or about the whole file when it is not
readable `autoform-atlas/v1` JSON, and `audit` reports each as an
`atlas-omission` [warning](reference/validation-and-audit.md#warnings). An older `AUTOFORM_REF` assigns no areas
from the file but publishes it as a static file, with every id it names.
Render reads it for the explorer's areas and leaves the file itself out of the
site, since it may name articles in unpublished folders; a page's link to it
keeps only its text.

A repository-wide inventory may use a narrative leaf to summarize an existing
Lean module containing several declarations. Such a leaf sets
`catalog: module` and omits `declaration`, so it is never dispatched as one
proof task. A catalog must be a leaf: `audit` reports one with contained
articles as `catalog-container`. Every catalog links a declaration ledger under
`blueprint/sources/` from its `## Sources` section: `check` warns about a
catalog that links none and `audit` reports it as `catalog-missing-ledger`,
while a link to a missing ledger fails both, as such a source link does for any
article. A hidden ledger under `sources/` draws a `check` warning and fails only
`audit`, as [Validation](reference/validation-and-audit.md#validation) explains. A completed catalog also
records in `lean:` the full name of every public declaration the module writes
with a declaration keyword, which is what the Lean source index records (see
[Validation](reference/validation-and-audit.md#validation)). Names Lean generates, such as constructors,
structure fields, derived or unnamed instances, and `@[ext]`, `@[simps]`, or
`@[to_additive]` results, and declarations the index cannot see yet, behind
`nonrec` or `meta` or written `class inductive`, go in the ledger as
supporting entries, never in `lean:`; a `private` name never goes in `lean:`.
A completed catalog may assert `statement: formalized` and `proof: formalized`
when the complete module has been checked. It contributes to the neutral
inventory metric and graph status while remaining a readable page in the vault
and a section of its parent chapter on the site, but its own entry stays
outside the mathematical `Scoped roadmap` completion percentage. Like any
prerequisite, a catalog linked under `## Depends on` or `## Proof depends on`
holds its dependents back until its whole-module assertion is recorded, so a
dependent that needs one result links the declaration article that expounds it.

`check --lean-root` and `audit --lean-root` resolve every name the catalog
lists, and say for a catalog name they do not find that a generated name
belongs in the ledger. They cannot prove that the list omitted no newly added
public declaration; completeness remains an authored assertion.
`audit --lean-root` also reads the
[elaboration limits](reference/validation-and-audit.md#elaboration-limits) of the declarations a catalog
resolves and reports them as warnings, which never fail the audit. A catalog
that records `proof: formalized` also gets `lean-target-wanted` for a wanted
target it names; the deprecation, declaration-kind, and node-size checks apply
only to declaration articles.

Versioned implementation notes live outside the mathematical roadmap at
`blueprint/.implementation-notes/<article_id>.md`, one file per article. The
durable ID survives article moves. Claims keep independent workers from editing
the same leaf's note; containers have no claims, and any worker may delete a
note that `autoform audit` reports as stale or repair an orphaned one. Every
command that loads the graph, including `autoform check`, rejects malformed,
empty, symlinked, or orphaned notes; assign the article ID before creating its
note. Parallel branches can orphan a note without a Git conflict, when one
deletes or merges an article while another writes its note; a worker repairs
that by moving anything still useful into the surviving article's note and
deleting the orphan. When the article still exists but lost its `article_id`
line, restore the line instead.
Delete the file once its article is proved; for a container, delete it once
every formalizable descendant, and every leaf marked `not_ready` beneath it,
is proved and there is at least one; a module catalog never counts. `autoform
audit` reports a note left behind after that point. The directory is hidden, so
render omits it from the site and the publication hash.

## Assertions and derived status

An article asserts only facts a human or agent verified:

| Key | Meaning |
| --- | --- |
| `area: Geometry & Topology` | Authored mathematical region for atlas grouping. CI's `autoform check` at an older `AUTOFORM_REF` rejects the key, so move the pin first, or assign the area in `blueprint/atlas.json`, which older refs ignore. |
| `navigation: collection` | Presentation-only container role: `topic`, `collection`, `transparent`, `source`, or `module` (see above). CI's `autoform check` at an older `AUTOFORM_REF` rejects the key, so move the pin first. |
| `catalog: module` | A non-dispatchable leaf cataloging one existing Lean module. Its `lean:` lists the module's public keyword-declared names, and it links its declaration ledger under `blueprint/sources/` from `## Sources`; cannot be combined with `declaration` or the `mathlib*` keys. CI's `autoform check` at an older `AUTOFORM_REF` rejects the key, so move the pin first. |
| `statement: formalized` | The Lean statement exists and compiles. Requires `lean:`. |
| `statement: retracted` | A revision retracted the statement while `lean:` still names the old declaration, which stays in the build until Formalize restates the article and records `statement: formalized` in its place. Requires `lean:`; invalid with `proof: formalized` or `mathlib: true`. CI's `autoform check` at an older `AUTOFORM_REF` rejects the marker, so move the pin first; until then, retract by removing `statement` and `proof` and keeping `lean:`. |
| `proof: formalized` | The Lean proof compiles. Requires `statement: formalized` and `lean:`. Under the open policy it may rest on open statements, and the article is then conditional; only the derived `fully_proved` means complete and `sorry`-free. |
| `mathlib: true` | The result is upstreamed into Mathlib. |
| `not_ready: true` | Needs more blueprint work before it can be attempted. |
| `lean: Ns.decl` | Declaration name(s) that discharge the article. |
| `discussion: 42` | Issue number or URL where the article is being discussed. |
| `article_id: af_...` | Durable identity, `af_` plus 24 lowercase hex digits; `autoform work` requires it on unfinished formalizable leaves, `review record` on the article it records, and `review prepare`, `review check`, and `render --review` on every Lean-mapped article but a module catalog. |
| `review_approved: sha256:<64 hex>` | The hash of the complete review surface someone approved for this article. It shows that surface is unchanged, not who approved it. |
| `open_statements: allowed` | Project policy, valid only in `roadmap/README.md`: a theorem's statement may land with a `sorry` proof (see [Open statements](reference/open-statements.md#open-statements)). Absent or `forbidden` keeps the strict policy. |
| `published: false` | Folder setting, valid only in the `README.md` of a folder below `roadmap/`: `check` and `audit` validate the folder and everything in it, but render leaves it out of the site and of the publication hash. No link on a published roadmap article may point into it, whether a dependency, a source or prose; a link from any other page keeps only its text, with a warning. `audit` and render reject coverage evidence that points into it. A folder inside an unpublished one is unpublished too, whatever its own README says. |

Everything a reader thinks of as progress is *derived* from the DAG on every
run, so it cannot go stale. Readiness depends on the project's policy: under
the default strict policy CI rejects every `sorry`, so a theorem's statement
lands only with its proof; under `open_statements: allowed` it may land with a
`sorry` proof.

| Derived state | Holds when |
| --- | --- |
| `can_state` | Every statement prerequisite is stated and every proof prerequisite is proved. Under the open policy a theorem waits for no proof prerequisite, and a definition, whose body is its proof, waits for them to be stated. |
| `can_prove` | Stated, every statement prerequisite is stated, and every proof prerequisite is proved (strict policy) or stated (open policy). |
| `proved` | The article records `proof: formalized`, is a stated definition, or is in Mathlib. |
| `conditional` | Proved, but the proof rests on an open statement; open policy only. |
| `fully_proved` | Proved, and every prerequisite is fully proved, recursively. |
| `defined` | A definition is written but rests on unfinished work; one whose body rests on an open statement is `conditional` instead. |

`proved` and `fully_proved` differ on purpose: a theorem whose own proof
compiles but which rests on unfinished work is green, not dark green.
`conditional`, labelled "conditionally proved", is the open policy's case of
that: the article is proved, but it reaches an open statement, a theorem that
is stated or retracted but not proved
(see [Open statements](reference/open-statements.md#open-statements)), through its dependencies. An open
dependency counts together with whatever its statement prerequisites reach, and
a proved dependency passes on
everything it reaches. The site colours it violet, never green, and lists those
open statements in an `Assumes` row on the article page. It is never
`fully_proved`, which keeps its meaning in both policies; a conditional result
is complete only once every open statement it assumes is proved. The
palette and state names follow
[leanblueprint](https://pypi.org/project/leanblueprint/), so the published
graph reads the same way as the Lean community's LaTeX blueprints.

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

Create a new project's vault, site configuration, and CI. The layout is fixed,
so it is written rather than described; existing files are left alone, which
makes the same command the repair path:

```bash
autoform init . --title "Finite Flat Group Schemes" \
  --repository-url https://github.com/owner/repo
```

Pass `--autoform-ref <sha>` to pin the generated workflows at an immutable
commit, `--force` to overwrite, and `--json` for machine-readable output.
An existing root `.gitignore` must be a regular file with one link; `init`
appends the missing Autoform rules to it. If an append cannot be verified, the
error says it may be partial: inspect the file before retrying. Before writing
anything, even with `--force`, `init` refuses an existing entry that differs
from a path it manages only in letter case or Unicode form, such as a
`Blueprint/` Lean library or `MkDocs.yml`: Git and Linux CI see only the
exact spelling, while a case-insensitive filesystem resolves the managed path
to the variant. `init` also refuses when it cannot list a directory on a path
it manages. A root `Readme.md` or `readme.md` is refused, not skipped like an
existing `README.md`.
The vault is always `blueprint/`, so a Lean library named `Blueprint` needs a
different library name (its lakefile `lean_lib`, root module and imports), not
a lowercase rename.

Create or inspect a Lean project and list Autoform's bundled known-good release pairs:

```bash
autoform project versions
autoform project new ./FiniteFlat --package FiniteFlat
autoform project new ./FiniteFlat430 --package FiniteFlat --lean-toolchain v4.30.0
autoform project new ./Gauss --package Gauss --library atlas
autoform project inspect .
autoform project inspect path/inside/project --json
autoform project versions --json
```

`project new` requires an absent target and uses the catalog's recommended
release unless `--release` names another listed one. It builds a complete Lean
shell, with the release's Lake-generated resolved dependency manifest,
blueprint, and site, in a private sibling directory, validates it, and
publishes it with an atomic no-replace rename: it never overwrites an existing
path, a failed or concurrent creation leaves no partial target, and exactly one
concurrent creator wins. A failure or interrupt after staging can leave a
hidden `.autoform-new-*` directory in the parent, and the error says so;
inspect it before removing it. The published tree has modes 0755 for
directories and executables and 0644 for other files, whatever the umask.
Its `lakefile.toml` sets `enableArtifactCache = true` and
`restoreAllArtifacts = true`, so checkouts on the same toolchain share builds
through Lake's artifact cache while each module's `.olean` stays in
`.lake/build`, where Autoform's probes load it.
Package names cannot shadow Mathlib libraries such as `Archive` or
`Counterexamples`.
Generated workflows are pinned as `init` pins them: `--autoform-ref` must be a
full commit SHA, an explicit `--autoform-source` carries its own ref or none,
and without flags the workflows pin the HEAD commit of the Autoform checkout
running the command, or of the marketplace checkout an installed plugin was
copied from. That pin is inferred only when a safe remote (Autoform's canonical
repository, then `origin`, then `upstream`, then a unique remaining one) has a
cached tracking ref containing HEAD, tracked files are clean, and the scaffold
renderer and templates match that commit; an installed copy must match the
checkout too. Without a ref the local project is complete but the workflows are
omitted. Apart from local Git reads, the command runs no subprocesses, Lake,
Lean, or network operations.

Its errors name a code and what to do:

- `project-parent-inaccessible` or `project-path-is-symlink`: the parent and
  each of its ancestors must be readable real directories, since no path
  component is followed through a link. On macOS, use the canonical
  `/private/tmp` path rather than the `/tmp` symlink.
- `project-parent-unsafe`: the parent is group- or world-writable and not a
  sticky directory owned by you or root; `chmod g-w,o-w` on the parent fixes it.
- `project-parent-busy`: another creation in the same parent held its lock for
  30 seconds; retry once it is done.
- `project-parent-changed`: the parent path stopped naming the locked directory
  before publication. Nothing was published, but an `.autoform-new-*` stage may
  remain in the original directory; inspect it before removing it.
- `project-create-commit-uncertain`: publication started but its outcome could
  not be confirmed, for example because the parent path changed after the
  project was published; locate the project before retrying.

Creation fails closed where POSIX descriptor traversal, advisory locking,
directory sync, or atomic no-replace rename is unavailable, including on
Windows.

`--lean-toolchain` takes a Lean release tag (`v4.30.0`, `v4.30.0-rc1`, or
`leanprover/lean4:v4.30.0`) and `--mathlib-rev` a Mathlib tag, branch, or
commit, defaulting to the same tag; `--mathlib-rev` requires `--lean-toolchain`,
and neither combines with `--release`. A pair equal to a catalog entry gets that
entry's bundled manifest. Any other pair is written without
`lake-manifest.json` and reported with a `project-release-unlisted` warning:
run `lake update` in the project, which needs network access, resolves and
locks Mathlib, and downloads the Mathlib build cache, then commit the manifest.
Use the toolchain that Mathlib revision declares in its own `lean-toolchain`;
otherwise Lake may rewrite the project's toolchain, warn, or fail to build.
Until the manifest exists, `project inspect` reports `indeterminate` with
`missing-lake-manifest`; afterwards, `unlisted`, or `supported` when Lake locks a
catalog commit. Autoform needs Lean v4.27.0 or
newer (the skeleton probe uses that release's `String` API and the generated
audit reads ILean `decls`); older toolchains get a `project-lean-below-minimum`
warning. With `--json`, such a pair reports `"release": null` and its warnings
go to the `warnings` array; otherwise warnings go to stderr. Either way the
exit status stays 0. Successful JSON uses schema
`autoform-project-creation/v1`.

`--library NAME` names an entry of the bundled library catalog,
`autoform_cli/project/libraries.json`. Each entry pins a shared Lean library
to a full commit on a listed release. The project is created on that release,
its `lakefile.toml` gains the library's `[[require]]` after the existing
blocks, and its `lake-manifest.json` is the release's bundled manifest plus the
library's resolved packages, so it needs no `lake update`. The first Lake
command clones the packages the manifest locks, which needs network access.
`--library` combines with no version option. An unknown name is
`project-library-unknown`, and a package name that is one of the library's
module roots or packages is `project-name-invalid`. The JSON result adds
`library: {name, git, rev}`.

`project inspect` is local and read-only. It inspects the nearest enclosing Lean
project without running Lake, Lean, Git, or the network. For automation, use
`--json`; accept only `autoform-project-inspection/v1`, then branch on `ok`,
`compatibility.status`, and `diagnostics[].code`, not message text.

Treat `ok` and compatibility independently:

- `ok` reports whether inspection found errors.
- `compatibility.status` is `supported` when the active Lean/Mathlib release
  identity matches the bundled catalog, `unlisted` when comparable but absent,
  and `indeterminate` when Autoform cannot establish that identity.

Exit 0 means `ok: true`, exit 1 an inspection or catalog error, and exit 2
invalid CLI usage. `supported` certifies release identity, not build validity.
See the [project-inspection reference](project/README.md) for resolver rules,
scope limits, JSON fields, nullability, and diagnostic codes.

`project versions` lists the bundled catalog of known-good Lean and Mathlib
pairs. These are the pairs `project new` can lock offline; it does not resolve
others, which it writes unlocked for `lake update`.

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

`autoform dashboard . --site-dir site` then serves the built site locally, with
live claims, until you stop it.

Drop `--require-declarations` when reviewing work in progress, where a
statement may name a Lean declaration that does not exist yet. On native
Windows, run `check` and `render` without `--lean-root`: the site then has no
code links (see the publication contract below). A Lake project in a
subdirectory of the repository, such as `v1/`, is passed as `--lean-root v1`.
Links name paths from the repository's top level, so its files link under `v1/`,
and a blueprint beside it, such as `blueprint/`, under `blueprint/`. The
generated `blueprint-pages.yml` passes `--lean-root .` to `check`, `audit` and
`render`; edit each to match.

`dashboard` serves the exact built MkDocs site on `127.0.0.1`, choosing an
available port unless `--port` is supplied, and adds a read-only live overlay
from current author claims. Static content remains the
same artifact deployed to GitHub Pages; only the loopback server exposes
`/__autoform/live.json`. The overlay is ephemeral, matches claims taken on
either an article's path-derived node ID or its `article_id`, reports in that
JSON the `claim_target` each lease used, and is never written into the vault,
publication manifest, or public site. Re-run render and the MkDocs build to
refresh durable content; claim badges update while the local server is running.

Validate structure, and optionally check that every `lean:` name really exists
in the project's Lean sources:

```bash
autoform check blueprint --lean-root .
autoform audit blueprint --lean-root .
```

`check` validates the graph contract. With `--lean-root` it resolves names only
in the project's own Lean files, not in Mathlib or other dependencies under
`.lake`; when a name is not found, a note at the end of the output says that a
shared library's declaration belongs in the article's implementation note.

With `--lean-root`, `check` also compares the blueprint's sources with each
usable shared library whose package is checked out (see
`autoform library list`). An unproved article reaches the arXiv papers and DOIs
that its `## Sources` link targets cite, and those cited by a Markdown page
under the blueprint that such a link names, up to 4 MiB; link text is not read.
A container stops reaching them once every formalizable article in its scope,
and every leaf marked `not_ready` beneath it, is proved, and there is at least
one: when audit asks for its implementation note to be deleted, and a module
catalog, which inventories existing Lean, never counts. For each complete
declaration whose own docstring cites a reached source, `check` warns
unless an implementation note, a Markdown page under `blueprint/sources/` or a
page an article's `## Sources` links names it in full, or a project Lean file
names it in full or by its last name component, since `open` shortens names; any
identifier with that component counts, comments and strings included, so a
generic one such as `symm` can hide the warning. Declarations that cite a
reached source only through their module's docstring share one warning for the
module, which naming the module, or in full one of its declarations citing that
source, silences; a Lean file that imports the module names it, but one that
imports only an umbrella module above it does not. Such a declaration usually
proves part of the source being formalized: reuse it and name it in the
implementation note of each article that uses it, or, when it does not apply or
no article concerns it, name it on the source's page under `blueprint/sources/`
with why. That record outlasts the implementation notes, which audit asks to
delete once their article is proved, and covers every article that reaches the
source, including ones added later.

Identifiers match across their usual forms: versions; `abs`, `pdf`, `html`,
`e-print` and `src` URLs, with or without a trailing slash; old-style
identifiers such as `math.AG/0210149`; arXiv's own DOIs; `https://doi.org/` and
`dx.doi.org` links, percent-encoded or not, up to a query or fragment; and the
labels `arXiv:`, `arXiv`, `doi:` and `DOI`, with the label or the identifier in
backticks, emphasis or a table cell. A bare number cites nothing. `check` also
warns when a library's index cannot be read or parsed, when one with a citing
declaration fails verification against its checkout, and when the project's Lake
files cannot be used. None of these warnings changes the exit status, and a
library's sources are hashed only when one of its declarations cites a reached
source.

`audit` adds deterministic completeness,
provenance, coverage, checked-fact, and optional Lean-target checks. It is local
and read-only: it neither contacts network services nor writes findings back
into the blueprint. Pass `--json` for stable machine-readable output. A nonzero
exit status means the audit found at least one finding; [warnings](reference/validation-and-audit.md#warnings)
never change it. The machine-checkable
`coverage/README.md` contract contains one `Area | Coverage | Evidence` table
with `MAPPED`, `INVENTORIED`, `DECOMPOSED`, `DEFERRED`, or `OUT` dispositions.
`MAPPED` is nonterminal. `INVENTORIED` is the terminal disposition for exact
source accounting and must link to a `catalog: module` record, directly or
through a containing roadmap scope: `coverage-role-mismatch` names a link that
reaches none, and `unclassified-inventory` the first catalogs no such row
reaches. CI's `render` at an older `AUTOFORM_REF` rejects `INVENTORIED` as an
unknown disposition, so move the pin first. `DECOMPOSED` is reserved for
source-grounded declaration articles and links to them, directly or through a
containing roadmap scope. A row whose links reach nothing but catalogs is a
`coverage-role-mismatch`. Any other link that reaches no declaration leaf, such
as one to prose or to leaves marked `not_ready` that declare nothing yet, is a
`decomposed-without-declaration` [warning](reference/validation-and-audit.md#warnings), since earlier versions
accepted it. `DEFERRED` and `OUT` record an explicit later milestone or
exclusion. Audit JSON includes canonical rows, counts, and the
exact coverage source hash, while `publication.json` records aggregate counts
without duplicating the authored rows. The `counts` object always includes an
integer `INVENTORIED` key, zero when no row uses it.

One row carries one disposition, so represent both axes with distinct,
axis-qualified `Area` labels; these name source areas and are unrelated to an
article's `area:` field. For example, `Repository inventory / MathlibExt`
may be `INVENTORIED` while `Mathematical exposition / MathlibExt` remains
`MAPPED` and later becomes `DECOMPOSED`; duplicate exact area labels are
invalid. A broad inventory row may link a container and classify every catalog
below it while finer exposition rows evolve independently.

The contract is read as published Markdown and fails closed; the reasons are
in `coverage.py` and `markdown.py`:

- A table inside an HTML comment, a fenced block, or a four-space-indented
  block is documentation, not contract, and is not discovered. A closing fence
  carries nothing but its marker.
- A comment or code block written between rows, and every row-shaped line
  stranded below it, is reported rather than silently truncating the contract.
  A table that does not publish, such as one a paragraph runs straight into, is
  rejected, and a published contract table the audit does not recognise, such
  as one without outer pipes, is named.
- Only what a reader sees counts: a table, row, or cell hidden by a `hidden`
  attribute, its own or an ancestor's, is not published. Hiding is read from
  HTML, not CSS, so a stylesheet class or inline `display: none` still counts
  as published.
- A row whose removal would change the rest of the page, such as one holding an
  unclosed `<style>` or evidence with a raw `<table>`, is refused.
- Evidence must say something to a reader. A cell holding only a code span, a
  comment, emphasis, an HTML tag, an entity, an empty link such as
  `[ ](notes.md)`, or text a browser hides is rejected, and so is evidence that
  is nothing but `TODO`, `TBD`, `pending`, `placeholder`, or `unknown`, or opens
  with one as a marker, such as `TODO: choose a milestone`. "Pending Mathlib PR
  1234" names something a reader can check and passes.
- `INVENTORIED` and `DECOMPOSED` evidence must contain at least one complete
  inline link to an existing roadmap article, and every linked scope must
  contain the role the row claims: a module inventory for `INVENTORIED`, or a
  declaration-bearing leaf for `DECOMPOSED`. Audit reports a row that does not,
  and `render` warns. Every local link must resolve, fragments included, and a
  link missing its closing parenthesis does not count. Fragments are checked
  against the heading IDs Python-Markdown produces with the extensions the
  generated `mkdocs.yml` enables.

### What coverage completeness does and does not claim

`coverage.complete` in audit and `publication.json` means exactly one thing:
every row the author declared has reached a terminal disposition, so no row is
still `MAPPED`. It is a statement about the contract, not a measurement of the
project. Terminal dispositions close different questions: `INVENTORIED` closes
exact source accounting, while `DECOMPOSED` says the area has source-grounded
declaration articles. One does not imply the other.

It does **not** claim that the declared rows cover the source exhaustively, and
it says nothing about whether the linked roadmap articles are formalized or
proved. A project that declares one narrow area and disposes of it reports
`complete` while most of its source remains undeclared. Exhaustiveness is an
authoring judgement that no local check can make.

Module inventory counts are reported separately from formalization-target
completion. The target denominator, readiness count, declaration-kind totals,
and the progress-state breakdowns in the book and in `autoform check` use
non-container articles carrying `declaration`; a `catalog: module` record
counts toward none of them. A scope's status ring and item count, and the
legend beside each dependency map, also count a leaf marked `not_ready` that
declares nothing yet, so deferred work holds its scope open. All three also
count every catalog, under a neutral status: `inventory checked` once the
catalog is fully proved, which records inspection rather than a completed
result, and `inventory pending` until then, whatever its derived state. Neither
status changes a scope's rolled-up status or completion, though a target that
depends on a catalog waits for it like any prerequisite.

The generated `blueprint-pages.yml` deploys only a commit that the generated
`autoform verify` workflow passed on a push to `main`. It runs when that
workflow completes, checks that the run is the project's own
`.github/workflows/autoform-verify.yml` by file, not a workflow that only shares
its name, checks out the run's exact commit, and renders code links at it with
`--ref`. A failed verification deploys nothing, so the last verified site stays
up while `main` is red. Pull requests and manual runs build the site to check
it and never deploy, and they cannot cancel a deploy waiting in its
concurrency group.

Projects scaffolded before this rule keep a workflow that deploys every push to
`main`, since `init` leaves existing files alone and `--force` also rewrites
`README.md`, `mkdocs.yml` and the blueprint READMEs. To switch, delete
`.github/workflows/blueprint-pages.yml` and run `autoform init` again, which
writes only missing files. No pin has to move: `render --ref` exists at every
pin since 0.5.0, so the new file's `AUTOFORM_REF` may be set back to the
project's own.

Since a manual run never deploys, redeploy by re-running the Pages run that the
newest successful verify run on `main` started. A re-run keeps its original
event and so deploys the same commit. By the same rule, re-running an older
verify run, or its Pages run, deploys that older commit, which stays up until
the next deploy.

Publication and audit are deliberately different gates. The generated
`blueprint-pages.yml` gates on `check` and `render`, and runs `audit` after
`check` only as a report: the step lists every finding in the run's log, or
`OK: roadmap audit passed`, and `continue-on-error` keeps a finding from failing
the build or stopping a deploy. An invalid coverage contract fails `render`
before any output is written, but a valid contract with `MAPPED` rows publishes
normally even though `audit` reports each one as a `declared-coverage-gap`; a
freshly scaffolded project's first run lists one, for the template's row. That
is intended: a roadmap is published while it is still being decomposed, and the
published `coverage.complete: false` is how a reader sees that. Coverage-role
issues take the same path: `render` prints each one as a warning and publishes,
and `audit` reports it. A project scaffolded before the report step can add it
after `check`:

```yaml
      - name: Audit the roadmap (report only)
        continue-on-error: true
        run: >-
          uvx --from "git+${AUTOFORM_SOURCE}@${AUTOFORM_REF}"
          autoform audit blueprint --lean-root .
```

Run `autoform audit` without `continue-on-error` in your own CI when you want
mapped rows or role findings to block a merge.

Extract what a reader must trust for each formalized statement:

```bash
autoform skeleton blueprint --lean-root .
autoform skeleton blueprint --lean-root . --node chapter/main-result
autoform skeleton blueprint --lean-root . --output skeleton.json --packets review-packets --passages review-passages
```

A theorem means what its statement means. The skeleton of a `lean:`
declaration is the reading list a person needs to agree that the Lean says what
the article claims: the elaborated signature, then every project declaration
the *statement* rests on, transitively, quoted from the sources in dependency
order. A definition contributes its body as well as its type, because the body
is part of its meaning; a theorem met along the way contributes only its type
to the packet. Proof bodies are never emitted. Lean's axiom analysis does
inspect proof metadata, so changing a proof can change the reported trust
context. The proof beneath a skeleton may be orders of magnitude longer, and it
is the kernel's to check, not the reader's. Each skeleton also reports the
axioms the declaration finally rests on, so a `sorry` shows up as `sorryAx`
beside the statement, and the
non-core constants it assumes from Mathlib or another dependency, listed by
name so a reader can see that a statement uses the library's notion of a limit
rather than a homemade one.

The closure is computed from elaborated terms, which is why this is the one
command that runs Lean: for each module that declares a selected `lean:`
target it runs a small probe with `lake env lean` against the built project.
A declaration's packet reads as it does to a file that imports its module:
it has the module's global notation, instances, and attributes, including any
the module declares after the declaration, but not its `local notation`, local
instances, or the `open` and `set_option` commands in effect at the
declaration. Before any probe, Lake must confirm, without
rebuilding, that every probed module matches its exact source inputs; a
missing `lake-manifest.json`, stale artifacts, or a source tree that changes
during extraction makes the command fail. That check rewrites Lake's `.hash`
files, so the project's `.lake` directory must be writable. The probe's helper
module `autoform-skeleton-helper` and its `AutoformSkeleton` namespace are
reserved: a project or dependency module, or one on `LEAN_PATH`, that takes
one makes the probes that import it fail.

Names outside the project are the trusted base and are not expanded.
Generated companions, such as constructors, projections, recursors, and
matchers, are folded onto the declaration the reader sees, so a structure
appears once, as its `structure` block; internal helpers with no source of
their own are marked `-- source not shown`. A `partial def` anywhere in a
declaration's trusted closure is refused, because its kernel face is an opaque
constant, and so is an ordinary declaration without its own source, such as
one a metaprogram adds under an existing name. A `lean:` name is unresolved
when it is absent from the sources or from the built environment, when Lean
declares it in another module than the one whose source the lexical index
finds it in, when the sources define it more than once with no single
declaration chosen by the rules under [Validation](reference/validation-and-audit.md#validation), when it
reaches a refused declaration, or when its probe fails on its own (a nonzero
exit, a signal, a timeout, or malformed or ambiguous records), in which case
the reason quotes Lean's output. An unresolved name affects only its article: other articles still
extract, the command exits nonzero, and it writes nothing into the vault. The
output and material limits apply to a whole probe, so a declaration that
resolves when selected alone can be unresolved beside its module's other
targets; a declaration that resolves has the same hash under any selection.
A missing `lake`, a failed freshness check or helper build, a dependency that
hides a toolchain library, or a blueprint or source tree that changes during
extraction still stops the whole command.
`--output` records the `autoform-skeleton/v5` report, which contains no
timestamp or absolute path, for a later render or review to consume. The
report identifies the exact blueprint, by a hash of every article's bytes and
of the passage each article cites, its complete target set, and whether
the extraction covered all targets or an explicit `--node` selection; a
report whose selection, articles, and unresolved declarations disagree can be
neither built nor loaded. Review evidence is derived only from a report that
selects every article and whose targets are the blueprint's `lean:` names. It
quotes each trusted definition's source and records theorem
dependencies by elaborated signature, so it stands on its own without ever
copying a theorem proof.

Run skeleton extraction only in a trusted checkout or an operating-system
sandbox. Lake evaluates `lakefile.lean`, and the generated probe imports project
code whose initializers, macros, and metaprograms may perform arbitrary IO and
can forge probe output. The timeout and output cap bound the direct batch
command; on POSIX, Autoform also terminates its process group, for every
probe, on every failure and on interruption. The Lake freshness check, the
helper's build, and each probe have their own 600-second budget;
`--timeout SECONDS` sets the helper's and each probe's, which a large
project may need. Probes run in parallel, at most eight at a time. These
limits are resource controls, not a security or authenticity boundary.

Every skeleton carries a full SHA-256 **drift hash** over the canonical
elaborated expressions of the root, every trusted declaration, each direct
external assumption, and each axiom, together with the dependency edges, the
Lean version, and the compiled `.olean` identities of the external boundary.
Local source spelling and comments do not enter it, while macro expansion,
synthesized instance bodies, types, and definition bodies do; proof axioms,
toolchain changes, and unrelated edits in an external module or its imports
may also rotate it. A dependency library rooted at `Init`, `Lean`, or `Std` hides the
toolchain's copy from the probe, so extraction stops with an error. An article
with several `lean:` names has one hash over all of them, printed as the
article skeleton; if any of those names is unresolved, the report records the
article's hash and review hash as null. It compares reports across builds; it
is not a stable statement identifier, reviewer authentication, or an approval
key.

Each skeleton also carries a **statement hash** over the same material without
the axioms and what only they reach. The probe closes over the statement first
and then over the axioms' types, and the report records both: `trusted`,
`assumed`, and `boundary_modules` hold the whole closure, `statement_assumed`
and `statement_boundary_modules` the part the statement reaches, and the
statement's trusted declarations are those the root's `depends` reach. The
packet shows only the statement's part, with no `-- axioms:` line. So editing
only a theorem's proof, from `sorry` to a proof, or to one that starts or stops
using an axiom, changes the drift hash and the reported axioms but not the
statement hash, and the packet only when it decides whether an equation-style
statement can be cut (below). A proof inside a definition the statement rests
on is part of that definition's meaning, so editing it changes both hashes, as
does any other edit to what the statement means; a spelling-only edit changes
only the packet.

Reports and packet manifests also carry an evidence hash over the exact packet
shown to a reviewer. It identifies those bytes but does not authenticate who
reviewed them. An article review hash additionally binds the joint packet to the
cited passage, its locator, and the drift hash, so a review recorded against it
does not survive a change of meaning that leaves the packet text unchanged. All
three are advisory provenance checksums when candidate code controls the
checkout. Human approval records one `review_approved` hash over the complete
review surface: the article's title and its statement as the site's statement
box shows it, cited passage and locator, the exact joint packet and each
declaration's packet, the project TeX macros the statement uses, and each
validated read-back's model and testimony, so changing any of them invalidates
it, while a proof edit, or a Lean or Mathlib bump that leaves the packets
unchanged, changes none of them.

A read-back is an independent agent's mathematical-English account of one
declaration packet. The coordinator gives that agent only an opaque packet and
the read-back instructions, then records the returned testimony through the
CLI. Cards live at `blueprint/readbacks/<article_id>/<encoded-declaration>.md`;
the durable `article_id` keeps testimony attached when an article moves, while
the encoded filename avoids platform-specific Lean-name collisions, and before
its first dot never spells a name Windows keeps for a device, as `Aux.lemma`
would. Each versioned card contains the exact packet in a Lean block, its
evidence hash under `packet:`, the declaration's statement hash under
`statement:`, which a proof edit leaves unchanged, a model label, and the
testimony in a text block. A card testifies about its packet: the statement
hash is kept as a record only, since it covers the Lean version, which a bump
can change while the packet stays the same.
The loader rejects missing or unknown fields, altered packets, identity
mismatches, cards not in canonical form, and malformed or empty testimony.
`model:` remains a label supplied by the coordinator, not authenticated
provenance.

Testimony is plain text with TeX formulas between dollar signs. GitHub and a
Markdown viewer of the vault show it as typed, in the card's text block, and
`render --review` shows it escaped in the statement's *Review* panel, but
copies no file under `readbacks/` to the site. Its formulas are the pieces
`readback.split_testimony` finds, so `\$` is a dollar sign that opens nothing.
The rules are in the read-back guide
`skills/human-review/references/readback.md`, and `readback.py` applies them.
Testimony must show a reader everything it says, so invisible and reordering
characters, and combining marks stacked over the lines around or with nothing
to sit on, are refused by name. A write also refuses code points its Python's
Unicode data leaves unassigned; loading does not, so a filed card loads the
same under every Python. Testimony must show at least one letter or digit, and
fit in 32 KiB and 500 lines, so every check is a linear scan of a bounded text.
A formula never makes testimony invalid. `readback.formula_problems` says
whether one can be typeset: it must use TeX from a flat allowlist, the notation
statements need out of MathJax 3.2.2's base and ams packages, with no spacing,
phantom, colour, box, size, or macro command, and hold nothing that shows as a
blank, such as a run of spaces in `\text`, an empty `\frac` or script, or two
empty cells one after the other. `readback.typesetting_warnings` names each
formula that cannot be, which the site shows as typed, dollar signs and all,
while it typesets the rest, and render warns about each.

Cards are read without following links, so a linked card or directory is
skipped. A card file holds at most 4 MiB, no file is read more than one byte
past that, and a card's frontmatter is read from its first 32 lines. A file at
a card path that is larger, is not UTF-8, or cannot be read, and a directory or
FIFO there, is reported as an invalid card, not skipped, even when the
declaration's name is too long for the filename to spell. A card is attributed
to the declaration its path names, so one that records another declaration, or
whose `.md` is in another case, is reported as that declaration's invalid card.
A directory under `readbacks/` that cannot be listed stops loading with an
error naming it. Writes name a card by the hash of its bytes, so a card that is
not UTF-8 is replaced like any other; one over the limit must be removed by
hand.

A write refuses a link on the way to the card directory and takes the
directory's `flock`, so Autoform's writes to one directory happen one at a
time; a write that cannot get the lock within ten seconds gives up, and a
writer that dies releases it. An optional expected-card hash makes updates
compare-and-swap: different content replaces a card only when it names that
card's hash, and a card that names a hash conflicts with a missing card.
Filing content identical to the current card writes nothing in its directory,
so it succeeds even in a read-only one. Otherwise the write stages the card in a
`.autoform-readback-*.tmp` file beside it, flushes it, and renames it over the
card in one step, so the card's name holds either the old complete card
(nothing, for a first card) or the new one. A failure or interrupt before the
rename removes the staging file; a crash, SIGTERM, or SIGKILL can leave it.
The loader never reads it as a card, and the blueprint `.gitignore` that
`autoform init` writes for a new project ignores it. The card committed to Git
is the durable copy: a crash just after a write can lose it, and filing it
again restores it.
The contract covers Autoform's writers only: an editor's save, or a directory
moved, during a write is not detected, so edit cards while no write is
running. A write also gives `readbacks/` a `.gitattributes` of `* -text` if
it has none, so Git leaves card line ends alone: Git for Windows checks text out
with CRLF line ends by default, and a card with them is invalid. Writing needs
`flock`, which Linux and macOS provide; elsewhere, including Windows, a write
is refused before anything is created, and cards can still be loaded. Git for
Windows checks out a path over 260 characters, which a long declaration name
makes, only with `core.longpaths` set.

`--packets DIR` writes one comment-stripped packet per skeleton, with a
manifest mapping packets to articles and hashes. Their file names spell each
article and declaration, so a blind auditor is given the packets
`review prepare` writes instead, named by hash. The destination must be empty
or carry Autoform's packet manifest; each run replaces the complete managed
tree, so removed declarations cannot leave stale packets behind. A concurrent
change detected before commit aborts publication instead of being overwritten.
If the isolated old tree changes later, Autoform preserves it at a reported
recovery path instead of deleting it.
Packet and passage manifests use their v2 schemas; v1 output trees are still
recognized and replaced during an upgrade.

An unresolved selected declaration makes the report incomplete and prevents
all packet and passage publication; `--output` alone can still record that
diagnostic report. Output destinations must be disjoint and non-symlinked, and
their parent filesystems must support the temporary files, hard links, and
atomic renames used for guarded replacement.

A packet holds only what a blind auditor may see: the signature, the same
signature printed in Lean's raw expression form, the canonical kernel material,
the statement as written, and the source of every project definition its statement
rests on, with every comment and docstring the probe can identify removed, so that a
reader who is asked what the Lean literally asserts cannot read the author's
intent into it. Lean's parser locates those comments, parsing each source in
its root module's environment. A source it cannot parse there, such as a body
that uses `local notation`, is withheld if it may hold a comment, and so is one
holding a non-builtin token with `--` or `/-` that no import of its own module
made globally active; the declaration's signatures and kernel material stay in
the packet, and the article is not unresolved. A `local` token, or a token the
file had in scope differently from the probe, can make the probe show code as a
comment or a comment as code; `skeleton.py` lists these cases.

Every item's signature is also printed raw, bypassing project notation,
unexpanders, and custom delaborators, so an `infixl " + " => HMul.hMul` cannot
make a product read as a sum in any signature. Source text is not notation-proof:
a definition's body, including a definition root's own source, is shown as
written, where such notation still applies. For those, and for structures and
generated companions, only the canonical kernel material, shown for every item,
states the meaning without notation.

Each theorem's packet also carries the statement *as written*, cut before a
`:=` value or a structure-style `where` value by Lean's parser with its
enclosing namespaces and the file's opened namespaces in scope. A proof Lean
cannot parse, for example one using `local notation`, does not stop those cuts.
Its comments are found by parsing the statement alone, with `:= sorry` as its
value, so editing only the proof changes neither the statement shown nor what
is stripped from it, unless it makes an equation-style form parse or stop
parsing outside its file.
The statement sits beside the elaborated signature: the printed form shows
binders that `variable` and `include` inject and the type every cast lands in;
the written form shows what the pretty-printer elides. Equation-style forms
that cannot be parsed outside their file are marked `-- source not shown`.

A statement's source passage can travel with it. A `## Sources` link to a
non-Markdown file inside the blueprint with a `#L<start>-L<end>` fragment, for
example `../../../sources/lebl-ra/ch-real-nums.tex#L693-L714`, names the exact
text the statement came from. External URLs are skipped, and so is a link with
such a fragment that names a regular Markdown file in the blueprint, in any
letter case: that is a note. Any other link with such a fragment is a locator,
whatever its suffix. A first local locator that names no text leaves the
article's declarations unresolved while the other articles still extract. It
names no text when it points outside the blueprint; names an invalid path, a
symlink loop, a link that cannot be read, or a missing, unreadable, oversized
or non-regular file; or names non-UTF-8 text or no lines of its file.
`--passages DIR` writes those passages beside the packets, one per article, in
a separate, disjoint managed directory. It requires `--packets`. Each article
directory also holds `article.lean`, the joint packet of every declaration the
article names, because a source theorem is often formalized by several
declarations together and each alone is honestly incomplete. A judge of
faithfulness is given the article packet and its passage; an auditor asked what
one declaration asserts is given that declaration's packet alone.

Review a formalized statement with three commands, then publish the review:

```bash
autoform review prepare blueprint --lean-root . --packets review-packets
autoform review record blueprint --packets review-packets \
  --article-id af_0123456789abcdef01234567 --declaration Ns.result \
  --testimony read-back.txt --model muse-spark-1.1
autoform review check blueprint --lean-root .
autoform render blueprint --lean-root . --review
```

`review prepare` extracts every Lean-mapped article from the current built tree
and writes one blind packet per declaration under `blind/`, named by the hash
of its bytes, so that, unlike a `skeleton --packets` file, its name tells its
reader nothing, with a manifest that maps each to its article and hashes for
the coordinator. Every Lean-mapped review article must be a declaration-sized
leaf; a module catalog, whose `lean:` names inventory a module rather than
state one result, is not under review. An article marked `origin: cited` must
link to an in-vault, non-Markdown source snapshot with an exact
`#L<start>-L<end>` range, and no article may cite blank lines; preparation
refuses a citation it cannot put before the reviewer.

`review record` runs no Lean. It reads the packet `review prepare` wrote for
the article and declaration and refuses one whose bytes do not match its hash,
a packet or testimony that is not a regular file (a FIFO is refused unread), an
`article_id` the blueprint no longer has, and testimony the read-back rules
refuse; then it files the card under its compare-and-swap, and warns about each
formula a site would show as typed instead of typesetting, and why. When a card
is already there with different content, the record must name its hash with
`--expected-card-hash`. Whether the card is current is for `review check` to
judge: a card whose packet is not the declaration's current packet is reported
invalid there, and no approval can be computed from it, so prepare again and
record the new packet.

`review check` derives its evidence from its own extraction, never from a
committed file, and fails until every Lean-mapped article has current cards and
a `review_approved` that matches its review hash, which it prints. A card and
an approval each bind each declaration's packet, the bytes the reviewer read,
not its statement hash, which covers the Lean version: a Lean or Mathlib bump
that leaves a statement's packet unchanged keeps its card and its approval. The
statement hash a card records is not compared. An approval also binds the
project TeX macros the statement uses, from `blueprint/tex-macros.json`,
directly or through another macro, since the site typesets the statement with
them: a change to one marks stale the approvals of the statements that use it,
and leaves the others current. It judges one state of the blueprint: it reads
the articles, the sources they cite, and the cards before Lean runs and cuts
every passage it compares from those bytes. When the extraction ends, it
requires the extraction to have seen the same articles and sources and the
cards to be unchanged, and it cuts every statement it compares from its article
read once more, which must still have the bytes it read first. An edit that
breaks any of these comparisons fails the check with `review-snapshot-changed`;
run it again once the blueprint is idle. These are comparisons, not a lock: a
change restored between them goes unseen, and an edit after the last does not
affect a verdict already reached. `tex-macros.json` is read once, after Lean,
and compared with nothing. `review prepare`, `review check`, and
`render --review` accept the same `--timeout SECONDS` probe override as
`skeleton`.

`render --review` makes the same check, from one extraction of its own, and
puts a *Review* disclosure under every formalized statement: the approval state,
the review hash to approve, as a row that can be selected, the cited passage,
and for each declaration its read-back card, marked current, invalid with the
reasons, or missing, and the exact packet that was hashed. The packet is all
the approval binds of a declaration, so the rows beside it mark its statement
hash, and what it assumes and its axioms, proof included, as not bound. Render
runs the extraction once its output, the vault it captured, the graph, the
coverage contract and the Lean sources pass their checks, so a render they
refuse costs no Lean. It judges the cards and the `tex-macros.json` it
captured, the bytes `publication.json` hashes, and the articles and cited
passages it publishes must be the ones the extraction read: an edit to one
between the capture and the end of the extraction fails it with
`review-snapshot-changed`. A card's formulas are typeset only when
`readback.formula_problems` accepts them; any other is shown as typed, and
render warns about it with its exit status unchanged. A passage cut from a file
the site leaves out, such as a script, a file under `readbacks/`, or
`atlas.json`, is refused with `review-source-unpublished`. A folder whose
README says `published: false` is reviewed with the rest of the vault, and its
articles, which render leaves out, get no disclosure and no warning; nor does a
module catalog, which is not under review. The panels stay out of the site's
search. `--timeout` is accepted only with `--review`, and when the review is
refused, render prints the reasons on stdout and exits 1, as its other refusals
do.

The gate is opt-in for every project: a project turns it on by committing
`blueprint/.autoform-review` holding `autoform-review-policy/v1` and a line
end, and `autoform init` never writes that marker, neither for a new project
nor on repair. With the marker, the generated CI runs `review check` after the
Lean build, without turning advisory roadmap or coverage findings into merge
blockers. Without it, cards or `review_approved` assertions fail CI instead of
going unchecked, and once it is committed, deleting every card cannot turn the
check off.

`review_approved` records unchanged evidence, not who approved it:
`review check` prints the expected hash, so anyone, an agent included, can
paste it. An approval is current when `review_approved` equals the current
review hash, which `review check` enforces, and a current approval is labelled
self-approved wherever it is shown.

`review_approved` is thus a drift checksum, not an authorization.
Authorization has to come from repository policy: CODEOWNERS gives `blueprint/`
a code owner (the `/blueprint/` rule in `CODEOWNERS.autoform.example`), and a
ruleset on the default branch requires code-owner review, dismisses stale
approvals and requires approval of the most recent push. Without that policy,
a current approval authorizes nothing.

When `--output`, `--packets`, and `--passages` are combined, all three outputs
are staged before publication and a failed commit restores the previous set.
This is failure atomicity, not simultaneous visibility across paths: each
rename is atomic, but a reader opening several outputs during publication can
briefly observe different generations.

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
