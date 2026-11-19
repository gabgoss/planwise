"""Shipped hook modules keep two contracts that an injected-input test cannot see.

1. Every option key a hook reads is declared under `userConfig` in `plugin.json`.
   A consumer can set only a declared key, so an undeclared key ships inert.
2. No hook reads the session id with `$.env.get`. The host does not rewrite that
   variable in a hook module's own environment, so the read returns the launching
   shell's value. In a nested session that is the parent's id.

Only one direction of the first contract is checked. A key read in code must be
declared. A declared key that nothing reads is out of scope, because a script may
read a plugin setting through another surface.

Fixtures are written under `tmp_path` only, never inside the shipped subtree.

Pinned run, from the project root:
    python -m pytest -q -c cloned-repos/planwise/pytest.ini cloned-repos/planwise/tests/test_hook_module_contracts.py
"""

import json
import re
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
PLUGIN_ROOT = TESTS_DIR.parent / "plugins" / "planwise"
HOOKS_DIR = PLUGIN_ROOT / "hooks"
MANIFEST = PLUGIN_ROOT / ".claude-plugin" / "plugin.json"

# options['k'], options["k"], options?.['k']
LITERAL_READ = re.compile(r"""\boptions\s*\??\.?\s*\[\s*(['"])([\w-]+)\1\s*\]""")
# options.k, options?.k
DOT_READ = re.compile(r"\boptions\s*\?{0,1}\.([A-Za-z_]\w*)")
# options[NAME], options?.[NAME]
NAME_READ = re.compile(r"\boptions\s*\??\.?\s*\[\s*([A-Za-z_]\w*)\s*\]")
SESSION_ID_ENV_READ = re.compile(r"""\$\.env\.get\(\s*(['"])CLAUDE_CODE_SESSION_ID\1""")


def hook_files(hooks_dir):
    """Every TypeScript hook source under the hooks folder."""
    return sorted(p for p in hooks_dir.rglob("*") if p.suffix in (".ts", ".tsx"))


def _constant_value(text, name):
    """The string a `const NAME = '...'` line sets, or None when the file has no such line."""
    pattern = re.compile(r"""(?:export\s+)?const\s+""" + re.escape(name) + r"""\s*(?::[^=\n]+)?=\s*(['"])([\w-]+)\1""")
    found = pattern.search(text)
    return found.group(2) if found else None


def option_keys_read(hooks_dir):
    """The option keys the hook sources read. An unresolvable NAME is reported as '<unresolved:NAME>'."""
    keys = set()
    for path in hook_files(hooks_dir):
        text = path.read_text(encoding="utf-8")
        keys.update(m.group(2) for m in LITERAL_READ.finditer(text))
        keys.update(m.group(1) for m in DOT_READ.finditer(text))
        for m in NAME_READ.finditer(text):
            value = _constant_value(text, m.group(1))
            keys.add(value if value is not None else "<unresolved:" + m.group(1) + ">")
    return keys


def declared_keys(manifest_path):
    """The key set under `userConfig` in a plugin manifest."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return set(manifest.get("userConfig", {}))


def env_session_id_reads(hooks_dir):
    """Every 'file:line' where a hook reads the session id through `$.env.get`."""
    hits = []
    for path in hook_files(hooks_dir):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if SESSION_ID_ENV_READ.search(line):
                hits.append(f"{path.name}:{number}")
    return hits


def _tree(tmp_path, hook_source, userconfig):
    """A scratch hooks folder and manifest. Returns (hooks_dir, manifest_path)."""
    hooks = tmp_path / "hooks"
    hooks.mkdir()
    (hooks / "x.ts").write_text(hook_source, encoding="utf-8")
    manifest = tmp_path / "plugin.json"
    manifest.write_text(json.dumps({"userConfig": {k: {"type": "string"} for k in userconfig}}), encoding="utf-8")
    return hooks, manifest


UNDECLARED_HOOK = "export const OPTION_KEY = 'undeclared_k'\nconst on = options[OPTION_KEY]\n"


def test_every_option_key_the_shipped_hooks_read_is_declared():
    assert hook_files(HOOKS_DIR), "the walk saw no hook sources, so an empty result proves nothing"
    read = option_keys_read(HOOKS_DIR)
    assert "agent_guard" in read, "the reader is blind: the known option key was not found"
    assert sorted(read - declared_keys(MANIFEST)) == []


def test_undeclared_key_is_reported_and_declaring_it_clears_it(tmp_path):
    hooks, manifest = _tree(tmp_path, UNDECLARED_HOOK, {"agent_guard"})
    assert option_keys_read(hooks) - declared_keys(manifest) == {"undeclared_k"}
    manifest.write_text(json.dumps({"userConfig": {"undeclared_k": {}}}), encoding="utf-8")
    assert option_keys_read(hooks) - declared_keys(manifest) == set()


def test_literal_and_dot_reads_are_collected(tmp_path):
    source = "const a = options['lit_k']\nconst b = options.dot_k\nconst c = options?.['opt_k']\nconst d = options[\"dq_k\"]\n"
    hooks, _ = _tree(tmp_path, source, set())
    assert option_keys_read(hooks) == {"lit_k", "dot_k", "opt_k", "dq_k"}


def test_unresolvable_name_is_a_failure_not_a_skip(tmp_path):
    hooks, manifest = _tree(tmp_path, "const on = options[computedKey]\n", {"agent_guard"})
    assert option_keys_read(hooks) - declared_keys(manifest) == {"<unresolved:computedKey>"}


def test_options_parameter_with_no_read_is_not_a_key(tmp_path):
    hooks, _ = _tree(tmp_path, "export function register(on, options) {\n  void options\n}\n", set())
    assert option_keys_read(hooks) == set()


def test_shipped_hooks_do_not_read_the_session_id_from_the_environment():
    assert hook_files(HOOKS_DIR), "the walk saw no hook sources, so an empty result proves nothing"
    assert env_session_id_reads(HOOKS_DIR) == []


def test_environment_session_id_read_is_flagged_and_the_session_read_is_not(tmp_path):
    wrong = "const sid = await $.env.get('CLAUDE_CODE_SESSION_ID')\n"
    correct = "const sid = await $.session.id()\nconst os = await $.env.get('OS')\n"
    (tmp_path / "wrong").mkdir()
    (tmp_path / "correct").mkdir()
    wrong_hooks, _ = _tree(tmp_path / "wrong", wrong, set())
    correct_hooks, _ = _tree(tmp_path / "correct", correct, set())
    assert env_session_id_reads(wrong_hooks) == ["x.ts:1"]
    assert env_session_id_reads(correct_hooks) == []
