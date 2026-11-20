# De-scoped prior bodies

These files are frozen test inputs. Each one is the body that release `1.0.2` shipped for one of the four `{all_paths}` entries of `rule_registry.DESCOPED_RULES`:

| Fixture | Source |
|---|---|
| `agent-orchestration.md@1.0.2.md` | tag `1.0.2`, `plugins/planwise/references/agent-orchestration.md` |
| `agent-orchestration-delegated.md@1.0.2.md` | tag `1.0.2`, `plugins/planwise/references/agent-orchestration-delegated.md` |
| `callout-conventions.md@1.0.2.md` | tag `1.0.2`, `plugins/planwise/references/callout-conventions.md` |
| `markdown-conventions.md@1.0.2.md` | tag `1.0.2`, `plugins/planwise/references/markdown-conventions.md` |

Release `1.0.2` is the last release below `rule_descope_migration.RESCOPE_MIGRATION_VERSION` (`1.0.3`). A consumer who installed from it holds these bodies as installed copies.

Each file was written once with `git show 1.0.2:<path>`, with CRLF converted to LF. The tests read the files from this folder and never from git, so a shallow checkout still runs them. Never edit a fixture to match a newer reference. A fixture that changes no longer proves that the real released body is recognized.

`tests/test_rule_descope_migration.py` drives each body through `migrate_installed_rules` and the doctor stale-rule sweep. It also pins the normalized digest of each released body against `manifests/rule-history.json`.
