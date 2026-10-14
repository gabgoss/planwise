---
id: 417
title: "Extract init_project's shared rule helpers into a leaf module to end the re-export import cycle"
priority: Low
status: IN_PROGRESS
abbrev: INFRA
created: 2026-09-28
blocks: []
route_hint: B
route_evidence: "Five importers plus ~27 test patch sites resolve these names on their current modules; the move needs a census and the globbed import-order test"
route_dated: 2026-09-28
---

# BB-417-INFRA-InitProjectLeafModuleForReexportCycle: Extract init_project's shared rule helpers into a leaf module to end the re-export import cycle

**Priority:** Low
**Domain:** INFRA

---

## Summary

`scripts/init_project.py` re-exports names from sibling modules at its bottom, and those siblings import names back from `init_project`. Plugin commits `5f7aba8`, `5eaa4fc` and `529fd4f` fixed the symptom by moving each back-edge import below the module's own definitions. The cycle itself remains. A leaf module removes it, so every import can return to the top of its file.

## Problem

Measured 2026-09-28 on plugin `529fd4f`:

- `init_project.py` imports `rule_descope_migration`, `artifact_upgrade` and `doctor_cli` near its bottom (around lines 332, 345 and 375 before the fixes). Each of those modules, plus `doctor_sweeps`, imports `INSTALLED_RULES`, `DESCOPED_RULES`, `resolve_rule_paths_value` or `update_frontmatter` back from `init_project`.
- Before the fixes, importing `artifact_upgrade`, `rule_descope_migration`, `doctor_sweeps` or `doctor_cli` first in a fresh interpreter raised `ImportError`. The fix moved each back-edge import block below that module's definitions. It is a placement fix only. Module attributes were kept because about 27 test sites patch them.
- `tests/test_import_order.py` now imports all 61 scripts first, each in a fresh subprocess, and passes. A future edit that moves one of those blocks back to the top reopens the failure.

~~The same file also carries a label no consumer can resolve.~~ **Done 2026-10-06, outside this item.** The "seam 4/5/6" label in the `init_project.py` alias comment was reworded ahead of the merge to `main`. It now names the modules: `rule_descope_migration`, `artifact_upgrade`, `doctor_sweeps` and `doctor_cli`. The live code has four back-importers, not the three this item first listed: `doctor_sweeps` also imports from `init_project`. The reword landed in plugin commit `40c3ced`. That commit was BB-421's, and it picked up the staged comment hunk when it committed the whole file, so its message does not mention the reword.

## Proposed Solution

1. Create a leaf module, for example `scripts/rule_registry.py`, that imports nothing from `init_project`, `artifact_upgrade`, `rule_descope_migration`, `doctor_sweeps` or `doctor_cli`. Move into it `INSTALLED_RULES`, `DESCOPED_RULES`, `resolve_rule_paths_value` and `update_frontmatter`.
2. Import the four names from the leaf module in all five modules. `init_project` keeps re-exporting them, so `from init_project import INSTALLED_RULES` still resolves for any consumer and for the test patch sites. Before moving anything, take a census of the `patch.object(init_project, …)` and `patch("init_project.…")` sites: a patch on the re-export no longer reaches a reader that imports from the leaf.
3. Move each guarded import block back to the top of its file, and delete the "moved below the definitions" comments.
4. ~~Reword `init_project.py:43` to name the modules.~~ Done in `40c3ced`, see Problem. Once the leaf module removes the cycle, delete or shorten that comment if the alias it explains is no longer needed. Keep the inline-defined `(R1: …)` parenthetical only if the sentence still needs it.

## Acceptance Criteria

- [ ] The four names are defined in one leaf module that imports none of the five modules
- [ ] Every guarded import in `init_project`, `artifact_upgrade`, `rule_descope_migration`, `doctor_sweeps` and `doctor_cli` sits at the top of its file
- [ ] `tests/test_import_order.py` passes, with every script importable first
- [ ] The full suite is green with zero collected node ids outside `cloned-repos/planwise/tests`
- [x] `init_project.py` carries no "seam 4/5/6" label (plugin `40c3ced`, 2026-10-06)
- [ ] `uvx ruff@0.16.8 check cloned-repos/planwise` is clean

## Files Touched

| Path | Role |
|------|------|
| `cloned-repos/planwise/plugins/planwise/scripts/init_project.py` | EDIT |
| `cloned-repos/planwise/plugins/planwise/scripts/artifact_upgrade.py` | EDIT |
| `cloned-repos/planwise/plugins/planwise/scripts/rule_descope_migration.py` | EDIT |
| `cloned-repos/planwise/plugins/planwise/scripts/doctor_sweeps.py` | EDIT |
| `cloned-repos/planwise/plugins/planwise/scripts/doctor_cli.py` | EDIT |
| `cloned-repos/planwise/plugins/planwise/scripts/{leaf module}.py` | CREATE |

## Related

- [BB-417-INFRA-InitProjectLeafModuleForReexportCycle.md](BB-417-INFRA-InitProjectLeafModuleForReexportCycle.md) - file for this item
- Source: review finding 7 and the F9 out-of-scope finding, `planwise/Plans/BacklogIndexRedesign/Sprint-05-LessonsIndexPort/Session-08-LessonsGeneratorModuleSplit/Outputs/BIR-S05-08-ReviewFixes.md`

---

*Created: 2026-09-28*
