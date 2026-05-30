# Research Context

This folder holds the literature-review and positioning material that informed Compute4Me's design. It is **research context, not specification** — the binding documents for what the project is and how it's built live in [../prd.md](../prd.md), [../context.md](../context.md), and [../adr/](../adr/).

## What's here

- **[related-work.md](./related-work.md)** — Condensed survey of distributed deep-learning systems (parameter servers / all-reduce, Ray, elastic training, decentralized/volunteer DL, federated/edge/fog, serverless ML). Summarizes what's solved, what's emerging, and where the gaps are.
- **[novelty.md](./novelty.md)** — Focused analysis of what Ray does *not* solve and where Compute4Me's novel contribution lives. Reads as a complement to [related-work.md](./related-work.md).

## Why it lives in the repo

Two reasons. First, the design choices in [../prd.md](../prd.md) and the [ADRs](../adr/) rest on this positioning — keeping it visible lets a reader follow the reasoning. Second, the eventual research paper will cite this framing; having it under version control alongside the code preserves the audit trail.

## What this is *not*

Not an exhaustive bibliography, not a literature review for publication. The original full-length section drafts (eight markdown files + PDFs) lived under `docs/md/` and `docs/pdfs/` in early commits and were consolidated into the two files here. The git history preserves them if anyone needs the long form.
