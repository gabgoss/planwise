# planwise — Agentic Project Manager

A Claude Code plugin that brings structured project management workflows to your Claude sessions. planwise helps you plan, execute, review, and track work across sessions using a consistent file-based methodology built on markdown artifacts.

## What It Does

Software projects often lose continuity across Claude Code sessions. Context is forgotten, tasks are duplicated, and decisions are re-litigated. planwise solves this by maintaining a persistent project structure — plans, backlog items, and lessons learned — that survives session boundaries.

**Problems planwise solves:**
- Session plans are ad hoc and inconsistent across projects
- No structured way to review plans before executing them
- Backlog items accumulate without scoring, prioritization, or routing
- Lessons learned are captured informally and lost
- No standard way to track what was completed, what is pending, and what is blocked

---

## Installation

### Via Claude Plugin (recommended)

```bash
claude plugin install planwise
```

Once installed, the `/planwise` command is available in all Claude Code sessions for the project.

### Manual Setup

1. Clone or copy this directory into your project
2. Add the plugin to your `.claude/settings.json`:
   ```json
   {
     "plugins": ["./planwise"]
   }
   ```

### Initialize in a Project

After installation, run the init command to set up the project structure:

```
/planwise init
```

This creates a `planwise/` folder in your project root containing `config.yaml`, `Plans/`, `Backlog/`, and `LessonsLearned/` directories, and installs 10 path-scoped rules to `.claude/rules/planwise/`.

---

## Subcommand Reference

| Subcommand | Usage | Description |
|------------|-------|-------------|
| `init` | `/planwise init` | Initialize project configuration and seed index files |
| `plan` | `/planwise plan [name]` | Create or scaffold a new session plan interactively |
| `review` | `/planwise review [plan-path]` | Review a plan with structural and content analysis before execution |
| `run` | `/planwise run [@orchestration-file]` | Execute a planned session with task tracking and recovery |
| `backlog` | `/planwise backlog [item-id]` | Triage backlog items — score, route, and update status |
| `list` | `/planwise list` | List all plans with name, abbreviation, status, and sprint count |
| `lessons` | `/planwise lessons [args]` | Search, capture, or promote lessons learned |

### init

Sets up the project management structure for a new project. Prompts for project name and directory preferences, then creates `config.yaml`, seeds the plan index, backlog index, and lessons learned index.

### plan

Creates new session plans using structured templates. Supports two modes:
- `plan [name]` — Create a new plan from scratch, prompting for abbreviation, sprint count, and session structure
- `plan --scaffold [abbrev]` — Scaffold a full plan from a Discovery phase, building out sprints and tasks automatically

### review

Reviews a plan before execution using a two-phase agent team approach:
- **Phase 1 (structural-reviewer):** Validates file naming, cross-references, orchestration format, and plan hierarchy
- **Phase 2 (plan-reviewer):** Reviews content quality — task specs, token estimates, dependency accuracy, and success criteria

Produces a structured review report and returns an APPROVED or CHANGES REQUIRED verdict.

### run

Executes a planned session by reading an orchestration file and working through tasks in dependency order. Supports two execution modes:
- **GUIDED mode** — Orchestrator proposes each task and waits for approval
- **DELEGATED mode** — Orchestrator delegates tasks to the `task-runner` agent automatically

Maintains a recovery file throughout execution so sessions can be interrupted and resumed.

### backlog

Interactive backlog triage workflow. Reads the backlog index, presents scored and prioritized items, and routes each item to one of three paths:
- **Route A (Direct Fix)** — Small bugs delegated to the `fix-agent`
- **Route B (Task List)** — Medium scope items broken into steps and worked through using TaskCreate
- **Route C (New Plan)** — Large scope items that need their own plan

### list

Displays all plans defined in the plan index with their abbreviation, status, sprint count, and file path. Supports optional status filtering.

### lessons

Manages lessons learned across the project lifecycle:
- `/planwise lessons [search-terms]` — Search lessons by keyword
- `/planwise lessons capture` — Capture a lesson learned mid-session
- `/planwise lessons promote <id>` — Promote a lesson to a formal artifact

