# Autoform open statements

## Open statements

By default a project runs the strict policy: CI rejects every `sorry`, so a
theorem's statement lands only together with its proof, and a statement waits
until the proof's prerequisites are proved. `open_statements: allowed` in
`roadmap/README.md` lets a theorem's statement land with a `sorry` proof. Such
an article, a theorem whose statement is formalized and whose proof is not, is
an open statement; CI audits it only through the declarations its `lean:`
names. A proof that uses open statements is conditional:
it compiles and records `proof: formalized`, but is reported as conditionally
proved, never as fully proved. Status, `work`, and the site derive that from
the Markdown dependencies and CI from what the Lean uses, so CI can print
`sorry-free` for an article the site shows as conditional, when its Markdown
depends on an open statement its Lean does not use. CI is never the looser of
the two, since a Lean reach the Markdown does not declare fails. The policy lets
dependents be stated and proved against a faithful statement before its proof
exists; the price is conditional
results that stay incomplete until every open statement they rest on is proved.
A dependent's proof can cite an open statement because its `sorry` proof
compiles, but not the placeholder a Batteries wanted command declares:
`theorem_wanted foo : T` declares a private `def` of type `ProofWanted T`, not a
theorem of `T`. Readiness still counts a prerequisite that records `statement:
formalized` against a wanted target like any other stated prerequisite. So under
this policy, state every theorem as a `theorem` with a `sorry` proof, not with
`theorem_wanted` or `proof_wanted`, and before a dependent cites an existing
wanted prerequisite, restate it that way or prove it.

A retracted theorem, one recording `statement: retracted` as a revision leaves
it, stays an open statement: the Lean its `lean:` names,
`sorry` or not, still compiles into whatever uses it. The audit keeps accepting
its `sorry`, and what rests on it stays conditional, until Formalize restates
and proves it, or the marker and `lean:` are removed. A theorem that was never
stated is not open even when it has `lean:`: a draft name does not become an
assumption, and CI rejects its `sorry`. A definition is never open: its body
is its proof, CI rejects a `sorry` in it, and its statement phase waits until
its proof prerequisites are stated. A retracted definition is not open either,
but what rests on it still assumes the open statements its body reaches. A
module catalog is never open, even while pending: it records inspection of
existing Lean, not a statement to assume, so CI rejects a `sorry` in a
declaration only it lists, and nothing that rests on it assumes it, though what
rests on one with `lean:` still assumes the open statements its own
dependencies reach. Turn
the policy back off only once no open statement remains, since the strict audit
rejects every `sorry` and strict
status shows a proof resting on one as proved, not conditional.

Write an open statement's proof as exactly `sorry`. The audit accepts a `sorry`
only inside the proof of a theorem that an open article's `lean:` names: never
in its type, a helper, a definition, or a `where` clause, and never inherited
from a declaration outside the root package. Lean-generated auxiliaries count as
helpers: a `where` clause becomes `T.aux`, well-founded recursion over two or
more arguments moves the `decreasing_by` proof into `T._unary`, and structural
recursion through a `mutual` block compiles the bodies into `T._f`, so all three
fail. Recursion can move a `sorry` case into such an auxiliary, so write the
whole proof as `sorry`, never one case of it. `lake build --wfail` and
`warningAsError` turn Lean's "declaration uses `sorry`" warning into an error,
so they cannot be combined with open statements; the generated workflow runs
plain `lake build`.

The generated `autoform-verify.yml` reads the policy with `python3
.github/autoform_audit.py --policy blueprint`, which prints `allowed` or
`forbidden` from `roadmap/README.md` (`forbidden` when the file or key is
absent) and exits 1 with `error: ...` on malformed frontmatter. Under either
policy the workflow then writes the `autoform work assumptions blueprint --json`
contract. Under `forbidden` it runs the strict audit with `--targets`: any
`sorryAx` fails with `NAME depends on unexpected axiom sorryAx` and
`root-package declarations failed the kernel-trust audit`. So does a `lean:`
name the build did not compile, with `NAME [ID] is not a declaration of the
Lean build; fix the article's lean: name or build the module that declares
it`: a theorem in a file no target imports or inside a string
passes the lexical `autoform check --lean-root` but not this. The strict audit
refuses a contract that allows open statements, records an article as open, or
lets one assume an open statement. Under `allowed` the workflow audits every
root-package declaration against the contract. The audit accepts a `sorry` in a
declared open statement's own proof and a proof that reaches only the open
statements its article's Markdown dependencies reach. It rejects a `sorry` in a
statement, a `sorry` anywhere else in the root package, a dependency outside the
root package that depends on `sorry`, an article declaration that reaches an
open statement its Markdown dependencies do not reach (so a fully proved
article, which assumes nothing, may reach none), a `lean:` name missing from the
build, and an open statement that its article records as proved. Each article
declaration gets at most one of these status lines, with `NAME` the declaration
and `ID` the article's node ID. A declaration with an error, or one that
reaches a failed declaration, gets none of them, and no declaration gets one
when the kernel replay fails:

