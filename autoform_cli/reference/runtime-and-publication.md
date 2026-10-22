# Autoform runtime and publication

## Local runtime doctor

Use the runtime projection and roadmap audit together without contacting any
external service:

```bash
autoform doctor . --lean-root .
autoform doctor blueprint --json
```

The doctor reports six ordered checks: blueprint resolution, runtime schema,
graph counts, reference invariants, roadmap audit, and optional local Lean
targets. It exits zero only when every required check passes. Omitting
`--lean-root` records an explicit advisory pass; supplying it performs only a
lexical local-source check, not a Lean build, kernel check, or proof-honesty
review. Only the `lean targets` check reads Lean sources, once. It holds every
finding that needs the Lean root, including `node-too-large`, and an unusable
Lean root or unreadable source fails only that check. The bundled example
intentionally exits nonzero while its declared coverage still holds `MAPPED`
rows.

This command is strictly read-only and local. It does not invoke Git, GitHub,
subprocesses, network services, claims, renderers, or dashboards, and it writes
no file.

## Runtime contract

`autoform_cli.runtime` projects the canonical Markdown graph into the versioned,
deeply immutable in-memory schema `autoform-runtime/v4`. Its declared authority
is `markdown-articles`: the adapter copies hierarchy, typed statement and proof
dependencies, authored assertions, derived progress, provenance, and optional
local Lean source locations, but it provides no persistence or write API. A
source target that is neither an http(s) link nor a path inside the blueprint,
and a `mathlib_file` that is not a portable relative path, are left out rather
than refused. `check` fails on a local path outside the blueprint and warns
about the rest.
`RuntimeGraph.as_dict()` and `to_json()` are deterministic compatibility
snapshots for consumers, not an authored or generated graph file. Autoform never
creates, synchronizes, or treats `graph.json` as an authority.

Every article remains in the runtime view so consumers can preserve the book's
arbitrary containment hierarchy. A node is dispatchable only when it is both a
formalizable article and a leaf; narrative containers and prose-only leaves are
never proof work units. Module inventories are likewise non-formalizable,
non-dispatchable source records. The source revision hashes exact roadmap
article paths and bytes, excluding timestamps, absolute paths, Git state, and
operational state. Optional Lean locations come from a local lexical scan and do
not by themselves establish compilation or proof correctness.

Schema v4 adds a nullable catalog discriminator for non-dispatchable module
inventories. It retains v3's optional durable `article_id` metadata beside the
graph's path-derived `id`, project `open_statements` policy,
`statement_retracted` assertions, and each status's `assumes` and `waiting_on`
fields. Temporary claims and local dashboard hooks may fall back to the path ID,
but durable execution records and routes must require `article_id` until the
path-move migration is complete. Operational state remains private and excluded
from runtime snapshots and publication.

Projection fails when an article's bytes no longer match the digest recorded
when the graph was loaded, so a source revision never labels node data parsed
from older bytes. A hand-built node without a digest makes no snapshot claim:
its `source_sha256` stays null and the revision covers whatever bytes its
article holds at projection time.

## Publication contract

`autoform render` publishes the book, derived progress, and one dependency
explorer as bounded project, chapter, and nested-scope projections. The legacy
full route is a project-scale compatibility shell backed by a layout-free global
search index, never an all-repository node cloud. Rendering never reads a
`graph.json` or an operational queue. Hidden files and directories, including
`.implementation-notes`, are omitted, while a `.autoform` directory and
symlinks, credentials, logs, provider state, and agent/task state outside hidden
directories cause the render to fail rather than silently leak them. Source and
output directories must be disjoint. A blueprint path that differs only in case
from one render writes (`SUMMARY.md`, `dependencies.json`, `dependencies.md`,
`structure.md`, `publication.json`, `assets/`, `dependencies/`, `javascripts/`,
`stylesheets/`, and the generated stylesheet, scripts and logo inside them) is
refused, as are two blueprint paths that differ only in case or Unicode form,
because they would collide on a case-insensitive filesystem. A blueprint file at
exactly `dependencies.json` or `javascripts/blueprint-dag.js` is left out of the
site with a warning, because the explorer writes its own file there.

