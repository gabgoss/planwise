---
description: Exit-criteria fidelity continued — a decision that leaves a known failure in a verifier's input set rewrites every criterion pinned to that verifier's exit code at the moment of the decision, and a flag that changes how a gate is read names and supersedes the criterion's wording (§16.13), and a size or rate constant is derived from the headline criterion while every closeout reports against the criterion, not the constant (§16.14), and an append-only record numbered from its newest end rewrites every existing identifier on each append (§16.15). Split out of exit-criteria-fidelity.md when that file neared the Read-tool token gate.
---

# Exit-Criteria Fidelity, Part 2 — A Decision Rewrites the Criteria That Depend on It

**Purpose:** §16.13 and §16.15, split out of [exit-criteria-fidelity.md](exit-criteria-fidelity.md) when that file neared the Read-tool token gate. §16.1-§16.12 stay on that anchor, which keeps the original filename. §16.13 extends §16.9 (an absence criterion must exclude its enactor) from the criterion that cannot be satisfied by construction to the decision that makes it so. §16.14 adds a rule for a size or rate constant that must be derived from the plan's headline criterion. §16.15 extends §16.12 (append, never insert) from a list that grows by hand to a record whose numbering counts from the newest end.

---

### 16.13 A Decision That Leaves a Known Verifier Failure Rewrites Every Criterion Pinned to Its Exit Code

> [!constraint] A decision that leaves a known failure in a verifier's input set changes every claim that verifier's exit code backs
> The claims live in files the decision-maker did not open. "`<verifier>` exits 0" was true when written. It became false at the decision, and nothing in the tree marked it. A routed flag that carries only the grading rule is correct and incomplete. It leaves the criterion standing, so the contradiction surfaces one session later as a structural finding instead of at its cause.

A checker globs every `*.json` file under one probes directory and exits 1 if any file drifts. A go/no-go session found two archived files drifting on a defect in a module. It decided to fix the module and to grant the checker no exemption. The two archived files stayed where the checker reads them. The decision routed a flag to the next sprint: "grade this session on its own output's OK line. A new DRIFT line naming the same event is the same defect."

Three task files, one session orchestration, one sprint plan and the master plan all still read "`<verifier>` exits 0". The receiving orchestrator ran the checker once before its first run. It exited 1, on exactly the two archived lines. Both tasks' success criteria were unsatisfiable before the session's own runs had produced anything.

> [!constraint] WRONG and CORRECT — the decision names and rewrites every dependent criterion
> ```
> WRONG — the decision leaves the inputs, routes a grading hint, and the criteria stand:
> decision: module edit, no checker exemption      (two archived DRIFT lines persist)
> flag ->   "grade on your own output's OK line"
> criteria: "<verifier> exits 0"                    (several files, untouched)
> next session, before its first run: exit=1        -> Phase-1 structural finding
>
> CORRECT — the decision names and rewrites every dependent criterion:
> decision: module edit, no checker exemption
> Grep "<verifier>" over <plan tree>                -> every pinned criterion listed
> each -> "this run's output line reads OK; no DRIFT names it; exit code and non-OK lines recorded"
> flag -> "criterion X in files A..E is superseded by the clause above"
> ```

Three consequences follow.

1. **Enumerate the criteria at the decision.** Run `Grep` over the plan tree for the verifier's name. Every "exits 0", "prints PASS" or "no DRIFT" over it is now a claim to rewrite, not a flag to route around.
2. **Rewrite each into a scoped clause.** Write: "The step-4 line for this run's output reads `OK`. No DRIFT line names this run's output. The exit code and every non-OK line are recorded verbatim." The archived failures then pass through the gate as recorded state, not as this run's defect.
3. **Say that the flag supersedes the criterion.** A flag that changes how a gate is read must say the gate's wording is superseded. "Grade on your own OK line" reads as advice beside a criterion that says "exit 0". Name the criterion, quote it, and replace it.

**Scope.** This is the propagation step after classification. Classifying a non-zero exit code by cause is a separate rule: see [verify-verdict-source.md](verify-verdict-source.md) §8. Carrying the consequence of a decision into every dependent criterion is this rule. It applies to:

- Any verifier that reads an accumulating directory (a glob over output files, logs or archives) where a known-bad input stays by decision.
- Any criterion phrased as an exit code or a single verdict word.
- Go/no-go and fallback decisions that route flags forward.

§16.9 covers an absence criterion that cannot be met because its own enactor trips it. This section covers a criterion that was meetable until a decision made it unmeetable, and the decision-maker was the only party positioned to rewrite it.

### 16.14 A Size or Rate Constant Is Derived From the Headline Criterion, and Every Closeout Reports Against the Criterion

> [!constraint] A budget constant and a headroom target are different quantities. A green budget gate says nothing about the target
> "Under 22,000" and "at least 2x under 25,000" answer different questions. When a plan states a headline target and a design constant that enforces size, derive the constant from the target. Or state explicitly that the constant is the weaker guarantee, and restate the target to match.

**Three design-time steps.**

