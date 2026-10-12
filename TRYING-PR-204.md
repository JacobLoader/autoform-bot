# Trying Autoform PR #204: reusing results from a Lean library

> This file is for trying the PR before it is merged. It points at a test
> copy of ATLAS, so it is removed before #204 merges.

[PR #204](https://github.com/facebookresearch/autoform-bot/pull/204) lets the
Autoform agents search a Lean library your project depends on (here
[ATLAS](https://github.com/facebookresearch/atlas-lean)) and reuse a result
instead of proving it again. Please try it on a real paper and tell us what
the agent did.

Requires Claude Code, Git, [`uv`](https://docs.astral.sh/uv/), and `elan`.

## 1. Load the plugin from the PR

This checkout is the plugin. If you do not have one yet:

```bash
git clone -b feat/issue-203-library-search https://github.com/zibo-yang/autoform-bot autoform-pr204
```

From the folder that holds it (not from inside it), start Claude with it. If
your checkout has another name, use that name instead of `autoform-pr204`
here and in step 3.

```bash
claude --plugin-dir "$PWD/autoform-pr204"
```

If you already have Autoform installed, disable it with `/plugin` for the
trial, so the two copies do not mix, and enable it again afterwards.

## 2. Set up the project

In Claude:

> /autoform:setup Set up a new Lean project in ./trial. It will depend on
> ATLAS, which I will require from https://github.com/zibo-yang/atlas-lean at
> 0ca59c787215c3638311b0a14af59aaae3208f6b.

Setup should create it on Lean and Mathlib v4.34.1, the versions ATLAS needs.
Then exit Claude and add ATLAS yourself, at the end of `trial/lakefile.toml`:

```toml
[[require]]
name = "atlas"
git = "https://github.com/zibo-yang/atlas-lean"
rev = "0ca59c787215c3638311b0a14af59aaae3208f6b"
```

```bash
cd trial
lake update atlas
```

This downloads Mathlib (about 8 GB with its cache), unless you first copy
`.lake/packages` from another project on Mathlib v4.34.1. ATLAS comes with its
search index, so you never build ATLAS as a whole. (This ATLAS is a test copy
of `main` with four slow-building files removed.)

## 3. Try it

In `trial`, save the paper and start Claude again:

```bash
curl -L -o paper.pdf https://arxiv.org/pdf/2307.05244v1
claude --plugin-dir "$PWD/../autoform-pr204"
```

Then:

1. `/autoform:roadmap Build a complete roadmap for Section 1.2 of paper.pdf: Gauss's Theorem 1.4 on r₃(n), the definitions it uses, and the Legendre/Gauss corollary.`
2. `/autoform:formalize Formalize the roadmap, one result at a time.`

ATLAS already proves the definition of r₃(n), r₃(n) = 0 for n ≡ 7 (mod 8),
r₃(4n) = r₃(n), and Legendre's three-square theorem. It states the Hurwitz class
number and Gauss's formula only as wanted, without proofs.

Formalize copies the project for each result it works on, so keep about 30 GB
free.

## 4. What to look for

- Roadmap searches ATLAS (`autoform search … --library atlas`) and finds the
  results above.
- Formalize uses those ATLAS results instead of proving them again.
- The agent says the Hurwitz class number and Gauss's formula are only wanted
  in ATLAS, not proved.
- The agent never edits `lakefile.toml` or `lean-toolchain`, and never runs
  `lake update` itself.

## 5. Send us

- A few lines on what worked and what did not.
- The Claude transcripts: the `.jsonl` files in `~/.claude/projects/`, in the
  folder named after the `trial` path.
