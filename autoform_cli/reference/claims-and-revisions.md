# Autoform claims and revisions

## Claim contract

Claims use canonical `autoform-claim/v1` JSON in orphan commit messages and
exact observed object IDs as update preconditions. Absent and verifiably expired
leases may be acquired; live peer leases are refused. Malformed or unreadable
refs are unverifiable and may not be acquired, renewed, released, or removed by
cleanup. A heartbeat verifies ownership on entry and permanently records any
later refusal or transport uncertainty as lost ownership.

A claim key is a slug and digest of any string, not a validated node id, so a
shared resource is locked the same way a node is, as is a Lean helper no
article owns under the `lean/<slug>-<digest>` key `work impact` reports.
Parallel agents get one Git worktree each, and builds take no claim. Worktrees
on one machine share its elan toolchain and Mathlib cache, so Formalize fills
the cache once before creating them.

`acquire`, `renew`, and `release` accept several targets. The board reads
every ref once, applies the single-key ownership checks to each, and sends one
atomic push with a lease per ref, so either every claim changes or none does;
a board that cannot push atomically is refused. Success prints the usual line
per target. A refusal exits 1 with one line such as `error: could not acquire
af_y, af_z; no claim was acquired: held by another worker: af_y`, naming the
blocking targets when known, and leaves no claim behind; a duplicate target
exits 2. Workers that need several
claims follow a no-hold-and-wait rule: acquire the whole set in one command and,
when it is refused, release everything already held and retry with the whole
set, never holding some claims while waiting for others. The CLI does not
enforce the rule; it is what keeps two multi-article revisions from
deadlocking.

`claim list` copies the whole board with one fetch and reads every lease at
once, so its cost hardly grows with the number of claims. Each lease it prints
is the one its ref named when the board answered. The listing is not a proven
consistent snapshot of the whole board: Git can read the refs it advertises one
by one, so a peer's multi-claim acquire or release made while the board answers
can show some of its claims changed and others not. A peer's renewal meanwhile
changes nothing, except that a server speaking Git's older stateless HTTP
protocol may refuse the fetch, which is then repeated up to three times. A
board with claim keys that differ only in case, which a case-insensitive
scratch cannot store under their names, is listed with one more command that
names its claims first. A listing is a report, not a lock: every acquire,
renew, and release checks ownership again.

`claim list TARGET...` lists only those targets' claims, in the same JSON; a
target without a claim is left out, and a duplicate target exits 2. It names
the targets' refs, fetches only those and reads their leases, so changes to
other claims never make it retry and no other claim's lease is copied, and a
target released meanwhile has the targets named again, never the whole board.
Naming the targets still downloads the board's list of refs, branches
included, so over a network its cost grows with that list. `--timeout SECONDS`,
120 by default, bounds the whole listing, however long it is set, and a step
still running after five seconds is named on stderr as `claim list: <step>...`. A listing
that fails exits 1 with nothing on stdout and one line on stderr: `error:
timeout:` when the board did not answer in time, naming the step; `error:
contention:` when the board refused every fetch because claims kept moving; or
`error: transport:` for any other failure to reach or read the board. Every
claim command runs Git with `GIT_TERMINAL_PROMPT=0` and no input, so Git itself
never waits for a password, though a credential helper or `GIT_ASKPASS` program
it is configured to use still can, until the time limit. `claim list` also
runs Git in its own process group, without a terminal on Linux and macOS so
`ssh` cannot prompt either, and stops a Git command that runs out of time or is
interrupted together with everything it started. The other claim commands run
Git in the caller's process group, so a terminal's interrupt reaches Git, which
then removes the ref lock it holds.

A Git process that stops while updating a claim ref leaves a lock file in the
board, and Git then refuses the updates it guards:
`refs/autoform-claims/<key>.lock` blocks that claim, `packed-refs.lock` blocks
every release, and on a board in the reftable ref format
`reftable/tables.list.lock` blocks every claim update. On a board given as a
local path, or as a `file://` URL except on Windows, a command whose push such
a file still blocks two seconds later exits 1 naming the file and when it was
modified; a lock that goes away within those two seconds counts as a lost race.
On such a board, `claim cleanup` leaves a lease whose release a lock file
blocks in place and still exits 0, and `claim list` and `claim cleanup` warn on
stderr about each lock file not modified within two seconds of the current
time. Git records no owner for a lock file, so Autoform never deletes one: once
no Git process is using the board, delete the file and retry. Over any other
transport the board's files are not visible, so a lock file there shows up as a
lost race or as Git's own error, depending on the file, the operation and the
server's Git version, and Git's error also stops `claim cleanup`.

Claims are temporary operational state, never article frontmatter.

## Revision contract

Revising a declaration X of article R that other articles' Lean uses touches
work R's claim does not cover. This contract makes that work claimable and
keeps the default build passing. Roadmap records a requested revision in the
Markdown (step 6); Formalize carries out the Lean side (steps 1 to 5).

1. On a fresh build, run `autoform work impact R . --lean-root .`, with
   `--declaration` when only some of R's declarations, or a helper, change.