```text
open statement (proof is sorry): NAME [ID]
open statement (proof depends on sorry elsewhere): NAME [ID]
open statement (proof is sorry-free; restate it if retracted, then record proof: formalized): NAME [ID]
conditional: NAME [ID] rests on open statement(s) A, B
sorry-free: NAME [ID]
```

A passing audit ends with `kernel trust clean except declared open statements
(N root-package declaration(s) audited; K open statement(s), C conditional
declaration(s))`; a failing one logs each error, naming the declaration and
what to change, and ends with `root-package declarations failed the
open-statement audit`.

Both audits check two more things. A `lean:` name outside the root package, as
a Mathlib article's is, must be neither unsafe nor partial (a `partial def`
counts as partial) and use no axiom beyond `propext`,
`Classical.choice`, and `Quot.sound`; otherwise it fails with `NAME [ID] is
outside the root package and is unsafe or partial` or `NAME [ID] is outside the
root package and depends on unexpected axiom AX`. The open-statement audit
reports `sorryAx` there as `NAME [ID] is outside the root package and depends
on sorry`. And both replay every root-package declaration through the kernel
on top of a fresh import of the modules outside the root package, because the
build's `.olean` files can hold anything and a root `run_cmd` can add a
declaration with kernel checking off. The replay runs only once every other
check has passed: replaying a declaration that reaches `Lean.reduceBool` or
`Lean.reduceNat` runs compiled project code, and the axiom check rejects every
such declaration, since both depend on `Lean.trustCompiler`. Until then the
audit logs `kernel replay of the root package skipped: it runs once every other
check passes`. A declaration the kernel rejects fails with `kernel replay of the
root package failed: ...`, which names the first one; the workflow's scan for
the kernel-check bypass option is only lexical.

Both audits refuse an unsafe or partial root-package declaration with `unsafe
or partial declaration: NAME`, and report a `partial def` under its own name.
For every computable recursive definition, structural, well-founded, or
`partial`, Lean adds a partial copy `NAME._unsafe_rec` for the compiler to run.
The audits skip these copies: the kernel refuses a safe declaration that refers
to one, and the kernel replay skips them too, so it refuses such a declaration
added with kernel checking off. A `lean:` name that is one still fails, with
`NAME [ID] is Lean's compiled copy of a recursive definition; name the
definition itself`.

