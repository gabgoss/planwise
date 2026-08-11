---
name: planwise
description: >
  Agentic project management — plan, execute, review, and track projects
  with structured workflows. Use when user wants to create plans, run sessions,
  review plans, manage backlog items, or search lessons learned.
argument-hint: "<init|plan|review|run|upgrade|doctor|token-saver|backlog|list|lessons|help> [args]"
user-invocable: true
disable-model-invocation: false
---

# /planwise — Agentic Project Management

## Routing

Parse `$ARGUMENTS`:
- `$0` = subcommand
- Remaining = subcommand arguments (forwarded as context)

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
| `list` | Read [handlers/list.md](../../handlers/list.md) |
| `lessons` | Read [handlers/lessons.md](../../handlers/lessons.md) |
| `help` | Display the Help section below (inline) |

If `$0` is empty, display help (below).
If `$0` is not in the table, respond: "Unknown subcommand: {$0}. Run `/planwise` for usage."

## Help

```
planwise — Your AI project manager that never forgets.

Usage: /planwise <subcommand> [args]

Available subcommands:
  init                         Initialize project structure
  plan [name]                  Create a new plan
  plan --scaffold [abbrev]     Scaffold from Discovery phase
  review [plan-path]           Review plan before execution
  run [@orchestration-file]    Execute a planned session
  upgrade                      Refresh installed rules/agents after a plugin update
  doctor                       Audit rule scope + (Token Saver) overhead staleness, read-gate scan, read-limit drift
  doctor --prune-stale         Delete stale de-scoped rules flagged REMOVABLE (writer; opt-in)
  token-saver on|off|status    Toggle Token Saver mode anytime (--plan to override one plan)
  backlog [item-id]            Triage backlog items; capture follow-up BLIs from resolution outputs
  list                         List all plans with status
  lessons [search-terms]       Search lessons learned
  lessons capture              Capture a lesson mid-session
  lessons promote <id>         Promote lesson to artifact
  lessons curate [--phase=X]   Categorise lessons and track promotions
  lessons promote-batch <scope>  Batch-draft promotion BBs
  help                         Show this help message
```

> For the full user guide, visit: https://github.com/gabgoss/planwise/tree/main/plugins/planwise

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

**Loaded on demand, NOT pre-injected** — each is pulled in by the handler that needs it (see that handler's *Required References* list for the trigger), or auto-injected as a path-scoped rule on matching `.claude/**` edits. Key references (not exhaustive — handlers own the full set):

- [Scaffolding hygiene](../../references/scaffolding-hygiene.md)
- [Discovery and exit criteria](../../references/discovery-and-exit-criteria.md)
- [Exit-criteria fidelity](../../references/exit-criteria-fidelity.md)
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
- [Verify against shipped artifact](../../references/verify-against-shipped-artifact.md)
- [Verify discovery-phase consolidation](../../references/verify-discovery-consolidation.md)
- [Cross-repo fix-task discipline](../../references/verify-cross-repo-fix-discipline.md)
- [Backlog-item citation freshness](../../references/verify-backlog-citation-freshness.md)
- [Artifact self-containment](../../references/artifact-self-containment.md)
