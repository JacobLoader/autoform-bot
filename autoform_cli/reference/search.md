# Autoform search

## Search contract

`autoform search` is a read-only projection of Markdown: it writes nothing,
builds no index, and starts no process. The contract is the JSON shape, the
exit codes, and the rule that an article is a hit only when every term of the
query occurs in it, as a substring of one of its fields; terms may sit in
different fields. How the query is cut into terms, folded, shortened, and
ranked may change, and `search.py` describes it; `terms` in the JSON shows what was
searched. Case, width, accents, typographic dashes and quotes, and invisible
characters do not matter. The fields, best first:

- `title`, without its Markdown markup;
- `lean`, the last component of each `lean:` and `mathlib_declaration` name, or
  a term that is the whole name or its last components;
- `node_id`, the last component of the path ID;
- `statement_text`, as the site publishes it, without headings, code blocks,
  diagrams, comments, and hidden elements; inline code and mathematics count,
  and published mathematics is delimited `\(...\)`, so search for a formula's
  content;
- `ancestors`, the titles of containing articles below the roadmap root;
- `qualified_names`, the path ID and Lean names in full, which is where a
  namespace alone matches.

Other frontmatter and the sections after the statement are not searched. There
is no phrase, synonym, or prefix search, and one absent term means no hit:
`map` matches `roadmap`, `unambiguous` does not match `non-ambiguous`, a symbol
such as `ℝ` folds to its plain letter, and a one-letter term matches nearly
every article. Only the query is shortened, so
`indices` does not find `index`. Superscript and subscript digits fold to the
digit while `^` and `_` stay, so `S^1` and `S¹`, or `H_0` and `H₀`, do not find
each other. A name with a dot, underscore, or digit is searched exactly. Query
with a few distinctive words or one exact Lean name,
search each spelling, and retry with fewer words before treating a result as
new. Hits sort by the best field any term matched, and last by node ID.

`--state` takes exact derived state keys, which `autoform search --help` lists
(`proved` does not include `fully_proved`), and `--declaration` frontmatter
`declaration` kinds, each repeatable; they apply before `total_matches` is
counted and `--limit` (default 20) after. `--declaration def` also keeps
`noncomputable def`, but not `definition`. When no article in the blueprint
declares any of the requested kinds, the search is refused with exit code 2 and
the kinds in use, rather than answered with no hits. A requested kind that no
article declares, beside one that some article does, adds nothing, and a note
on standard error names it.

`--json` writes `autoform-search/v1`: `schema`, `source_revision`,
`open_statements`, `query`, `terms`, `filters` (`declaration` and `state`,
each a list), `limit`, `total_matches`, and
`hits`, with no timestamp and no path outside the project. A hit carries
`node_id`, `article_id`, `article_path`, `article_revision`, `title`,
`declaration`, `catalog` (`module` for a module inventory), `state`,
`statement_text` (the authored Markdown),
`lean_targets` (all of them), `mathlib`, `mathlib_declarations`,
`mathlib_file`, `source_targets` (as the article writes them, once each, minus
any that is neither an http(s) link nor a path inside the blueprint), `used_by`,
`used_by_count`, `shared_title`, and `matched_fields`; `article_id`,
`declaration`, `catalog`, and `mathlib_file` may be null. A Lean target has
`declaration`, `source_file` (relative to `--lean-root`), and `line`; the last
two are null without `--lean-root`, when the lexical scan does not find the
name, or when it finds several with none chosen (see Validation).
`used_by` holds the first ten dependents by node ID, through statement or
proof; `used_by_count` counts all. `shared_title` marks a title another article
repeats and is advisory. `matched_fields` lists, best first and once each, the
fields in which some term found its best match; it does not say which term.
No hit is `"hits":[]` with exit 0. Human output shortens the statement, omits
sources and dependent names, and is not a contract. It opens with how many
matches each list shows, the blueprint's and each library's, and puts each
hit's statement, or a library hit's signature, on the hit's first line, so
output cut short still gives every list's count and, for each hit it shows,
the statement or signature.

Search rereads each article it matches against and refuses, with exit 2, bytes
other than those the graph was built from, as it refuses a symlinked roadmap
entry. Each call reads every such article and renders its statement, so its
cost grows with the blueprint.

### Searching a library the project depends on

`--library NAME` (repeatable) also searches the index a locked Lake package
publishes, and needs `--lean-root`, which names the Lake project.
For example,
`autoform search . "separating hyperplane" --lean-root . --library atlas`.
`autoform library list ROOT` reports each package in `lake-manifest.json`
with its type, locked revision, and whether search would accept it, and for a
package it would not, why. Text shows one row per package: name, type, the
first 12 characters of the revision, and `usable` or `not usable: REASON`.
`--json` emits `autoform-library-list/v1`, `schema` and `packages`, each with
`name`, `type`, `revision`, `index` (whether the checkout holds an index
file), `usable`, and `reason` (`null` when usable).
Neither command starts a process or writes a file.
A search without `--library` whose project locks a package with an index file
adds one `note:` line on stderr naming the package and the flags that search
it; stdout, the JSON and the exit status are unchanged. The note only checks
that the file exists, so `library list` still decides whether it is usable.

The index is the file `autoform-library-index.jsonl` at the package root, or
the file given as `--library NAME=PATH`. Its format,
`autoform-library-index/v0`, is provisional and may change without notice
until it is promoted to `v1`.

