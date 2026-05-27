---
name: planwise
description: >
  Agentic project management — plan, execute, review, and track projects
  with structured workflows. Use when user wants to create plans, run sessions,
  review plans, manage backlog items, or search lessons learned.
argument-hint: "<init|plan|review|run|backlog|list|lessons|help> [args]"
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
| `backlog` | Read [handlers/backlog.md](../../handlers/backlog.md) |
| `list` | Read [handlers/list.md](../../handlers/list.md) |
| `lessons` | Read [handlers/lessons.md](../../handlers/lessons.md) |
| `help` | Read [handlers/help.md](../../handlers/help.md) |

If `$0` is empty, display help (below).
If `$0` is not in the table, respond: "Unknown subcommand: {$0}. Run `/planwise` for usage."

## Help

```
Usage: /planwise <subcommand> [args]

Available subcommands:
  init                         Initialize project structure
  plan [name]                  Create a new plan
  plan --scaffold [abbrev]     Scaffold from Discovery phase
  review [plan-path]           Review plan before execution
  run [@orchestration-file]    Execute a planned session
  upgrade                      Refresh installed rules/agents after a plugin update
  backlog [item-id]            Triage backlog items; capture follow-up BLIs from resolution outputs
  list                         List all plans with status
  lessons [search-terms]       Search lessons learned
  lessons capture              Capture a lesson mid-session
  lessons promote <id>         Promote lesson to artifact
  lessons curate [--phase=X]   Categorise lessons and track promotions
  lessons promote-batch <scope>  Batch-draft promotion BBs
  help                         Show this help message
```

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

- [Markdown conventions](../../references/markdown-conventions.md)
- [Callout conventions](../../references/callout-conventions.md)
- [Agent orchestration](../../references/agent-orchestration.md)
- [Scaffolding hygiene](../../references/scaffolding-hygiene.md)
- [Discovery and exit criteria](../../references/discovery-and-exit-criteria.md)
- [EI fidelity](../../references/ei-fidelity.md)
- [Schema pin requirement](../../references/schema-pin-requirement.md)
- [Task content fidelity](../../references/task-content-fidelity.md)
- [Verification gates](../../references/verification-gates.md)
- [Verify against shipped artifact](../../references/verify-against-shipped-artifact.md)
- [Artifact self-containment](../../references/artifact-self-containment.md)