Every render writes `publication.json` with blueprint and Lean-source hashes
(the Lean-source hash is empty when render reads no Lean sources, as on native
Windows), Git ref, article and dependency counts, the site's file inventory, and
available views. It contains no timestamp or absolute path, so identical inputs
produce identical output files. Render reads the blueprint and the Lean sources
once each and derives every page, link and hash from those bytes; an edit saved
during a render waits for the next one, and until then the dashboard reports the
built site as stale. Under `--review`, the extraction reads both again, and an
article or cited passage edited between the capture and the end of the
extraction fails the render instead (see `render --review` under statement
review); a later edit waits for the next one. The vault's hidden implementation notes are read in place
only to validate them. Repository links appear only when the Lean bytes match
one locally available Git commit, recorded by its full object ID; a clean
checkout that Git converts on checkout still matches. Otherwise the render stays
local, keeps source notes in the site, records no Git ref, and warns with the
first mismatch. Links into the blueprint (an article's Markdown source, a source
note) also need the blueprint's bytes in that commit. When they differ, render
keeps the code links, keeps source notes in the site instead of linking to them,
and warns with the first mismatch; a blueprint outside the repository, or in a
submodule or other checkout nested in it, gets the same result without a
warning. When render reads no Lean file (native Windows, or a project with no
`.lean` file yet), it records the Git ref only if the blueprint matches it.

The manifest's schema is `autoform-publication/v3`. It records what v2
records, but the site holds the shared explorer's JSON projections and script
in place of v2's Mermaid dependency maps, and the blueprint hash is taken under
a label of its own, so no v2 `source_revision` equals a v3 one. The dashboard
accepts only a v3 site and reports an older one as stale until render replaces
it.

The site is built and synced in a hidden `.autoform-publication-*` directory
beside the output, then swapped in with one atomic exchange (`renamex_np` on
macOS, `renameat2` on Linux); renders committing into the same parent directory
take turns when it can be locked. On filesystems without the exchange (NFS, SMB,
9p or WSL2 `/mnt/c`, exFAT, sshfs) the previous site is first renamed to
`.autoform-publication-backup-<name>`; if render dies between the two renames,
the next render moves it back before anything else. Render replaces only an
empty directory or a complete `autoform-publication/v2` or v3 site whose files
match its inventory (macOS metadata files, `.DS_Store` and `._*`, are ignored
in both), and refuses anything else, including a legacy v1 output, which you
remove once by hand. A failed or refused render leaves the output as it was. A
render killed mid-way can leave a `.autoform-publication-*` directory beside the
output (the repository root for `--output site-src`); render never indexes it
as Lean source and the setup ignore rules cover it, but it may hold the previous
site, so inspect it before deleting it. (On macOS `fsync` does not flush the
drive's cache, so a power loss can still lose the newest site.) Native Windows
has no directory-descriptor traversal. There render reads the blueprint and the
output as two pathname captures that must agree, commits through the backup
swap without a lock, and reads the Lean sources only for an explicit
`--lean-root`, which then fails closed. Without one it publishes no code
links; when a published statement names a `lean:` declaration it warns, and
`--require-declarations` makes it exit 1.

Check the site MkDocs builds from render's output for what the build broke:

```bash
autoform site check site --source site-src
```

`mkdocs build --strict` never checks a link written as raw HTML, as render
writes card references, the structure page and the landing page's Next up card,
and it logs a broken Markdown anchor only at info level. `site check` reads
every HTML page of the built site and reports, as warnings, an internal link or
asset whose target the site does not contain, a fragment that matches no `id`
on its target page, a link that is not a valid URL, and, with `--source`, each
statement card that render wrote into a source page but the page built from it
lacks. A link with a scheme or a network location, or a path from the site
root, depends on where the site is served and is not checked, and neither is a
fragment of `name=value` pairs, such as the dependency explorer's `#node=`,
which the page's script reads. The exit status is 0 whatever it finds; it is 1
only when the site or the source is not a directory.