2. Choose the route:
   - **Contained** (`contained: true`): revise X in place, under R's claim when
     using claims. `contained` ignores R's own declarations, so re-check R's
     other declarations that use X as well.
   - **Expand, migrate, contract**, the default whenever anything uses X: add
     X' with the revised statement, leave X unchanged and mark it
     `@[deprecated X' (since := "YYYY-MM-DD")]`, and point R's `lean:` at X'.
     Under the open policy, while X's proof is still `sorry`, R's `lean:`
     names X beside X', so the audit keeps accepting that `sorry` as an open
     statement, and R records `proof` only after step 4 deletes X.
     Statement-impacted articles replace `statement: formalized` with
     `statement: retracted`, lose `proof`, and keep `lean:`, so they return to
     the frontier as revisions; under the open policy a statement-impacted
     theorem stays an open statement meanwhile (see [open
     statements](open-statements.md#open-statements)). When X's proof is sorry-free,
     proof-impacted articles keep everything, since their proofs still use the
     valid old X; migrating them to X' is later work. While it is still
     `sorry`, proof-impacted theorems lose `proof: formalized` but keep
     `statement` and `lean:`, so they return to the frontier as proof phases
     and migrate to X'. A stated definition counts as proved whatever its
     `proof:` says, so a proof-impacted definition is migrated to X' in the
     same commit or, when that is not possible, retracted like a
     statement-impacted article. Otherwise they would keep resting on the
     deprecated, `sorry`'d X, show "conditional, assumes R" although R's text
     now describes X', and keep X out of `deprecated_unused`, so R could never
     record its proof. The claim set is every article whose frontmatter or
     Lean changes: R, the statement-impacted articles, the unused statement
     dependencies, and, in that case, the proof-impacted ones.
   - **In place**, only when X and X' cannot coexist, for example an instance
     or a structure change: the claim set is every `claim_targets` entry.
     Repair every impacted declaration in one commit whose default build
     passes. A change `work impact` cannot see, to an instance's priority or
     scope, an attribute, or notation, also takes this route whatever
     `contained` says, and its `claim_targets` are incomplete: add every stated
     article whose Lean imports the changed module and treat it as
     statement-impacted. A statement-impacted article keeps `statement` only
     after an Agent Review of its source faithfulness under X's new meaning;
     otherwise it records `statement: retracted`, loses `proof`, and keeps
     `lean:`. A repaired dependent proof keeps `proof: formalized` only after
     an Agent Review of the repair; otherwise it loses `proof`. A theorem's
     proof that cannot be repaired becomes exactly `sorry` under the open
     policy; otherwise delete the declaration and remove its article's
     `lean:`, `statement`, and `proof`, which works only when nothing else
     uses it. When neither applies, the revision is blocked: release any claims
     and report it. Record what happened in the revision commit and report. Use
     an implementation note only until [its deletion
     rule](../README.md#articles-and-containment) applies.

   An unused statement dependency, which rules out the contained route, is
   re-reviewed under the revised meaning, X' on the expand route and X's new
   meaning in place: it keeps `statement` only after an Agent Review of its
   source faithfulness; otherwise it records `statement: retracted`, loses
   `proof`, and keeps `lean:`.
3. When using claims, claim the route's claim set with one
   `autoform claim acquire`. When it is refused, release everything and report
   the held claim as the blocker. After acquiring, re-run `work impact`; if the
   set grew, release and start over with the larger set. Without claims, a
   Formalize subagent has its lead confirm the set instead. With or without
   claims, after rebasing onto the current shared branch and rebuilding, re-run
   `work impact` once more; if the set grew, repair the new targets before
   landing, after acquiring the whole larger set in one command under the
   no-hold-and-wait rule of the [claim contract](#claim-contract) or, without
   claims, after the lead confirms them. Under the open policy, reproduce the CI
   audit as [open statements](open-statements.md#open-statements) shows before landing. Land one
   commit, then release any claims.
4. Contract: delete a deprecated X once it appears in `deprecated_unused` of
   `work impact R . --lean-root .`, meaning no declaration uses it and no
   other article's `lean:` names it, and drop it from R's `lean:` in the same
   commit. `contained` is not enough: it ignores R's own declarations, such as
   an X' built from X.
5. `autoform audit --lean-root` reports `lean-target-deprecated` for a
   declaration article whose `lean:` names a declaration with `deprecated` in
   its own `@[...]` attribute list; point it at the replacement. The check is
   lexical, so it misses a later `attribute [deprecated] X`, which the
   deprecated list of `work impact` does see. Under the open policy the finding
   is expected for a superseded X that step 2 keeps in R's `lean:` until step 4,
   so `autoform audit --lean-root` and `autoform doctor --lean-root` fail in
   that window by design, while CI, which runs neither, passes.
6. When Roadmap revises an article, its statement text or only its Lean, it
   records the decision and retracts the article: it replaces `statement:
   formalized` with `statement: retracted`, removes `proof: formalized`, and
   keeps `lean:`, which `work impact` needs, so the article returns to the
   frontier as a revision. It retracts only that article and the dependents
   whose Markdown text the revision rewrites; the Lean-side impact decides
   every other dependent. Roadmap edits only Markdown: it releases any claims
   and leaves the Lean revision to Formalize.

With the review marker, a commit that drops a declaration from an article's
`lean:` also deletes that declaration's read-back cards under
`blueprint/readbacks/<article_id>/`, which `review check` otherwise reports as
orphaned, and one that removes `lean:` also removes `review_approved`.
