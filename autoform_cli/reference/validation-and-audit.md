# Autoform validation and audit

## Validation

`autoform check` rejects cycles between authored articles, missing targets,
escaping paths, symbolic links under `roadmap/`, self-dependencies,
missing or multiple H1 titles, unsupported frontmatter keys, assertion values
it does not recognize, and assertions the Lean cannot back: `proof: formalized`
without `statement: formalized`, or either without a `lean:` name, even beside
`mathlib: true`. With `--lean-root`, `check` also fails on a `lean:` name that
is absent from the sources (as `leanblueprint checkdecls` does for LaTeX
blueprints) or defined more than once in them (see below). It validates
structure and leaves mathematical correctness to the agent and the Lean
kernel. Only the article graph must be acyclic, so project, chapter, and scope
maps can relate two containers in both directions.

Render omits hidden paths, those with a part starting with `.`, so:

- Hidden files and folders under `roadmap/` are no part of the roadmap: they
  hold no articles, need no chapter page, and may be symbolic links, such as
  an editor's lock file. A dependency on a hidden page fails, naming the hidden
  path, as does one that steps through a hidden folder and back out, and so
  does an `.implementation-notes` folder under `roadmap/`.
- A `## Sources` link to a local path must name a file inside the blueprint
  that opens as written, as `audit` also requires: a missing file or a missing
  folder on its path, a directory, an invalid path or URL, a symbolic link
  loop, a target outside the blueprint, or a path with a hidden part, even one
  its `..` steps leave again, fails. Under `sources/`, a hidden note passes
  `check` with a warning instead and `audit` still reports it: only a
  repository link reaches it, so it must be committed.
- A `## Sources` link to a view generated at the blueprint root, such as
  `dependencies.md` or `structure.md`, fails too, and `audit` and render reject
  coverage evidence that names one.

These pass `check` with a warning:

- A `## Sources` link with another scheme or a network location, which work
  and search leave out; only `audit` checks fragments and fails such links.
- A `mathlib_file` that is not a portable relative path, which search reports
  as null.
- A byte-order mark at the start of an article that otherwise loads. It hides
  whatever opens the first line: frontmatter there is read as text, so its keys
  are ignored.
- A `declaration` on a container article, since nothing counts or schedules a
  container's own declaration; `audit` reports it as `formalizable-container`.

A byte-order mark that hides an article's H1 title fails `check`, as a missing
title.

`check` also warns, naming the file and the line, about what a published page
could use to run script or pass for the site's own markup. None of it fails
`check` or stops `render`: `render` publishes such a page, or such a statement
in its box, as typed, every character escaped in one preformatted block under
a note, until the warning is fixed. The page keeps the title its H1 gives, in
its header and in the navigation, and a statement shown as typed stays in its
section with the chapter's other statements. A flagged landing page shows
only its title and opening sentence, as text, above the dashboard.

- Raw HTML: a tag, a character reference, an unclosed comment, or anything the
  site's Markdown would pass through as HTML. Write it in Markdown, or in code
  to show it as typed; in a formula, put a space after `<`. A complete
  `<!-- ... -->` comment outside code is left out of the page, and one in code
  is shown as typed. A reference a browser shows as typed, such as the `&D;`
  in `R&D;`, is fine.
- A link, an image, or a link definition, used or not, to anything but the
  site's own pages or an `http:`, `https:`, or `mailto:` address, in any case:
  a `javascript:` or `data:` one would run or show what it holds on the site's
  origin. An address shown in code is fine.