Before an index is used, search checks by reading files that the checkout is
at the locked revision, that the index's toolchain and direct dependencies are
the ones the checkout pins, that the Lean files under the indexed directories
are exactly the indexed modules with the recorded digests, and that the index
as a whole is one generation. A package that is not locked, not checked out, a
path dependency, replaced by `.lake/package-overrides.json`, without an index,
or failing a check is refused, as is any library of a project whose `.lake` or
packages directory is a symbolic link, with exit 2 and a message that begins
`library NAME:`. One refused library refuses the whole call, blueprint hits
included, since a partial answer would read as "this result is new". A
package replaced with `lake --packages=` is not detected. Neither is an edit
to the index file that leaves each module's `name`, `source_file`, and `sha256`
and the header's toolchain, dependencies, and source directories alone: a
declaration record, a module's `module_doc` or `module_system`, or the
header's `generator`, `probe`, or `package`.

A declaration matches when every term occurs in its last name component
(`lean`), docstring, module header (`module_doc`), full name (also without
`_root_.` and `«»`) or module (`qualified_names`), the constants in its type
(`mentions`), or its keyword (`kind`), ranked in that order, with `complete`
before `wanted` among otherwise equal hits. `--state` and `--declaration` apply
to articles only; `--limit` applies to each list.

With `--library` the JSON schema is `autoform-search/v2`: every
`autoform-search/v1` key keeps its meaning, and `libraries` lists, in the
order given, `name`, `revision`, `index_schema`, `generator`, `probe`,
`differences`, `total_matches`, and `hits`. A hit carries the declaration's
`name`, `kind`, `status`, `module`, `source_file`, `line`, `signature`,
`statement`, `docstring`, `mentions`, `auto_named`, `module_system`,
`matched_fields`, `module_doc` (the module header when it matched, otherwise
`null`), and `import`, the line that makes a `complete` declaration available
(`null` for a `wanted` one, which carries no proof). `module_system: false`
marks a file a Lean module file cannot import. `differences` lists the
library's toolchain and each direct dependency whose locked revision is not
the project's, as objects with `what` (`lean_toolchain` or `dependency`),
`name` (`null` for the toolchain), `library`, and `project` (`null` when the
project locks no such dependency or either side is a path dependency); it does
not say the library fails to build. Without
`--library` the output stays `autoform-search/v1`, byte for byte.

#### Publishing an index

`autoform library index ROOT` writes `autoform-library-index.jsonl` at the
package root of a built library. `--lib NAME` (repeatable) limits it to those
`lean_lib` targets; the default is every `lean_lib` of the package. The format
is `autoform-library-index/v0`. Only the source directories of those targets
are read. A target's `globs` select its modules as Lake does: `M` is one
module, `M.*` the module and its submodules, `M.+` its submodules only.

It is the only library command that runs Lean and Lake. It imports the
library's modules, so run it on a trusted checkout or in a sandbox. It does
not build: a missing or stale build exits 2 with the `lake build` command
for the indexed targets and the first module Lake found unbuilt, and the
freshness check rewrites Lake's `.hash` files, so `.lake` must be writable.
`--timeout SECONDS`, a positive number, bounds the probe. The index records
the Autoform version that wrote it, so the command refuses to run from an
Autoform that is not installed. The index is written whole or not at all; a
failed write says why and whether the previous index is unchanged.

A declaration is indexed when it is one a user wrote with a declaration
keyword, not a generated companion, an internal detail, or a `where` or
`let rec` helper; `library/declarations.py` gives the exact selection, the
`line`, and where a record's `statement` is cut, which never includes part of
the body. A declaration that rests on `sorry` or on an axiom other than
`propext`, `Quot.sound` and `Classical.choice` is left out, and the count is
written to standard error. A result declared with `theorem_wanted`,
`proof_wanted`, `def_wanted` or `instance_wanted` is indexed with status
`wanted`. A range the probe reports that is not in the source file means the
source is not the one the library was built from: the command exits 2 and
names the declaration and its module.

`--check` writes nothing. It exits 0 when the index at the root is current, 1
when it is stale, with the reason on standard error, and 2 when it cannot
tell. A package with no index is stale. A package root that does not exist,
an index that exists but cannot be read, and a missing or stale build are
cases where it cannot tell. Changed, new and missing source files are found
without running Lean.
Run it in the library's CI after the build, with the same `--lib` flags, and
pin the Autoform revision: the bytes of an index depend on it.

The generator is tested on Lean 4.34.1 and 4.35.0 only and is not supported on
Windows: it exits 2, before it runs Lean, when the package's `lean-toolchain` is
neither `leanprover/lean4:v4.34.1` nor `leanprover/lean4:v4.35.0`, nor a spelling
elan resolves to one of them, such as `v4.35.0`.
The index's `package` is the name in the package's `lake-manifest.json`, else in its
`lakefile.toml`, and the command exits 2 when neither gives one; the folder it
is checked out in never matters.
Module names must be ASCII identifiers. A Lean file under an indexed
directory that no indexed library builds is refused. So are two modules that
declare the same public name in two ways: Lean refuses to import both. A
theorem two modules state the same way is indexed once, under the first of
its modules in name order, with a warning on standard error naming the
modules; a wanted name is private to its module, so each module's copy is
indexed, and a record is identified by its name and module together.
