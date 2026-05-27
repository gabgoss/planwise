# planwise

**Your AI project manager that never forgets.**

planwise is a plugin for [Claude Code](https://docs.anthropic.com/en/docs/claude-code) that helps you plan, execute, review, and track your work across sessions. It keeps everything organized in simple markdown files so nothing gets lost between conversations.

## Table of contents

- [Initialize planwise](#step-1--initialize-planwise-in-your-project)
- [Start using planwise](#step-2--start-using-planwise)
  - [Create a plan](#create-a-plan)
  - [Review a plan](#review-a-plan-before-executing-it)
  - [Execute a plan](#execute-a-plan)
  - [Manage your backlog](#manage-your-backlog)
  - [List all plans](#list-all-your-plans)
  - [Lessons learned](#work-with-lessons-learned)
  - [Get help](#get-help)
- [Quick reference](#quick-reference)
- [How it works under the hood](#how-it-works-under-the-hood)
- [Updating planwise](#updating-planwise)
- [Uninstalling](#uninstalling)
- [Troubleshooting](#troubleshooting)

---

### The problem

Ever had Claude Code forget what you were working on? Started a new session and had to re-explain everything? Watched tasks pile up with no way to prioritize them?

**planwise fixes that.** It gives your projects a persistent memory — structured plans, scored backlogs, and lessons learned that survive across every session.

---

## Step 1 — Initialize planwise in your project

Navigate to the project you want to manage, open Claude Code there, and run:

```
/planwise init
```

Claude will ask you a few questions:

1. **Project name** — just type your project's name (e.g., `my-cool-app`)
2. **Planwise root directory** — where to store planwise files (default: `planwise/` in your project root — just press Enter to accept)
3. **Directory names** — for Plans, Backlog, and Lessons Learned (defaults are fine)

Once done, you'll see a new folder structure in your project:

```
your-project/
  planwise/
    config.yaml          <-- your project settings
    Plans/               <-- where session plans live
    Backlog/             <-- where tracked items go
    LessonsLearned/      <-- where insights are saved
  .claude/
    rules/
      planwise/          <-- 17 path-scoped rules that help Claude work with your plans
```

> **You only need to run `init` once per project.** After that, planwise remembers your setup.

#### How `init` works

```mermaid
flowchart LR
    A([Run command]) --> B[Answer a few<br/>questions]
    B --> C[planwise creates<br/>folders &amp; config]
    C --> D([Ready to use])
```

---

## Step 2 — Start using planwise

Here's what you can do now. Each command starts with `/planwise` followed by a subcommand.

---

### Create a plan

```
/planwise plan my-new-feature
```

This walks you through creating a structured session plan. Claude will ask about:
- What abbreviation to use (like `APP` for app features, `BUG` for bug fixes)
- How many sprints you need
- What tasks go in each session

Your plan gets saved as organized markdown files you can review anytime.

> **What's a sprint?** A group of related work sessions. If your feature is small, one sprint with one session is enough. Bigger features might need multiple sprints.

**Scaffold from an existing Discovery phase:**

```
/planwise plan --scaffold APP
```

This takes a Discovery plan you've already written and automatically builds out all the sprints and tasks from it.

#### How `plan` works

```mermaid
flowchart LR
    A([Run command]) --> B[Describe your<br/>plan &amp; sprints] --> C[Plan files<br/>created] --> D([Ready to run])
```

---

### Review a plan before executing it

```
/planwise review
```

This sends your plan through a two-phase AI review:

1. **Structural review** — checks that files are named correctly, links aren't broken, and the plan hierarchy makes sense
2. **Content review** — checks task quality, token estimates, dependencies, and success criteria

You'll get a report with an **APPROVED** or **CHANGES REQUIRED** verdict.

> **Why review?** Catching problems in a plan is much cheaper than catching them mid-execution. Think of it like proofreading before you hit send.

#### How `review` works

```mermaid
flowchart LR
    A([Run command]) --> B[AI checks<br/>structure] --> C[AI checks<br/>content] --> D([Get verdict])
```

---

### Execute a plan

```
/planwise run
```

This starts working through your planned tasks in order. You get two modes:

- **GUIDED mode** — Claude proposes each task and waits for your OK before doing it (recommended for your first time)
- **DELEGATED mode** — Claude works through tasks automatically using a task-runner agent

If you need to stop mid-session, don't worry — planwise saves a recovery file so you can pick up exactly where you left off.

#### How `run` works

```mermaid
flowchart LR
    A([Run command]) --> B[Confirm to start] --> C[Work through<br/>tasks] --> D[Get summary] --> E([Done])
```

---

### Manage your backlog

```
/planwise backlog
```

Opens an interactive view of all your tracked items, scored and prioritized. For each item, you choose a route:

| Route | When to use | What happens |
|-------|-------------|--------------|
| **A — Direct Fix** | Small bugs, quick changes | An AI agent fixes it right away |
| **B — Task List** | Medium scope work | Breaks it into steps and works through them |
| **C — New Plan** | Large features or overhauls | Creates a full plan for it |

**Filter your backlog:**

```
/planwise backlog --priority High
/planwise backlog --status IN_PROGRESS
/planwise backlog BUG-042
```

#### How `backlog` works

```mermaid
flowchart LR
    A([Run command]) --> B[See prioritized<br/>items] --> C[Pick an item] --> D[AI works on it] --> E([Approve &amp; close])
```

---

### List all your plans

```
/planwise list
```

Shows a table of every plan in your project with its status, sprint count, and when it was created.

#### How `list` works

```mermaid
flowchart LR
    A([Run command]) --> B[See table of<br/>all your plans]
```

---

### Work with lessons learned

**Search your lessons:**
```
/planwise lessons database migration
```

**Capture a lesson mid-session:**
```
/planwise lessons capture
```

**Promote a lesson to a formal rule:**
```
/planwise lessons promote LL-003
```

**Curate lessons — categorise new ones and track promotions:**
```
/planwise lessons curate
/planwise lessons curate --phase=categorize
/planwise lessons curate --phase=promote
```

Curate runs two phases against your lesson set. Phase 1 sorts uncategorised lessons into the domain buckets defined in `config.yaml` (Database, Application Code, Process, Tooling — customisable). Phase 2 finds lessons you've already promoted to rules or applied to code, verifies the destination artifact exists, and logs each one in the Rule Promotion Log inside your lessons index. Run `--phase=both` (the default) to do both at once, or scope to just one phase.

**Batch-draft promotion plans for a whole bucket:**
```
/planwise lessons promote-batch --category=A
/planwise lessons promote-batch LL-052,LL-053,LL-054
/planwise lessons promote-batch --all-documented
/planwise lessons promote-batch --category=A --dry-run
```

Where `/planwise lessons promote LL-003` promotes one lesson immediately, `promote-batch` plans the promotion of many lessons at once — grouping them by domain bucket and drafting backlog items (BBs) that describe the rules to be created, with the WRONG/CORRECT examples from each lesson inlined. Execution happens later via `/planwise backlog`. Add `--dry-run` to see the grouping plan without writing any files.

> **What are lessons learned?** When something goes wrong (or right!), planwise can capture that insight so you don't repeat mistakes or forget what worked.

> **Curate before you batch-promote.** `promote-batch` will refuse to run if any lessons in the master index aren't yet categorised. Run `/planwise lessons curate --phase=categorize` first to keep the bucketing file in sync.

#### How `lessons` works

```mermaid
flowchart LR
    A([Run command]) --> B[Search, capture,<br/>promote, curate,<br/>or batch-draft] --> C([Done])
```

---

### Get help

```
/planwise help
```

Shows all available commands at a glance and links to this full user guide.

#### How `help` works

```mermaid
flowchart LR
    A([Run command]) --> B[See command list<br/>&amp; docs link]
```

---

## Quick reference

| Command | What it does |
|---------|-------------|
| `/planwise init` | Set up planwise in your project (once) |
| `/planwise plan [name]` | Create a new session plan |
| `/planwise plan --scaffold [abbrev]` | Build a plan from a Discovery phase |
| `/planwise review` | AI-review a plan before running it |
| `/planwise run` | Execute a planned session |
| `/planwise backlog` | Triage and work on backlog items |
| `/planwise list` | See all plans and their status |
| `/planwise lessons` | Search the lessons learned index |
| `/planwise lessons capture` | Capture a lesson mid-session |
| `/planwise lessons promote <id>` | Promote one lesson to a rule/skill/hook/agent |
| `/planwise lessons curate [--phase=X]` | Categorise new lessons and log promotions |
| `/planwise lessons promote-batch <scope>` | Plan promotion of many lessons as backlog items |
| `/planwise help` | Show available commands and link to user guide |

---

## How it works under the hood

planwise is built entirely on markdown files and Python scripts — no databases, no servers, no external services. Everything lives in your project folder and gets version-controlled with your code.

### Custom agents

planwise uses four specialized AI agents behind the scenes:

| Agent | What it does |
|-------|-------------|
| **structural-reviewer** | Validates plan file structure, naming, and cross-references |
| **plan-reviewer** | Deep content review — task specs, estimates, dependencies |
| **task-runner** | Executes individual tasks during plan runs |
| **fix-agent** | Applies targeted code fixes for small backlog items |

You don't need to interact with these directly — they're called automatically when you use `/planwise review`, `/planwise run`, and `/planwise backlog`.

### Configuration

After running `/planwise init`, your settings live in `planwise/config.yaml`. Here are the key things you might want to customize:

| Setting | What it controls | Default |
|---------|-----------------|---------|
| `project.name` | Your project name (used in headers) | Set during init |
| `abbreviations` | Category prefixes for plans (APP, BUG, etc.) | 4 defaults |
| `scoring` | How backlog items are scored and ranked | Sensible defaults |
| `build_commands.default` | Command to verify builds after changes | `echo '...'` |

### Plugin file structure

```
planwise/                           # Plugin root
  .claude-plugin/
    plugin.json                     # Plugin identity
    marketplace.json                # Marketplace catalog
  skills/planwise/SKILL.md          # The /planwise command router
  handlers/                         # 8 subcommand handlers (init, plan, review, run, backlog, list, lessons, help)
  agents/                           # 4 custom AI agents (auto-mirrored into project .claude/agents/ on init)
  references/                       # 20 knowledge base documents (17 installed as path-scoped rules + 3 lessons-workflow helpers consumed inline)
  templates/                        # 13 markdown templates
  seed/                             # Index file seeds for init
  scripts/                          # 7 Python backlog utilities
  examples/                         # Sample outputs
  config.yaml.template              # Config template
```

---

## Changelog

### 1.2.0 (PPU remediation)

This release closes the gaps surfaced by the 2026-05-22 external-feedback audit. The 1.1.0 release shipped the enforcement layer (reviewer checks, role wiring) ahead of the rule prose it referenced; v1.2.0 authors the missing rule prose, repoints every dangling reviewer citation, ships the two reserved project-agnostic references, and applies the two divergence decisions. The "all 16 Consolidated Context parts implemented" criterion that 1.1.0 over-claimed (audit C1) is closed only with this release.

**Missing rule-body sections authored:**

- `references/task-content-fidelity.md` §9.A.4-7 + §9.B.6-9 — §9.B reframed for generic external contracts per PLG-004; 2 missing §9.A.3 rate rows added per P5-2
- `references/ei-fidelity.md` §3.1 (`paths_consume_first` schema) + §8.1 (bidirectional consistency)
- `references/scaffolding-hygiene.md` §8 + §9 + §10 — parallel-scaffold deviation classes (PLG-011)
- `references/schema-pin-requirement.md` §3.1
- `references/discovery-and-exit-criteria.md` §17 (design-extension) + §18 (audit-triage) + §16.3 (BLI-cited-anchor re-verification — PLG-019)
- `references/callout-conventions.md` — PLG-007 S4 Sequential Chain pattern + new `> [!chain-halt]` callout type
- `references/session-plan-requirements.md` — §B Selective Helper Enumeration (PLG-010)
- `references/agent-orchestration.md` §11.13 PLG-020 shared-target matrix restored (Option A cap-at-4 / Option B shards / Option C orchestrator-reconciled — PREFERRED); §11.14 Orchestrator-Only Review Commands + §11.15 Delegated Code Task-Runners Build LAST (LL-057, project-agnostic); §11 hierarchy normalised (ToC entries; H3 promotions; §7→§11.7 cross-link added)

**Dangling-reference defect closed (audit §0):**

Every `§N.M` citation across `agents/plan-reviewer.md`, `handlers/review.md`, `templates/task-file.md`, and `references/session-plan-requirements.md` now resolves to an authored section. 49/49 `plan-reviewer.md` citations verified resolved. The C2 / C5 "Sprint-03 COMPLETE-by-count-not-enforceability" defect is closed.

**New references:**

- `references/verification-gates.md` — IPC / protocol / codec round-trip evidence requirement (generalised from RevitWise round-trip-gate + LL-052; 122 lines, project-agnostic)
- `references/verify-against-shipped-artifact.md` — cross-sprint + cross-version symbol verification; §6 Discovery-phase citation + SDK-premise verification (LL-054 folded in; 532 lines, project-agnostic)
- `references/webfetch-registry-fallbacks.md` — recorded **JUSTIFIED-SKIP *low-value*** (kernel too thin + wrong-domain + no enforcement layer). Stub removed from `scripts/init_project.py` / `handlers/init.md` / README. Slot permanently retired (not deferred).

**Divergence decisions:**

- **PLG-003 enforcement severity** — raised WARNING → BLOCKING for runnable-artifact tasks. Source PLG-003 §3C called BLOCKING; the v1.2.0 population infrastructure (`templates/task-file.md` Per-File-Type table + `handlers/plan.md` Step 8e Populate Verification Commands) makes the constraint coherent; the `<!-- VERIFICATION: not-applicable (reason) -->` HTML-comment escape hatch covers legitimate doc/decision-only exemptions. Applied to `references/session-plan-requirements.md` enforcement table + `handlers/review.md` rows 34/35/36.
- **`--scaffold-per-sprint`** — recorded **JUSTIFIED-SKIP *out-of-remediation-scope***. The full per-Exec-sprint Scaffold-session resume mechanism is a new feature beyond remediation scope; the shipped pause-between-sprints behavior is accurately documented in `handlers/plan.md` (no over-claim, no README correction required). Added `> [!practice] Scope — Pause-Between-Sprints, Not Per-Sprint Scaffold Sessions` block to `handlers/plan.md` so the intentional simplification is visible to future maintainers.

**Wiring gaps closed:**

- `templates/orchestration.md` — `**Prerequisite:**` field added under `Status:` (PLG-001 §14.6)
- `templates/task-file.md` — DELEGATED retry-limited error-recovery line under "Notes for Agent"
- `skills/planwise/SKILL.md` — Base Context list extended with the 7 new references (3 → 10 entries; all resolve)
- `skills/planwise/SKILL.md` + `handlers/help.md` — follow-up-BLI-capture help line for `backlog` (PLG-018 §18.3)
- `handlers/plan.md` — `Outputs/.gitkeep` emitted for every session folder (Scaffolding Step 5); new Step 8e Populate Verification Commands from per-file-type command map (PLG-003 §3C)
- `handlers/review.md` — Error Pattern Catalog completed; collapsed PLG-020 row 17 expanded into 8 checks
- `scripts/init_project.py` — `install_rules()` reconciled; "pending user confirmation" comment removed; all 17 tuples map to existing files; `init_project.py --name SmokeTest` runs warning-free
- `handlers/init.md` — Step 6 header count reconciled to 17; Step 10 banner hedges removed for `verification-gates.md` and `verify-against-shipped-artifact.md`

**Lessons folded in:**

- **LL-052** — folded into `references/verification-gates.md` as `> [!practice]` (round-trip evidence as sprint exit-gate)
- **LL-054** — folded into `references/verify-against-shipped-artifact.md` §6 with `> [!constraint]` (WRONG: silent laundering of stale `file:line` + verified-false delegate-only premise → CORRECT: verified position + prominent task-brief premise correction) + operational rule for multi-task Discovery sessions + `> [!practice]` enforcing prominent (non-silent) corrections
- **LL-057** — folded into `references/agent-orchestration.md` §11.14 (Orchestrator-Only Review Commands) + §11.15 (Delegated Code Task-Runners Build LAST); both `> [!constraint]`, project-agnostic (`{build-cmd}` placeholder + "review lenses" generic phrasing)

**1.1.0 reconciliation (no over-claims):**

- "Pending user confirmation" hedges on `verification-gates.md` and `verify-against-shipped-artifact.md` removed from README and `handlers/init.md` — both files ship.
- Reference count reconciled: `references/` holds 20 files (17 installed as path-scoped rules + 3 lessons-workflow helpers consumed inline by lessons handlers). The 1.1.0 "18 (10 baseline + 5 confirmed + 3 pending)" count is corrected here.
- PPU Disposition Ledger marked **RESOLVED** — every recommendation in the source corpus carries an explicit verdict (IMPLEMENT, ALREADY COMPLETE, or JUSTIFIED-SKIP with a fixed-taxonomy reason).

### 1.1.0 (PPU initial release)

> **Note (added in 1.2.0):** The 1.1.0 release shipped the enforcement layer (reviewer checks, role wiring) ahead of the rule prose it referenced. The 2026-05-22 external-feedback audit identified the gap; v1.2.0 closes it. The original 1.1.0 entries are preserved below; the "pending user confirmation" hedges have been removed (those references now ship), and the `webfetch-registry-fallbacks.md` slot was retired in v1.2.0 (JUSTIFIED-SKIP *low-value*).

**New reference files** (7 shipped — `webfetch-registry-fallbacks.md` retired in v1.2.0):

- `references/ei-fidelity.md` — Execution Input fidelity (§3.1 + §8 authored in v1.2.0)
- `references/task-content-fidelity.md` — Task content fidelity §9.A + §9.B (§9.A.4-7 + §9.B.6-9 authored in v1.2.0)
- `references/schema-pin-requirement.md` — Schema Pin requirement for SQL-emitting tasks (§3.1 authored in v1.2.0)
- `references/discovery-and-exit-criteria.md` — Discovery scope rigor + cross-layer exit-criteria fidelity (§17 + §18 authored in v1.2.0)
- `references/scaffolding-hygiene.md` — Six binding rules for plan scaffolding (§8 + §9 + §10 authored in v1.2.0)
- `references/verification-gates.md` — IPC / protocol / codec round-trip evidence requirement (file authored in v1.2.0)
- `references/verify-against-shipped-artifact.md` — Cross-sprint + cross-version symbol verification (file authored in v1.2.0)

**New template:**

- `templates/sprint-signoff.md` — Sprint signoff template with EI exit-criteria verbatim quote + mechanical anchors + gate verdict + round-trip evidence

**Handler enhancements:**

- `handlers/plan.md` — Pre-Scaffold CONFIRM blocks at Discovery Step 1 + Scaffolding Step 1; multi-tier Discovery extraction (Tier 1 + Tier 2 + Tier 3); new `--scaffold-per-sprint` flag; Deferred / Out-of-Scope log per sprint; Auto-Init Fallback Config Gate; Auto-Mode tags at 14 critical + 2 convenience AskUserQuestion sites
- `handlers/review.md` — Namespaced agent spawns (`planwise:plan-reviewer`, `planwise:structural-reviewer`) at 7 spawn sites; ~12 new Error Pattern Catalog entries; Required References extended with 4 new conditional loads; Auto-Init Fallback Config Gate
- `handlers/run.md` — Namespaced `task-runner` spawns at 4 sites; Phase 4.3 user-action-gate check; Auto-Init Fallback Config Gate; Auto-Mode tags at 3 critical + 1 convenience sites
- `handlers/backlog.md` — Namespaced `fix-agent` spawn at 1 site; new Phase 7 FOLLOW-UP BLI CAPTURE (auto-files actionable recommendations from resolution Outputs); existing Phase 7 renumbered to Phase 8; Auto-Init Fallback Config Gate; Auto-Mode tags at 2 critical + 3 convenience sites
- `handlers/init.md` — Step 6 Rules table extended with 7 new reference rows (count reconciled to 17 in v1.2.0); NEW Step 6b agent mirroring; NEW `## Called As Subroutine` section documenting `--auto-from` subroutine contract; Step 10 banner updated to include Agents mirrored section
- `handlers/list.md` — Auto-Init Fallback Config Gate (no other substantive changes)
- `handlers/lessons.md` — Auto-Init Fallback Config Gate + Auto-Mode tags at 4 critical sites *(applied AFTER LCP-S03 merges)*

**Agent enhancements** (covered in separate consolidation parts):

- `agents/plan-reviewer.md` — Role checklists extended with ~50+ new BLOCKING / ERROR / WARNING checks (PLG-001..022 + Markuup + BB-028/031/032)
- `agents/structural-reviewer.md` — Folder-count check; Outputs/.gitkeep presence check; sequential-sprint prerequisite check

**Template enhancements:**

- `templates/task-file.md` — `Cross-Sprint Refs:` header field; Schema Pin subsection; Field Mapping subsection (MERGE/upsert); USED-Helper Enumeration subsection; Verification Commands section; `~?` placeholder prohibition constraint
- `templates/orchestration.md` — Scaffolding CONFIRM block placeholder; NEW DELEGATED Mandatory Triggers Reminder; updated Context Boundary callout (`> [!constraint]` form)

**Reference enhancements** (covered in separate consolidation parts):

- `references/agent-orchestration.md` — New §5 plugin-handler-spawn pitfall callout (PLG-017); §10 background-write hazard row; new §11 DELEGATED Dispatch Discipline (13 subsections); LSP-diagnostic-verification subsection; Large-File Read Tactics subsection
- `references/session-execution-protocol.md` — Discovery / Meta-Plan Status with user-action gates
- `references/session-plan-requirements.md` — Multi-tier Discovery extraction; EI bidirectional consistency; cross-sprint dependency mirroring; post-scaffold back-propagation; module split threshold; declarative follow-up block convention
- `references/callout-conventions.md` — New `> [!chain-halt]` callout type (PLG-007 S4)

**Auto-Init Fallback & Auto Mode Policy:**

- All 7 handlers receive Config Gate fallback subroutines (`plan`, `review`, `run`, `backlog`, `list`, `init`; `lessons` deferred to LCP merge)
- Per-handler AskUserQuestion call sites tagged with `<!-- AUTO-MODE: critical -->` or `<!-- AUTO-MODE: convenience -->` comments (24 critical + 13 convenience tags total)
- New `## 4b. Auto Mode Policy` section in `references/skill-authoring.md` documenting critical/convenience taxonomy + inference defaults
- New `install_agents()` function in `scripts/init_project.py` mirrors plugin agents into `.claude/agents/` (companion to PLG-017 namespacing)
- New `--auto-from {caller}` flag in `init_project.py` for subroutine-mode invocation

**Plugin file structure** (updated counts):

```
planwise/
  handlers/      # 8 subcommand handlers (init, plan, review, run, backlog, list, lessons, help)
  references/   # 20 knowledge base documents (17 path-scoped rules + 3 lessons-workflow helpers); count reconciled in v1.2.0
  templates/    # 13 markdown templates (12 baseline + sprint-signoff.md)
```

### 1.0.1

Baseline release. Existing 10 reference rules + 12 templates + 7 handlers + 4 agents.

---

## Upgrading

When a new plugin version is published:

1. **Refresh the plugin source**

   ```
   /plugin marketplace update
   /plugin install planwise@planwise-marketplace
   ```

   This updates the plugin's handlers, references, templates, and scripts to the latest version. Files Claude reads directly from the plugin directory are now current.

2. **Propagate updates into your project's `.claude/` directory**

   ```
   /planwise upgrade
   ```

   `/plugin install` does not refresh the rules in `.claude/rules/planwise/` or the agents in `.claude/agents/` — those were installed once during `/planwise init` and are skip-if-exists thereafter. `/planwise upgrade`:

   - Bumps the pinned `plugin_version:` in your `config.yaml`
   - Adds any new top-level config keys (the additive merge previously available via `--migrate`)
   - Refreshes installed rules/agents whose local body still matches the previously-shipped body
   - Writes `.new` sidecars under `{planwise_root}/upgrade-conflicts/<from>-to-<to>/` for any file whose body has diverged from the shipped version, so your customisations are preserved

   See `handlers/upgrade.md` for the full workflow.

> Running `/planwise init` after a plugin update detects the pinned-version drift and surfaces a SKIPPED row pointing at this command, so the prompt is reachable even if you forget the recipe.

---

## Uninstalling

To remove the plugin:

```
/plugin uninstall planwise
```

To remove the marketplace:

```
/plugin marketplace remove planwise-marketplace
```

> **Note:** Uninstalling the plugin does **not** delete your `planwise/` project folder or any of your plans, backlogs, or lessons. Your data is always safe.

---

## Troubleshooting

**"Command not found" when typing `/planwise`**
- Make sure you installed the plugin from the marketplace
- Run `/reload-plugins` or restart Claude Code to activate newly installed plugins

**"Config not found" when running a subcommand**
- Run `/planwise init` first — most commands need the project to be initialized

**Python scripts show errors**
- Check that Python 3.8+ is installed: `python --version`
- If you see YAML-related warnings, install PyYAML: `pip install pyyaml` (optional but silences warnings)

**Plans or backlog seem out of date after a plugin update**
- Run the two-step upgrade recipe: `/plugin marketplace update` + `/plugin install planwise@planwise-marketplace`, then `/planwise upgrade` to propagate refreshed rules and agents into your project

**Not sure which command to use?**
- Run `/planwise help` to see all available commands and a link to the full user guide

---

## License

MIT — Gabriel Gosselin
