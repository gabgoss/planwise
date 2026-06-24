# Handler: /planwise help

**Purpose:** Display available commands and link to the full user guide.

---

## Workflow

Display the following to the user:

```
planwise — Your AI project manager that never forgets.

Available commands:
  /planwise init                         Initialize project structure
  /planwise plan [name]                  Create a new plan
  /planwise plan --scaffold [abbrev]     Scaffold from Discovery phase
  /planwise review [plan-path]           Review plan before execution
  /planwise run [@orchestration-file]    Execute a planned session
  /planwise upgrade                      Refresh installed rules/agents after a plugin update
  /planwise doctor                       Audit rule scope + (Token Saver) overhead staleness, read-gate scan, read-limit drift
  /planwise token-saver on|off|status    Toggle Token Saver mode anytime (--plan to override one plan)
  /planwise backlog [item-id]            Triage backlog items; capture follow-up BLIs from resolution outputs
  /planwise list                         List all plans with status
  /planwise lessons [search-terms]       Search lessons learned
  /planwise lessons capture              Capture a lesson mid-session
  /planwise lessons promote <id>         Promote lesson to artifact
  /planwise lessons curate [--phase=X]   Categorise lessons and track promotions
  /planwise lessons promote-batch <scope>  Batch-draft promotion BBs
  /planwise help                         Show this help message
```

Then display:

> For the full user guide, visit: https://github.com/gabgoss/planwise/tree/main/plugins/planwise
