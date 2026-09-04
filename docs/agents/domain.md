# Domain Docs

How the engineering skills should consume this repo's domain documentation when exploring the codebase.

## Before exploring, read these

- **`CONTEXT.md`** at the repo root — the vocabulary (loja, cargo, dono, and so on).
- **`docs/adr/`** — read ADRs that touch the area you're about to work in.

If any of these files don't exist, **proceed silently**. Don't flag their absence; don't suggest creating them upfront. The `/domain-modeling` skill (reached via `/grill-with-docs` and `/improve-codebase-architecture`) creates them lazily when terms or decisions actually get resolved.

## File structure

This repo is **single-context**: one `CONTEXT.md` at the root covers the whole
system, and `docs/adr/` holds the decisions.

```
/
├── CONTEXT.md
├── docs/adr/
│   ├── 0001-....md
│   └── 0002-....md
└── <um diretório por produto: chatbot-api/, motor-simulacao/, ...>
```

It is a multi-product monorepo (eight products, each with its own database and
migrations), but the domain vocabulary is shared, so there is no `CONTEXT-MAP.md`
and no per-product `CONTEXT.md`. If one product ever grows vocabulary the others
don't share, promote that product alone rather than scaffolding all eight.

## Where existing docs already live

Read these before writing a new one — most of what looks like a missing ADR is
already written down somewhere here:

- **`docs/README.md`** — the map of the doc set. Start here when unsure.
- **`docs/referencia-viva/`** — valid specs, design and as-built descriptions.
  New ADRs go to `docs/adr/`; the as-built record stays where it is.
- **`docs/fila/`** — planned work, one card per task.
- **`docs/nao-plano/`** — history, brand, tutorials, superseded plans. Not the
  current state of anything. `docs/nao-plano/arquivados/` is explicitly not to
  be executed.

`AGENTS.md` caps doc reading at **three files** before the first edit. Respect
that cap: this file's job is to tell you which three, not to invite a full sweep.

## Use the glossary's vocabulary

When your output names a domain concept (in an issue title, a refactor proposal, a hypothesis, a test name), use the term as defined in `CONTEXT.md`. Don't drift to synonyms the glossary explicitly avoids.

If the concept you need isn't in the glossary yet, that's a signal — either you're inventing language the project doesn't use (reconsider) or there's a real gap (note it for `/domain-modeling`).

## Flag ADR conflicts

If your output contradicts an existing ADR, surface it explicitly rather than silently overriding:

> _Contradicts ADR-0007 (event-sourced orders) — but worth reopening because…_

The same applies to the owner's recorded decisions in `AGENTS.md` §5 and in the
UX triage doc: a rejected item does not come back as a fresh proposal.