- An attribute list, which could give text an id, a class, or a style that
  makes it look like the site's own markup, such as a status mark; a heading's
  id comes from its title. The braces of a code fence may only name its
  language, as in ```` ```{.lean} ````, and options such as `title` or
  `linenums`.
- A code fence at the margin left open where an article, a statement, its
  notes, or a stretch of a chapter ends. The site reads fences over a whole
  page, so it would run on through what `render` puts after it, status marks
  included, to the next fence on the page; close it.
- A list nested deeper than the site's Markdown converter can read, hundreds
  of levels down; flatten it.

`check` also warns about a formula that defines a command, such as
`\newcommand`, `\def`, or `\DeclareMathOperator`, or uses one the site turns
off, such as `\label`. The site's MathJax ignores notation an article defines
(see above), so such a formula shows an error in red and the rest of the page
is published as written; put the project's notation in
`blueprint/tex-macros.json`.
`check` reads every Markdown page the site publishes as `render` publishes
it, the landing page, `coverage/README.md`, and source notes included, so the
site never publishes markup that an article's reviewer read as text and the
owners of its theme never saw.

`--lean-root` inspection needs directory-descriptor traversal, so platforms
without it, including Windows, fail closed. A detected Git permalink is emitted
only for a file whose bytes equal its blob at the detected commit; dirty,
untracked, or missing files keep local declaration locations but get no URL.
An explicitly supplied ref is the caller's attestation.

Lean indexing reads the whole Lean root or nothing. It stops with an error,
rather than indexing what it could, when an entry it must read cannot be read
safely: a `.lean` file that cannot be read, a folder that cannot be listed or
searched, a `.lean` entry that is a symbolic link or a special file (editor
lock links named `.#*.lean` are skipped), or an unreadable `manifest.json`
below the root, which is read to recognize skeleton and review packet output
folders, or an unreadable `publication.json` below the root, which is read to
recognize rendered sites. These stops apply in every folder the walk
enters, so an unreadable folder of unrelated files inside the Lean root stops
indexing too; other files are never read. `render` without `--lean-root` uses
the blueprint's parent folder as the Lean root. To clear a stop, fix the
permissions, or move the entry out of the Lean root or into a folder the walk
skips: `.direnv`, `.git`, `.lake`, `.obsidian`, `.trash`, `.venv`,
`build`, a folder below the root that holds a `.git` entry, a
recognized skeleton or review packet output folder, or a folder below the
root that holds a complete `publication.json`, such as a rendered site or the
`mkdocs` copy of one. Every command skips these folders, so `render` and the
other commands index the same files. `render` marks the site it is writing
before it copies any file into it, so a command that indexes during a render
skips it too.
`mkdocs build` empties `site/` and then copies files in name order, so `site/`
can hold copies before its `publication.json`; a command that indexes during
the build can read them, so run it again once the build is done. There is no
command-line option to exclude other folders. The skipped folder names and the
`manifest.json`, `publication.json` and `.git` names match in any letter case,
except `build`, which must be lowercase. The `.lean` suffix must match
exactly, so `A.LEAN` is not indexed.

A capture that sees Lean inputs change while it indexes is retried; when every
attempt changes, the error names the changed paths it can attribute, relative
to the Lean root, for example `Lean sources kept changing while they were
indexed; changed: Proj/A.lean`. Folders the walk skips, such as a generated
site or a nested Git checkout, and files other than `.lean` sources may change
during a capture.

Within each file, up to an `#exit` line, the index records the declarations
written with `theorem`, `lemma`, `def`, `abbrev`, `instance`, `structure`,
`class`, `inductive`, `opaque`, `axiom`, `irreducible_def`, Batteries' `alias`,
and Batteries' wanted commands `theorem_wanted`, `proof_wanted`, `def_wanted`,
and `instance_wanted`, which state a result whose proof or construction is
deferred. The command may follow `@[...]` attribute lists and the modifiers
`public`, `private`, `protected`, `noncomputable`, `partial`, `unsafe`,
`scoped`, and `local`; a declaration behind any other modifier, such as `meta`
or `nonrec`, is not indexed, and neither is an unnamed `instance` or
`instance_wanted`. `_root_.X` is recorded as `X`. `alias b := a` records `b`,
and `alias ⟨mp, mpr⟩ := a_iff` each of its names that is not `_`; the `:=` must
be on the alias's line, and the target on that line or the next nonblank one.

