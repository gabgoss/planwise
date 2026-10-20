---
id: 507
title: "No-PyYAML fallback config parser cannot read quoted keys, block scalars or nested abbreviation entries"
priority: Low
status: NOT_STARTED
abbrev: BUG
created: 2026-10-10
blocks: []
route_hint: B
route_evidence: "the fix has two valid shapes (extend the parser, or make the migrator write only parser-readable shapes) and needs a choice"
route_dated: 2026-10-10
---

# BB-507-BUG-NoPyYamlFallbackParserMisreadsAbbreviationKeys: No-PyYAML fallback config parser cannot read quoted keys, block scalars or nested abbreviation entries

**Priority:** Low
**Domain:** BUG
**Source:** UpgradeRunDefects session URD-S02-02 review, closed 2026-10-10, plugin commit a8ba06c on branch 1.0.5.3

---

## Summary

`config_loader.py` falls back to a minimal parser, `_parse_yaml_simple`, when PyYAML is not installed. That parser matches only bare keys and one nesting level. A `config.yaml` whose `abbreviations:` block uses quoted keys, block-scalar values or nested entries is read wrongly or not at all. The backlog migrator re-reads the config after it writes. Without PyYAML, that reload check fails closed, the run ends `write_failed`, and the config is restored.

## Problem

**Evidence:** every key pattern in `_parse_yaml_simple` is `[a-zA-Z_]\w*`, so a quoted key or a key with a hyphen or dot cannot match — verified 2026-10-10 by Read of `cloned-repos/planwise/plugins/planwise/scripts/config_loader.py` lines 347-404.

The relevant patterns (`config_loader.py`, `_parse_yaml_simple`, at commit a8ba06c):

```python
if re.match(r"^[a-zA-Z_]\w*:\s*$", stripped):                      # section header: bare key only
top_match = re.match(r"^([a-zA-Z_]\w*):\s+(.+)$", stripped)         # top-level scalar: bare key only
nested_match = re.match(r"^\s+([a-zA-Z_]\w*):\s+(.+)$", line)       # one nested level: bare key, inline value
list_match = re.match(r"^\s+-\s+(.+)$", line)                       # list item
```

Consequences for an `abbreviations:` block:
- A quoted key such as `"Y": Yes` or `'N': No` does not match `[a-zA-Z_]\w*`, so the entry is dropped or mis-assigned.
- A block-scalar value (`key: >` or `key: |`) is stored as the literal text `>` or `|`, and its indented body lines fall through to the nested-key or list patterns.
- A nested entry deeper than one level under `abbreviations:` is flattened or lost, because the parser tracks a single `current_section`.

Interaction with the migrator: session URD-S02-02 made the backlog migrator's config-append refuse YAML boolean and null words as abbreviation names before it writes, and write `Y` and `N` bare, so the file stays readable by this parser. That keeps migrator-written configs safe. A config that a user or another tool wrote with the shapes above is still misread. When PyYAML is absent, the post-write reload check then fails closed: the run ends `write_failed` and the config is restored. No data is lost, but the migration can never succeed on that machine until PyYAML is installed.

To reproduce, run the migrator on a project whose `config.yaml` has an `abbreviations:` block containing a quoted key, in an interpreter without PyYAML. Run the repro once against the current tree before pinning it, per the project's pinned-command rule.

## Proposed Solution

Pick one of two shapes and record the choice in the fix:

1. **Extend the fallback parser** to read quoted keys, block scalars and one more nesting level inside `abbreviations:`. Keep its scope tight to the shapes the shipped `config.yaml.template` and the migrator can produce.
2. **Fail early and clearly** when PyYAML is absent and the config holds a shape the fallback cannot read. The migrator then reports a refusal that tells the user to install PyYAML, before any write, instead of ending `write_failed` after one.

Either shape needs a test that runs the loader with PyYAML hidden (for example by patching the module-level `yaml` import to `None`) over a config using each unreadable shape.

## Acceptance Criteria

- [ ] A test with PyYAML hidden loads a config with a quoted abbreviation key and gets the same dict PyYAML gives, or gets a refusal that names PyYAML, not a silent misread
- [ ] The same test covers a block-scalar value and a nested abbreviation entry
- [ ] A migrator run without PyYAML on such a config ends in a refusal before any file is written, or succeeds, but never ends `write_failed`
- [ ] The existing config_loader and migration tests pass unchanged
- [ ] The full plugin suite passes, run as `python -m pytest -q -c cloned-repos/planwise/pytest.ini cloned-repos/planwise/tests`, with zero collected node ids outside `cloned-repos/planwise/tests`

## Related

- [BB-483-01-INFRA-PyYamlInterpreterCorrectRemediation.md](BB-483-01-INFRA-PyYamlInterpreterCorrectRemediation.md) - PyYAML-missing remediation text
- [BB-482-01-BUG-InitMissingPyYamlFalseDriftRow.md](BB-482-01-BUG-InitMissingPyYamlFalseDriftRow.md) - another PyYAML-absent behaviour defect
- UpgradeRunDefects session URD-S02-02, plugin commit a8ba06c - the session that added the bare `Y`/`N` write and the boolean and null refusal

---

*Created: 2026-10-10*