The probe runs no project code. Its header imports only the toolchain's Lean,
and the workflow runs it with plain `lean`, not `lake env lean`, passing the
project's search path in `AUTOFORM_AUDIT_LEAN_PATH`. The probe refuses to run
when that variable is unset or when `LEAN_PATH` is set. It loads the
root-package modules as data, with the toolchain's library first on the search
path and no environment extensions, so no `initialize` block runs and no project
instance, macro, or elaborator applies to the probe's own code. It finds each
declaration's axioms by walking types and values itself, not from the axiom
tables the `.olean` files store, and counts a name that no module declares as an
axiom, which fails with `NAME depends on X, which no module of the build
declares`, or for a `lean:` name outside the root package with `NAME [ID] is
outside the root package and depends on X, which no module of the build
declares`. The walk takes a mutual inductive block as one node, so each type and
constructor of the block gets the axioms of the whole block. It imports the
toolchain's `Init` along with the build, so a core name that the build declares
itself, such as `propext`, cannot pass the axiom allowlist, which compares
names: a differing declaration fails to load with `environment already contains
'propext'`, and an identical copy of a theorem or of a Prop-valued axiom is
merged with the toolchain's own constant. Lean does let a
theorem stand in for another module's axiom of the same name and type, which the
module system relies on, so a theorem restating an axiom such as
`Lean.trustCompiler`, whose type is `True`, fails with `M declares a theorem N
in place of the axiom K declares; rename one of them so the audit can run`. A
root module whose first component names an entry of the toolchain's library,
such as `Lean.Hack`, would be looked up in the toolchain's library, where it
fails to load or a toolchain module of the same name stands in for it, so the
audit refuses it with `root module M shares its first component R with the
toolchain's library; rename the module so the audit can run`. Lean loads a
module from the first search-path entry that holds its first component, and Lake
lists dependency libraries before the root package's, so a dependency library
that also provides a root module's first component could stand in for the root
package's files. The audit refuses that with `root module M shares its first
component R with another library on the search path (DIRS); rename the module so
the audit can run`, where DIRS lists the library directories that hold R. The
workflow runs the probe with `LEAN_ABORT_ON_PANIC=1`, so a panic stops it
instead of letting it continue with a default value. It also requires the
probe's success line as its last line, so a probe that stops early fails the
step even when it exits 0.

The audit does not cover build-time IO. `lake build` runs root and dependency
code, and the Lake configuration, on the same runner before the audit, so that
code can rewrite the audit script, the toolchain, the workflow's inputs, or the
blueprint before the audit reads them. The audit also does not defend against a
malicious dependency at build time, edits to the workflow, or crafted `.olean`
bytes. Closing those needs a separate audit job that runs no project code; the
generated workflow does not have one. The project's `lean-toolchain` chooses
the Lean that builds the project and runs the probe: the workflow installs elan
with `--default-toolchain none`, and elan installs any toolchain the file names,
including a fork on GitHub, so the audit trusts that toolchain too.

`autoform init` writes `.github/CODEOWNERS.autoform.example`. GitHub ignores
that filename, so the example cannot mask or replace a repository's active
owners. Two of its suggested rules cover Autoform's control paths: the roadmap's
`open_statements` policy and `.github/` CI. To activate them, find the first
existing CODEOWNERS file in GitHub's order (`.github/CODEOWNERS`, `CODEOWNERS`,
then `docs/CODEOWNERS`), or choose `.github/CODEOWNERS` when none exists; copy
the rules there, replace `@OWNER`, and uncomment them. Consider rules for the
Lean build controls too: the Lake configuration, `lean-toolchain`, and
`lake-manifest.json` decide what CI compiles.

GitHub reads CODEOWNERS from a pull request's base branch, so new rules cannot
protect their own activation unless equivalent coverage already exists there.
Review that change explicitly. Then require pull requests and code-owner
review, dismiss stale approvals after new commits, and audit every
branch-protection or ruleset bypass. These rules put changes in front of an
owner; they do not stop project code from changing files on the CI runner.

The step runs `autoform work assumptions` from `AUTOFORM_REF`, and the earlier
`autoform check` step validates the frontmatter with that same pin. Scaffolded
workflows pin `AUTOFORM_REF` to the Autoform checkout that scaffolded them, so a
project scaffolded before open statements existed must, before opting in, move
`AUTOFORM_REF` to a commit that has `work assumptions` and replace
`.github/workflows/autoform-verify.yml` and `.github/autoform_audit.py` with the
versions `autoform init` writes at that commit. An opted-in project with an
older pin fails closed: `autoform check` stops with `unsupported frontmatter key
'open_statements'`, and the audit step fails without `work assumptions`. Under
the strict policy that missing command, which argparse reports as `invalid
choice: 'assumptions'`, is the one failure the step tolerates: it logs a warning
that `AUTOFORM_REF` predates `autoform work assumptions` and runs the strict
audit without the `lean:` name check, as earlier workflows did. Any other
failure there, such as a failed fetch, fails the step. An older workflow runs
the strict audit, which rejects every `sorry`. A newer
`.github/autoform_audit.py` keeps the older workflow's three-argument form,
which runs the strict audit without the `lean:` name check. Its probe refuses
to run under an older workflow's `lake env lean`, so replace the two files
together.

To reproduce the CI audit locally after a build, with `ROOT_PACKAGE` the Lake
package name the workflow reads from `lake translate-config toml`, and
`--targets` in place of `--open-statements` under the strict policy:

```bash
lake build
lake pack /tmp/autoform-root.tgz
autoform work assumptions blueprint --json > /tmp/autoform-assumptions.json
python3 .github/autoform_audit.py --open-statements /tmp/autoform-assumptions.json \
  ROOT_PACKAGE /tmp/autoform-root.tgz /tmp/autoform-probe.lean
AUTOFORM_AUDIT_LEAN_PATH="$(lake env printenv LEAN_PATH)" LEAN_ABORT_ON_PANIC=1 \
  lean /tmp/autoform-probe.lean
```

The audit passes only when `lean` exits 0 and the last line it prints is the
`kernel trust clean ...` line; the workflow checks both.