A name declared once has that declaration, even a private one. A name declared
more than once has the one declaration that is neither `private` nor a wanted
command (Batteries elaborates each into a private placeholder), since every other module
sees the public one. With two or more public declarations (a file no library
builds counts too), or only private and wanted ones, the name has none:
`check --lean-root` fails with `declaration defined more than once`, `render`
warns (`--require-declarations` exits 1), `audit` reports
`lean-target-ambiguous`, `skeleton` leaves it unresolved, and work and search
report no `source_file`; each diagnostic lists the `path:line` of every
declaration of the name. `work impact` locates a compiled constant in its own
module's file. The rule sees only indexed declarations: a public one behind an
unindexed prefix such as `open X in`, or written `«main»` where the article
writes `main`, leaves a private one as the name's only declaration. In a file
that starts with `module`, a declaration outside a `public section` and
without `public` is private to Lean but public to the index, so such a name may
be reported as defined more than once where Lean accepts it, or selected where
Lean binds it nowhere outside its file.

The Markdown files are the source of truth. Graphs and sites are derived views
that may be regenerated at any time.

## Audit contract

`autoform audit` reports structured findings at blueprint-relative paths. It
checks that no article leaves a code fence open, that formalizable articles are
declaration-sized leaves with statement text and an explicit dependency
section, that asserted Mathlib facts are
internally consistent, and that cited work resolves to local source
material without escaping the blueprint. Coverage files are checked for broken
links and explicitly declared gaps. With `--lean-root`, local declaration names
and declaration kinds are checked against the Lean source index, along with the
elaboration limits each target runs under. It leaves `review_approved` to
`review check`, since judging it needs a Lean extraction.

An alias has its target's kind, size, and elaboration limits when the index
can be sure what the target is, by the rules in `lean.py`'s `alias_target`;
otherwise it matches any intent and is measured, like any other declaration,
by its own span and limits. Each name of `alias ⟨mp, mpr⟩`, and any alias of
one, is a theorem whatever its target is.

A wanted target matches the intent its command mirrors: `theorem_wanted` and
`proof_wanted` a `theorem`, `lemma`, `proposition`, or `corollary`,
`def_wanted` a `def` or `definition`, and `instance_wanted` an `instance`. A
theorem's wanted target can back `statement: formalized`, but no wanted target
backs a proved article: `lean-target-wanted` reports one named, directly or
through an alias, by an article that records `proof: formalized`, or by a
definition that records `statement: formalized`, since a stated definition
counts as proved. A wanted command
without a body elaborates to a placeholder that carries no `sorry`, so no
`sorry` check catches one. Batteries declares every placeholder `private`, so
the kernel-trust audit of the generated verify workflow looks a `lean:` name up
among the root package's placeholders when the build has no declaration of that
name. A target that resolves to a placeholder, or to a public alias of one,
passes as wanted only when the assumption contract records its article as
`stated`, `can_prove`, `can_state`, `planned` or `not_ready`. Any other state
fails it, as `lean-target-wanted` fails proved and defined articles, and so do a
`mathlib` state and a state the helper does not know. The audit still reports
any other `private` declaration as not a declaration of the Lean build.

### Warnings

