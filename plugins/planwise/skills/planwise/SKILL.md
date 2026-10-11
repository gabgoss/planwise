---
name: planwise
description: >
  Agentic project management — plan, execute, review, and track projects
  with structured workflows. Use when user wants to create plans, run sessions,
  review plans, manage backlog items, or search lessons learned.
argument-hint: "<init|plan|review|run|upgrade|doctor|token-saver|backlog|list|lessons|feedback|harvest|help> [args]"
arguments: sub
user-invocable: true
disable-model-invocation: false
allowed-tools: Bash(python -B "${CLAUDE_PLUGIN_ROOT}/scripts/skill_preflight.py" *)
---

# /planwise — Agentic Project Management

## Routing

Parse `$ARGUMENTS`:
- `$0` = subcommand
- Remaining = subcommand arguments (forwarded as context)

The shell line below runs before you see this prompt. Its output replaces the line.

!`python -B "${CLAUDE_PLUGIN_ROOT}/scripts/skill_preflight.py" '$sub' || true`

The injected line above also prints a `planwise: …` version notice when the config pin differs from this plugin. Pass any such line to the user verbatim before routing.

| Subcommand | Handler |
|-----------|---------|
| `init` | Read [handlers/init.md](../../handlers/init.md) |
| `plan` | Read [handlers/plan.md](../../handlers/plan.md) |
| `review` | Read [handlers/review.md](../../handlers/review.md) |
| `run` | Read [handlers/run.md](../../handlers/run.md) |
| `upgrade` | Read [handlers/upgrade.md](../../handlers/upgrade.md) |
| `doctor` | Read [handlers/doctor.md](../../handlers/doctor.md) |
| `token-saver` | Read [handlers/token-saver.md](../../handlers/token-saver.md) |
| `backlog` | Read [handlers/backlog.md](../../handlers/backlog.md) |
| `list` | Follow [List](#list) below (normally zero tool calls) |
| `lessons` | Read [handlers/lessons.md](../../handlers/lessons.md) |
| `feedback` | Read [handlers/feedback.md](../../handlers/feedback.md) |
| `harvest` | Read [handlers/harvest.md](../../handlers/harvest.md) |
| `help` | Display the Help section below (inline) |

If `$0` is empty, display help (below).
If `$0` is not in the table, respond: "Unknown subcommand: {$0}. Run `/planwise` for usage."

## List

The shell line under Routing renders the `list` answer before you run. Check rule 5 first, then apply the first of rules 1-3 that matches.

1. **Block present, no fallback line.** Display everything between `<!-- planwise:list:begin -->` and `<!-- planwise:list:end -->` verbatim as the whole answer, after any `planwise:` notice line. Run nothing. If the banner reports drift, add one sentence offering to reconcile, and wait.
2. **A `PLANWISE_LIST_FALLBACK:` line is present.** Answer by its cause:
   - `config.yaml not found`: say no planwise `config.yaml` was found in that directory, and tell the user to run `/planwise init`. Never initialise from `list`.
   - `config.yaml parse error`: fail loud with `config.yaml parse error at {path}: {error}. Fix or delete the file before running /planwise list.` Then stop.
   - `Plans index not found`: print the line. Suggest `generate_plans_index.py --write` to generate it from the Master Plans, or a check of `config.yaml`.
   - Any other cause: print the line.
3. **No block at all, or the line reads `[shell command execution disabled by policy]`.** Run this command once with Bash. Copy it byte for byte and add only the flags the user typed. Apply rules 1 and 2 to its output. Do not Read any file.

   ```
   python -B "${CLAUDE_PLUGIN_ROOT}/scripts/skill_preflight.py" list
   ```

4. **Reconcile on consent.** The writer is `reconcile_plans.py --write`, and it regenerates the whole plans index. Run it only after the user agrees. A permission prompt on this path is acceptable. [handlers/list.md](../../handlers/list.md) gives the exit-code meanings.
5. **Typed flags.** If the `ARGUMENTS:` line holds `--active` or `--no-check`, ignore any injected block. The shell line passes only the subcommand, so that block is unfiltered and always checked. Take the one-call route of rule 3 with those flags.

## Help

```
planwise — Your AI project manager that never forgets.

Usage: /planwise <subcommand> [args]

Available subcommands:
  init                         Initialize project structure
  plan [name]                  Create a new plan
  plan --scaffold [abbrev]     Scaffold from Discovery phase
  review [plan-path]           Review plan before execution
  run [@orchestration-file] [--resume]  Execute a planned session
                               --resume skips the start approval on a proven mid-session resume
  upgrade                      Refresh installed rules/agents after a plugin update
  doctor                       Audit install health — version gate, rule scope,
                               stale/diverged rules, orphaned agent mirrors, index drift,
                               feedback capability, upgrade leftovers, and (Token Saver)
                               overhead staleness, read-gate scan, read-limit drift
  doctor --prune-stale         Delete stale de-scoped rules flagged REMOVABLE (writer; opt-in)
  doctor --prune-upgrade-leftovers  Delete past-upgrade backups and caches flagged prunable (writer; opt-in)
  doctor --create-feedback-dir Create the missing feedback drafts directory (writer; opt-in)
  token-saver on|off|status    Toggle Token Saver mode anytime (--plan to override one plan)
  backlog [item-id] [--loop-resume <run-id>]  Triage backlog items; capture follow-up BLIs from resolution outputs
                               --loop-resume re-enters a one-item-per-session loop (needs the plugin's hooks module)
  list [--active] [--no-check] List all plans with status
  lessons [search-terms]       Search lessons learned
  lessons capture              Capture a lesson mid-session
  lessons promote <id>         Promote lesson to artifact
  lessons curate [--phase=X]   Categorise lessons and track promotions
  lessons promote-batch <scope>  Batch-draft promotion BBs
  feedback [bug|lesson|idea]   Report a planwise bug, lesson, or idea upstream
  feedback --status            Show each local draft and whether it was posted
  feedback --sweep             Archive drafts already posted (asks first; never deletes)
  harvest [<scope>] [--dry-run] [--resume] [--max-items=N] [--include-existing] [--no-auto-approve]
          Run the lesson-to-artifact chain end to end, unattended.
  help                         Show this help message
```

> For the full user guide, visit: https://github.com/gabgoss/planwise/tree/main/plugins/planwise

> Found a bug or have an idea? Run `/planwise feedback`, or open an issue at https://github.com/gabgoss/planwise/issues

## Argument Forwarding

| In SKILL.md | In Handler | Example |
|-------------|-----------|---------|
| `$0` | subcommand name (consumed by router) | `plan` |
| `$1` | handler's first argument | `MyPlan` |
| `$2` | handler's second argument | `--meta` |
| `$ARGUMENTS` | full original string | `plan MyPlan --meta` |

ARGUMENTS: $ARGUMENTS

---

## Base Context

**Pre-injected with this skill** — apply to every subcommand (mirrored by each handler's **Base references** note):

- [Markdown conventions](../../references/markdown-conventions.md)
- [Callout conventions](../../references/callout-conventions.md)
- [Agent orchestration](../../references/agent-orchestration.md)
- [Do the hard things](../../references/do-the-hard-things.md) — the project motto: favor the coherent, complete treatment over the easy partial one; effort is never the tiebreaker
- [Native tool use](../../references/native-tool-use.md) — dedicated file tools (Read/Grep/Glob/Edit/Write) over shell equivalents for file-tree reads, searches, and edits; scoped, not a blanket shell prohibition

**Loaded on demand, NOT pre-injected** — each is pulled in by the handler that needs it (see that handler's *Required References* list for the trigger), or auto-injected as a path-scoped rule on matching `.claude/**` edits. Key references (not exhaustive — handlers own the full set):

- [Scaffolding hygiene](../../references/scaffolding-hygiene.md) — §1–§12, what the scaffold emits
- [Scaffolding hygiene — Part 2: derivation and parallelism](../../references/scaffolding-hygiene-Part-2-DerivationAndParallelism.md) — §13–§19, what the scaffold must compute before it closes
- [Discovery and exit criteria](../../references/discovery-and-exit-criteria.md)
- [Exit-criteria fidelity](../../references/exit-criteria-fidelity.md)
- [Exit-criteria fidelity, Part 2 — a decision rewrites the criteria that depend on it](../../references/exit-criteria-fidelity-Part-2-DecisionLeavesCriteriaStale.md)
- [Execution-time binding rules](../../references/execution-time-binding-rules.md)
- [EI fidelity](../../references/ei-fidelity.md)
- [EI citation and token reconciliation](../../references/ei-citation-and-token-reconciliation.md)
- [EI completeness](../../references/ei-completeness.md)
- [EI source-promise integrity](../../references/ei-source-promise-integrity.md)
- [Schema pin requirement](../../references/schema-pin-requirement.md)
- [Task content fidelity](../../references/task-content-fidelity.md)
- [Verify-before-cite](../../references/verify-before-cite.md)
- [Verification gates](../../references/verification-gates.md)
- [Measurement discipline](../../references/measurement-discipline.md)
- [Measurement discipline, Part 3 — recorded delta and pinned count](../../references/measurement-discipline-Part-3-RecordedDeltaAndPinnedCount.md)
- [Verify against shipped artifact](../../references/verify-against-shipped-artifact.md)
- [Verify discovery-phase consolidation](../../references/verify-discovery-consolidation.md)
- [Cross-repo fix-task discipline](../../references/verify-cross-repo-fix-discipline.md)
- [Backlog-item citation freshness](../../references/verify-backlog-citation-freshness.md)
- [Artifact self-containment](../../references/artifact-self-containment.md)
