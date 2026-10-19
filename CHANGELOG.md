# Changelog

Notable changes to Autoform, newest first. A release's version is the one in
`pyproject.toml`; `uv.lock` and the Claude, Muse and Codex manifests carry the
same one (`tests/test_release.py` checks), and `autoform --version` prints it.
Add a line under **Unreleased** with each change worth knowing about, and give
the section its version and date when the release is tagged.

## Unreleased

What has landed since 0.5.0 (2026-08-28), across about 200 merged pull requests,
grouped by theme. Each group names the pull requests to read for detail.

### Added

- **Formalization frontier.** A Markdown roadmap now schedules the work:
  `autoform work` lists ready leaves, gives one leaf's context, and measures
  the impact of a revision or an import (#92, #136, #183). Proofs may import
  other articles' modules when that impact is measured.
- **Skeletons.** `autoform skeleton` extracts what a reader must trust for each
  formalized statement, from elaborated terms, one Lean probe per root module,
  run in parallel (#12, #213, #214).
- **Search and reuse.** `autoform search` finds articles by title, Lean name or
  statement before an agent adds one (#171, #208, #375). `autoform library`
  searches and indexes a shared Lean library, ATLAS among them, and the skills
  reuse its results (#204, #311, #343, #278, #379).
- **Projects.** `autoform project new`, `inspect` and `versions` create and
  inspect Lean projects from a pinned release catalog (#14, #96, #211).
- **CI audit.** The generated verify workflow checks `lean:` targets,
  non-root axioms, a kernel replay and elaboration limits, without running
  project code in its probe (#156, #190, #247, #264).
- **Statement status.** Open statements and conditional proofs (#138).
- **Feedback.** `autoform debrief`: forms agents fill in about their work
  (#195).

### Changed

- **Commands inform; they do not break a codebase.** A new check warns and
  keeps the exit status instead of failing a repository that passed before
  (#325, #335, #361).
- **Claims are optional.** A single Formalize run keeps its own workers apart,
  and builds take no claim (#298, #324).
- **Publication.** Render publishes a site transactionally (#165), scales
  linearly (#289, #339), and links files by the spelling Git committed (#301,
  #333).
- **Checks.** The graph loader rejects formalized work the Lean cannot back
  (#158). `check` rejects Sources links that name no file (#287) or a hidden
  path (#321), and container articles that set a declaration (#328); since
  #361, hidden source notes and declaring containers pass with a warning.

### Removed

- `autoform unused-hypotheses`, in favor of Batteries' `unusedArguments`
  linter (#198, #352).
- The language server's diagnostics path (#306), the project routers and
  resident-era REPL pool (#316), and code nothing called (#114, #341, #344).

### Fixed and hardened

- **Lean runtime, REPL and LSP:** bounded transport, isolated public REPL
  calls, diagnostics barriers, and cleanup of leftover Lean processes (#13,
  #105, #106, #107, #111, #256, #283, #288, #322, #331, #338, #354, #360, #382).
- **Process control:** verified descendant cleanup and real exit statuses when
  SIGCHLD is ignored (#67, #118, #168, #315, #334, #370).
- **Lean source capture and indexing:** filesystem-generation snapshots,
  aliases, multiline declarations, public declarations among duplicates, and
  repositories of any size (#95, #148, #231, #257, #308, #312, #345, #348,
  #363, #364, #371).
- **Render and links:** malformed, angle-bracket and query links, code-only
  labels, and links that leave the blueprint (#318, #320, #326, #327, #355,
  #362, #365).
- **Security:** credentials stripped from remote URLs, URL queries redacted,
  and nonlocal dashboard requests rejected (#98, #125, #245).

### Contracts

Public CLI and JSON shapes are contracts. The JSON schema identifiers on main
include `autoform-skeleton/v5`, `autoform-work/v2`, `autoform-runtime/v3`,
`autoform-search/v2`, `autoform-publication/v2` and `autoform-impact/v1`.

### Dependencies

- `cryptography` bounded on both sides of the Intel Mac split (#56, #57);
  `pyjwt`, `urllib3` and `mcp` bumped (#50, #51, #353).
