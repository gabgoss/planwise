---
description: Detect an unnoticed project pivot before triaging an aged or high-priority backlog item, sweep the affected cohort to one shared BLOCKED disposition via the umbrella item's `blocks:` frontmatter instead of closing items individually, and gate the check to the triage passes where it pays for itself
---

# Backlog Triage: Pivot Detection

**Purpose:** An item that has sat in the backlog for a while — or that heads a cohort of siblings — can be quietly invalidated by work that happened after it was filed. Routing a pivoted item through the normal Direct-Fix / Task-List / Session-Plan flow burns a route decision on a problem that already dissolved.
**Loaded by:** the triage handler's pre-routing gate, on demand — not every triage pass (see §4 below).

---

## 1. Detection Signals

> [!practice] Check Two Cheap Signals Before Routing an Aged or High-Priority Item
> **Signal 1 — recent commits in adjacent domains.** Run `git log --oneline -20` and skim which directories the commits touch: new schema files, a new adapter family, a new plan tree. Under 30 seconds, and it reveals whether the project is mid-pivot.
>
> ```bash
> git log --oneline -20
> git log --since="{item_created_date}" --name-only --format="" | sort -u | head -40
> ```
>
> The second command is the sharper one: it answers "what has been built since this item was written?" — the exact question an aging item cannot answer about itself.
>
> **Signal 2 — implicit user signals during scope clarification.** When triage asks whether to route an item, the user's reply routinely carries strategic context the item body lacks. Ask the framing question explicitly when Signal 1 lights up:
>
> *"There's active work in {domain} since this item was filed — does {item} still match where that's heading?"*
>
> Do not treat the item body as the authority on its own relevance. It was written before the thing that invalidated it.

---

## 2. Cohort Sweep When a Pivot Is Confirmed

> [!constraint] Sweep the Cohort, Not Just the Selected Item
> Identify siblings before transitioning anything: items created near the same date, items sharing the domain abbreviation, items named in `blocks:` chains.
>
> ```bash
> grep -l "^created: {YYYY-MM}" {backlog_dir}/*.md          # same-period siblings
> grep -l "^abbrev: {ABBREV}" {backlog_dir}/*.md            # same-domain siblings
> grep -n "^blocks:" {backlog_dir}/{selected_item}          # declared dependents
> ```
>
> Propose one batch transition with a shared rationale.
>
> WRONG — transition the selected item, leave siblings at NOT_STARTED to re-surface individually:
> ```
> update_backlog.py --id {selected_item} --status BLOCKED
> # siblings untouched — each re-trips this same signal on its own next triage pass
> ```
> CORRECT — one batch transition covering the whole cohort, gating context recorded once:
> ```
> update_backlog.py --id {selected_item} --status BLOCKED
> update_backlog.py --id {sibling_id} --status BLOCKED
> generate_backlog_index.py --write
> # one shared rationale, recorded once, on the umbrella item (see §2.1)
> ```

### 2.1 Gating Mechanism

No `blocked_by:` frontmatter field exists on a backlog item — an item does not declare what blocks *it*. Instead, blocking is declared in the umbrella item's `blocks:` frontmatter, which is the **single source of truth**: the index row's `Blocks` column is its generated projection, never a place to declare blocking. The backlog parser's blocked-map builder reads that relationship from `blocks:` frontmatter, via the generated `Blocks` column — live machinery that already ships and works today.

The sweep files one **umbrella item** representing the pivot itself, and sets the umbrella item's `blocks:` frontmatter to the cohort's IDs. The existing blocked-item exclusion then hides the cohort from selectable-item output automatically — no schema change, no new frontmatter field. The umbrella item is the natural place to record the pivot's scope and its re-triage trigger.

> [!practice] Caveat — Give the Umbrella Item Its Own Disposition
> The umbrella item is itself open and will appear in triage. Route it to Session Planning as the pivot's own work, or give it a status that keeps it out of the selectable set — otherwise the sweep's own bookkeeping item re-surfaces as a normal triage candidate.

A free-text rationale field on each item was considered and rejected: it requires template, parser, and scoring changes, and it creates a second blocked-ness mechanism running alongside `blocks:` frontmatter — two ways to express the same fact, and they drift.

### 2.2 Use BLOCKED, Not CLOSED