---

## Configuration

After running `/planwise init`, a `config.yaml` is created in your planwise root directory (default: `planwise/config.yaml`):

```yaml
project:
  name: "{project-name}"
  planwise_root: "planwise"
  # Directories below are relative to planwise_root
  plans_dir: "Plans"
  backlog_dir: "Backlog"
  lessons_dir: "LessonsLearned"
  index_files:
    plans: "00-Index-Plans.md"
    backlog: "00-Index-Backlog.md"
    lessons: "00-Index-LessonsLearned.md"

abbreviations:
  APP: "Application features"
  BUG: "Bug fixes"
  DOC: "Documentation"
  INFRA: "Infrastructure and DevOps"

lesson_abbreviations:
  TOOL: "Tool usage patterns"
  PERF: "Performance optimization"
  SEC: "Security practices"
  PROC: "Process and workflow"

scoring:
  priority_high: 30
  priority_medium: 20
  priority_low: 10
  bug_fix_bonus: 15
  blocks_bonus: 20

statuses:
  - NOT_STARTED
  - PLANNING
  - IN_PROGRESS
  - BLOCKED
  - COMPLETE
  - CLOSED

build_commands:
  default: "echo 'Configure build_commands in config.yaml'"
```

**Key fields to customize:**
- `project.name` — Your project name, used in plan file headers
- `project.planwise_root` — Root folder for all planwise files (default: `planwise`)
- `abbreviations` — Domain prefixes for plan file naming (e.g., `APP-S01`, `BUG-S02`)
- `lesson_abbreviations` — Category prefixes for lessons learned files
- `scoring` — Weight adjustments for backlog scoring algorithm
- `build_commands.default` — Command to verify builds after code changes

---

## Custom Agents

planwise ships four custom agent definitions used automatically during review and execution workflows:

| Agent | Model | Tools | Role |
|-------|-------|-------|------|
| `structural-reviewer` | Haiku | Read, Glob, Grep | Phase 1 plan review — validates file structure, naming, and cross-references |
| `plan-reviewer` | Sonnet | Read, Glob, Grep | Phase 2 plan review — deep content quality analysis with role-based review modes |
| `task-runner` | Inherit | All subagent tools | Executes individual tasks in DELEGATED run mode |
| `fix-agent` | Sonnet | All subagent tools | Applies targeted code fixes for Route A backlog items |

Agents are defined in the `agents/` directory and are auto-discovered by Claude Code when the plugin is installed.

---

## Directory Structure

### Plugin structure (in your project or plugin directory)

```
planwise/                        # Plugin root
├── .claude-plugin/
│   └── plugin.json              # Plugin manifest
├── skills/
│   └── planwise/
│       └── SKILL.md             # Router — invoked as /planwise
├── handlers/                    # Subcommand handlers (7 files)
│   ├── init.md
│   ├── plan.md
│   ├── review.md
│   ├── run.md
│   ├── backlog.md
│   ├── list.md
│   └── lessons.md
├── agents/                      # Custom agent definitions (4 files)
│   ├── structural-reviewer.md
│   ├── plan-reviewer.md
│   ├── task-runner.md
│   └── fix-agent.md
├── references/                  # Reference knowledge base (10 files)
├── templates/                   # Plan file templates (11 files)
├── seed/                        # Project init seed files (3 files)
├── scripts/                     # Python backlog utilities (7 files)
├── examples/                    # Example outputs (3 files)
└── config.yaml.template         # Config template for init
```

### Project structure (created by `/planwise init`)

```
your-project/
├── planwise/                    # Planwise root (configurable)
│   ├── config.yaml              # Project configuration
│   ├── Plans/                   # Plan folders
│   ├── Backlog/                 # Backlog items
│   └── LessonsLearned/         # Lessons learned
└── .claude/
    └── rules/
        └── planwise/            # 10 path-scoped rules (installed by init)
```

---

## License

MIT — Gabriel Gosselin
