# Sprint Plan — VGL-FIX-S05 Guide Reorganization

**Sprint:** VGL-FIX-S05

---

## Sprint Objective

Genericize the illustrative example, and relocate the measurement doctrine so that
each guide owns exactly one concern.

---

## Routing Decisions

| Content | Current owner | New owner | Task |
|---------|---------------|-----------|------|
| §7 Measurement Sources | `guides/guide-alpha.md` | `guides/guide-alpha.md` (stays) | — |
| **§8 Measured Anchors, Not Recalled Ones (ALL of §8, including §8.1 and §8.2)** | `guides/guide-alpha.md` | **`guides/guide-beta.md`** | 01 |
| §9 Escalation | `guides/guide-alpha.md` | `guides/guide-alpha.md` (stays) | — |

> [!important] §8 moves out of `guide-alpha.md` in this same sprint
> Task 01 genericizes the §8.1 example **and** the whole of §8 relocates to
> `guides/guide-beta.md`. Any assertion anchored on `guide-alpha.md` §8.1 therefore
> stops describing that file once Task 01 lands — it will pass whether or not the
> genericization was ever applied.

---

## Tasks

| # | Task | Agent |
|---|------|-------|
| 1 | Genericize the §8.1 illustrative example and relocate §8 | Sonnet |
