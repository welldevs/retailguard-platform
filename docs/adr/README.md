# Architecture Decision Records (ADR)

This directory is the **official, frozen reference for the project's architectural identity**.
It was produced by an Architecture Review Board (ARB) review and supersedes any ad-hoc discussion
about what the project is or which technologies belong in it.

## How to use this

- **[0001-architecture-baseline.md](0001-architecture-baseline.md)** — the baseline: North Star,
  Core vs. Extensions vs. AI, repository taxonomy, the full decision list (ADR-001 … ADR-021),
  risks, and the governance checklist.
- Every future change must **cite the relevant ADR by number** and respect it.
- The baseline is only reopened if the **Data Engineering job market changes materially** — not for
  personal preference.

## Governance gate (every new feature must pass)

A feature only enters the project if it answers **YES** to all six:

1. Improves employability? (appears in real target job descriptions)
2. Reinforces the narrative? (End-to-End Data Engineering Platform)
3. Appears in real job postings? (not hype without demand)
4. Increases technical maturity? (testability / governance / cost / scale)
5. Justifies its complexity? (value > maintenance cost *and* narrative-noise risk)
6. Improves credibility? (works for real and is honestly described)

If any answer is **NO**: the feature goes to `extensions/` (if it adds a keyword but not core value)
or is rejected. This gate exists to prevent regression into a "technology showcase."