1. **Compute what the constant permits in the target's units.** A 22,000-token budget against a 25,000-token cap permits 1.14x headroom.
2. **If that falls short, change one side.** Lower the constant (to 12,500 for a 2x target) or restate the target as the weaker guarantee.
3. **Record the measured headroom beside the target at every sprint closeout.** Do not record it against the constant alone.

> [!constraint] WRONG and CORRECT — the constant is derived from the headline, and every closeout reports against the headline
> ```
> WRONG:
> Headline: at least 2x headroom under 25,000 tokens
> <design pin>: budget 22,000 tokens per file          # permits 1.14x, never reconciled
> Sprint closeout: "<index> 15,164 tokens, 6,836 headroom (vs 22,000)"   # reported against the budget only
>
> CORRECT:
> Headline: at least 2x under 25,000  ->  file at most 12,500 tokens
> <design pin>: budget = 12,500 (derived from the headline), or headline restated as "under 22,000 per file"
> every closeout: "<index> 15,164 tokens = 1.65x (target 2x: MISSED)"
> ```

**What happened without it.** The plan's headline criterion was "reads in one `Read` call with at least 2x headroom under the 25,000-token page cap". That is a file at or below 12,500 tokens. The design set a per-file budget of 22,000 tokens, which permits 1.14x. Every size gate reported green. Each sprint closeout recorded the measured size against the budget only. The miss surfaced at the final cutover read, three sprints later. The file measured 1.60x. The cutover was held and the user accepted the miss with a follow-up. Every other criterion had passed. The one the plan was named for was unmeetable from the day the constant was chosen.

**Where it applies.** Any plan whose success criterion is a margin or ratio (headroom, a latency percentile, an error budget) while the implementation enforces a different threshold. It also applies to any closeout that reports a measurement against the implementation's threshold rather than the plan's criterion. §16.11 covers filling the signoff at sprint close. This section covers what the filled signoff must report against.

#### Reviewer Check 096 — Size Constant Cannot Meet the Plan's Headline Margin

- **Severity / Role / Type:** WARNING (HIGH confidence) | Verification-Gate Reviewer | NEW
- **What:** For each headline margin or ratio criterion, find the design constant that enforces size. Compute the constant's implied margin. Flag a constant that cannot meet the headline and states no weaker-guarantee restatement.
- **Detection:**
  1. List each headline criterion phrased as a margin or ratio (headroom, percentile, error budget).
  2. Find the design pin, budget or threshold that enforces it in the implementation.
  3. Compute the margin the constant permits in the headline's units.
  4. Constant permits less than the headline, and no sentence restates the headline as the weaker guarantee → WARNING.
  5. A closeout or signoff row that reports the measurement against the constant but not against the headline → WARNING.
- **Finding template:**
```
[WARNING] Size constant cannot meet the plan's headline margin
File: {design pin or EI path} | Location: {constant / headline criterion}
Issue: Headline requires {margin}; constant {value} permits {implied margin} and no weaker-guarantee restatement exists
Fix: Derive the constant from the headline or restate the headline, and report each closeout against the headline, per references/exit-criteria-fidelity-Part-2-DecisionLeavesCriteriaStale.md §16.14 | Confidence: HIGH
```

### 16.15 A Newest-First Numbered Record Renumbers Every Entry on Each Append

> [!constraint] An append-only record that counts identifiers from the newest end rewrites every existing identifier on each append
> An entry number then stops meaning the same entry over time. Every append also edits lines it did not add. Number from the oldest end, or key each entry by its date or another fixed value. An append then touches only the new entry. The newest entry can still sit at the top of the page.

§16.12 covers a list where an author inserts new entries by hand. This section covers a record that renumbers itself by construction. A changelog numbers its entries newest-first, so `## Entry 1` is always the latest. One append shifted three existing headings: 1 to 2, 2 to 3, and 3 to 4. A ledger that recorded "`## Entry 1 — <date>` present" then named the wrong entry. No step errored. The ledger row read as true and pointed at a different entry.

> [!constraint] WRONG and CORRECT — a stable key per entry, newest still on top
> ```
> WRONG — newest-first counter:
> ## Entry 1 — 2026-09-26   <- new
> ## Entry 2 — 2026-09-23   <- was Entry 1
> ## Entry 3 — 2026-09-19   <- was Entry 2
>
> CORRECT — a stable key per entry, newest still on top:
> ## 2026-09-26 — <title of the newest entry>
> ## 2026-09-23 — <title of the previous entry>
> ## 2026-09-19 — <title of the oldest entry shown>
> ```
> An ascending counter works as well. The oldest entry is `## Entry 1`, and the newest entry carries the highest number and sits on top. The headings then descend top to bottom, and a number never changes once assigned.

- **Until the scheme changes, cite an entry by its date or heading text.** Never cite it by its number.
- **Check the writer first.** A writer that assigns the next number and never renumbers an existing one has the stable form. A record kept by hand, or by a writer that counts from the top, has the unstable form.

**Applies to** any changelog, log, or decision record kept newest-first with numbered headings. It also applies to any ledger or evidence file that cites such an entry by number.