A finding is a problem the audit fails on. A warning never fails the audit:
`clean` and the exit status depend on findings alone, so a repository that
passes keeps passing when a warning appears. The text output prints a
`warning: <path>: <code>: <message>` line for each, after the error lines.
`--json` lists them after `findings` as `warnings`, sorted by `article_path`
and `code`. Each also carries a `message` and `declarations`, one object per
affected declaration and setting with its `name`, `option`, `value`,
`location` (the `set_option` as `path:line` relative to the Lean root), and
`scope` (`file`, `section`, `declaration`, or `proof`), sorted by name. The
catalog limit warnings under [Elaboration limits](#elaboration-limits) fill
`declarations`. Two warnings leave it empty: `atlas-omission`, at `atlas.json`,
names what loading ignored in that file, and `decomposed-without-declaration`,
at `coverage/README.md`, names a `DECOMPOSED` row's links that reach no
declaration leaf.

### Structure

Containment is inferred from nested `README.md` articles, so a chapter
directory without one is invisible to the hierarchy: its pages attach to the
roadmap root and the book loses a level. `missing-chapter-article` reports a
directory directly under `roadmap/` that holds articles but names no chapter.
Deeper directories (the `definitions/` and `theorems/` buckets the bundled
example uses) are a filing convention inside a chapter and are not checked.
`overfull-container` reports a mathematical article with more than 24 direct
children, which is a table of contents rather than a chapter. A roadmap root
whose direct children are all chapter pages is a repository-wide subject index
and may hold 64; one root-level leaf returns the root to the 24-article limit.
A `navigation: module` page lists one Lean module's declarations, so it may
hold as many as the dependency explorer draws as a map, 120.

### Node size

`node-too-large` is retrospective and needs `--lean-root`: it measures the
source span of a node's resolved `lean:` declarations, from each declaration's
first line to the line before the next one. A node is reported only once it
clears both 200 lines and four times this project's own median, so a project
whose units are uniformly long is measured against itself rather than gated on
an imported norm, and a project with too few finished nodes to have a
meaningful median cannot clear the multiple at all. Every measurement appears
in the finding's reason.

### Elaboration limits

With `--lean-root`, the audit reads the `maxHeartbeats`,
`synthInstance.maxHeartbeats`, and `maxRecDepth` settings each resolved `lean:`
target is elaborated under, including a catalog's. For a declaration article,
`lean-target-unbounded-limit` reports a target with no heartbeat limit: a
`set_option maxHeartbeats 0` or
`set_option synthInstance.maxHeartbeats 0` in force at the declaration or inside
its proof, which lets elaboration run indefinitely instead of failing.
`lean-target-unscoped-limit` reports a target whose raised limit comes from a
file- or section-wide `set_option`, which also covers every later declaration
whether or not it needs one; Mathlib's `linter.style.setOption` rejects
unscoped heartbeat limits for the same reason. A raised limit put on the
declaration itself with `set_option ... in` is accepted Mathlib practice and is
not reported. The pass is lexical: it follows `namespace`, `mutual`, `end`, and
`section` nesting, including `noncomputable section` and the module system's
`@[expose] public section`, and treats an indented `set_option` as part of the
proof above it.

A catalog inventories code that already exists, so its declarations get the
same two checks as [warnings](#warnings), at most one per catalog and code:
`catalog-unbounded-limit` and `catalog-unscoped-limit`. As for a declaration
article, an alias is read as the declaration it reaches. The message counts the
affected declarations against all those the catalog's resolved names reach (an
alias listed beside its target counts once), names the options involved, and
locates the `set_option` of the first by name, for
example `2 of 40 catalogued declarations have no maxHeartbeats limit
(Inv.alpha at Inv.lean:1 and 1 more); existing code: change it only on request,
and a finite limit must pass a rebuild`. A name that does not resolve is a
`lean-target-not-found` or `lean-target-ambiguous` finding and is not counted.

### Statement text

A formalizable article must state its result in prose a reader sees. At most
one of three findings reports a statement that does not, checked in this order:

- `missing-statement-text`: the statement has no prose outside code blocks, HTML
  comments, and lines that hold only a heading written with `#` marks, such as
  `### Setting`.
- `empty-statement-text`: the published prose has no letter or digit, as with a
  hidden element, a horizontal rule, an image, a link with no text, or a heading
  that is underlined, quoted, or in a list item.
- `placeholder-statement-text`: every word is one of `pending`, `placeholder`,
  `todo`, `tbd`, `unknown`, or the statement opens with one of them followed by
  a colon or a dash, as in `TODO: state it`. A single hyphen or en dash counts
  only with a space after it, so `Unknown-variance` is a word.

The prose is read as the site publishes it, without headings, code blocks, and
diagrams; inline code and mathematics count. A status word that begins a
sentence passes ("Pending Mathlib PR 1234 ..."), and so does a marker written
without punctuation; both are left to review. A real statement that opens
`Unknown: ...` or `Pending: ...` is reported and needs rewording, and so does
one written in symbols alone, such as `⊥ ≠ ⊤.`, which has no letter or digit.
A reference-style link is read
without its definition when that sits in a later section. Coverage evidence is
held to the same placeholder rule.