A pivoted item is gated, not resolved. Premature closure destroys standalone value that survives the rebuild. BLOCKED plus a recorded rationale keeps the audit trail and makes the cohort recoverable when the pivot's scope lands. CLOSED means someone re-derives it from scratch later.

### 2.3 Capture Forensic Findings Before Teardown

When a pivot will demolish artifacts holding empirical findings — a measured divergence rate, a reproduced defect — file those findings before the teardown, or the rebuild can re-introduce the same failure mode with the evidence gone.

---

## 3. Triage Application Workflow

> [!checklist] Pivot-Detection Workflow
> - [ ] Run `git log --oneline -20`, skim for domains adjacent to the selected item
> - [ ] If the item predates recent activity in its domain, list what has been built since its `created` date
> - [ ] If a signal lights up, ask the user the framing question before scope-assessing for routing
> - [ ] If a pivot is confirmed, sweep the cohort and propose one batch BLOCKED transition with a shared rationale
> - [ ] Capture any forensic findings the pivot will destroy, as separate items, before transitioning

---

## 4. When This Applies

> [!decide] Applicability Gates
> Run the detection signals when:
> - The item's priority is High, or its computed score is in the top band
> - The item was authored well before the current triage pass — the staler the item, the cheaper the check relative to the risk
> - The item is part of a multi-item cohort: siblings created within days of each other, or joined by `blocks:` chains
>
> Skip it otherwise: the signals are cheap but not free, and a freshly-filed item cannot have been pivoted out from under itself.

---

## 5. A Permission-Change Deliverable Is Not Agent-Executable

> [!constraint] Authorization to do the work is not authorization to change what the agent may do
> A user who selects a route, answers a routing prompt and types "go" grants item-level consent. The harness separately gates any change to the permission configuration. An agent that can widen its own rules can widen them in directions nobody approved. That gate firing is correct behavior, not a fault to route around.

A backlog item's whole deliverable was a one-character widening of a `permissions.deny` entry. The item was fully specified and explicitly authorized. The harness still refused the `Edit` of the settings file. It then refused a read-only hash of the same file. It then refused a child-process probe whose command string named the file. Every refusal came from a layer above the entry under test, and only a human could approve the change.

Three routing consequences follow.

- **It is not delegable to a fix-agent.** A spawned subagent meets the same gate with less ability to explain the block or to obtain consent. It is also subject to whatever rule it just installed. Direct-fix delegation is the wrong route for this item class, however small and well specified the edit is.
- **It cannot run under Auto Mode or unattended.** A workflow that assumes the whole item completes without a consent channel stalls at exactly one step, after the preparation is done.
- **The block radiates to neighbouring reads.** Once the gate engaged on the settings path, an ordinary read-only hash of the same file was refused, and so was a child-process probe whose command string contained the path. Budget for reads about the control being blocked, not only writes to it. Use the native `Read` tool, not a shell equivalent.

**Sequence the blocked step last.** Build everything that does not need the changed permission first: fixtures, the probe harness, a discrimination proof against the current setting, and the recorded revert line. Then the human's approval is followed by minutes of measurement, not by setup. This matters most when the installed state can disrupt other sessions.

> [!constraint] A refusal is a consent gap, not a capability gap
> WRONG — the edit is denied, so land the same byte change through a tool the gate did not flag:
> ```
> Edit <settings-file>                  -> refused
> python -c "...write the same bytes"   -> succeeds, gate defeated
> The refusal text invites using another tool, and a shell write is another tool.
> That reading is wrong here. The gate's intent is that a human approves permission
> changes. A path that lands the bytes without one defeats that intent.
> The permitted workarounds are for capability gaps, not for consent gaps.
> ```
> CORRECT — stop, and hand the decision to the human who can grant it:
> ```
> Edit <settings-file> -> refused
> -> state exactly what was being changed, and why
> -> give the precise diff and the precise revert
> -> let the user apply it, or approve the edit
> ```

**Applies to** triaging or routing any item whose deliverable edits a permissions block (deny, allow, additional directories) or any other file that governs what the agent may do. It also applies to any Auto Mode or unattended workflow that lists a permission change among its tasks. Route such an item to the user as a hand-off, not to a fix-agent.

---

*Related: [backlog-schema.md](backlog-schema.md) for the backlog index's table format, including the generated `Blocks` column this mechanism's `blocks:` frontmatter projects into.*
