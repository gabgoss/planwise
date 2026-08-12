"""config.yaml generation and migration.

Owns InitConfig, the config.yaml.template rendering (generate_config), the
additive --migrate merge (migrate_config), and the small config.yaml
line-edit helpers (plugin_version pin, Token Saver on-flip) that write
through the same parse-checked writer.
"""

import dataclasses
import json
import re
from enum import Enum
from pathlib import Path

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False


try:
    from config_loader import find_context_block, get_upgrade_config, write_config_checked
except ImportError:
    # Partial-install tolerance, mirroring the structural_compare guard in rule_divergence.py:
    # a half-synced scripts tree must not kill the whole CLI at import time.
    # Mirrors config_loader.get_upgrade_config()'s conservative defaults.
    def get_upgrade_config(config: dict) -> dict:   # noqa: D103
        return {
            "customization_handoff": "report",
            "github_issue": False,
            "descope_preserve_paths_edits": True,
        }

    def write_config_checked(config_path, text: str) -> None:   # noqa: D103
        # Degraded fallback: the post-write parse check lives in config_loader,
        # so a half-synced scripts tree writes unverified rather than failing
        # to start. Same spirit as the no-PyYAML no-op in the real helper.
        Path(config_path).write_text(text, encoding="utf-8")

    def find_context_block(lines: list) -> "tuple[int, int, str] | None":   # noqa: D103
        # Unlike the two degraded-but-safe fallbacks above, this helper's own
        # job IS config.yaml write correctness. Duplicating (and risking drift
        # from) the block-extent logic here would let a half-synced scripts
        # tree silently rewrite a user's config.yaml with no signal something
        # is wrong. Fail loudly instead — config_loader is a required sibling.
        raise ImportError(
            "config_loader is required for config.yaml context-block editing; "
            "the scripts/ directory appears to be partially installed"
        )


PLAN_TIER_WINDOWS = {
    "pro": 200000,
    "max": 1000000,
}


# Top-level keys that `--migrate` will copy from config.yaml.template into an
# existing user config when absent. Existing keys are NEVER overwritten — the
# flow is purely additive. Order matches the on-disk layout of the template
# so merged output stays readable.
MIGRATABLE_TOP_LEVEL_KEYS = [
    "plugin_root",
    "plugin_version",   # paired with plugin_root: version pin set on init, bumped by upgrade
    "context",
    "categorization",
    "upgrade",          # HAS_UNIQUE handoff routing + de-scope paths-only-edit policy
]


# Sub-keys under `context:` that `--migrate` adds to an EXISTING context block.
# The top-level merge above skips `context` whenever the user's config already
# has it (every installed config does), so the six Token Saver sub-keys would
# never reach an existing install without this nested merge. Each tuple is
# (sub_key, default_value_literal) where the literal is rendered verbatim into
# the YAML line. Existing sub-keys are NEVER overwritten — purely additive.
MIGRATABLE_CONTEXT_SUBKEYS: list[tuple[str, str]] = [
    ("token_saver", "false"),
    ("token_saver_session_target", "150000"),
    ("token_saver_runner_overhead", "0"),
    ("token_saver_orchestrator_overhead", "0"),
    ("token_saver_context_breakdown", "{}"),
    ("token_saver_overhead_measured_on", '""'),
]


def _existing_context_subkeys(lines: list[str], start: int, end: int) -> set[str]:
    """Return the set of sub-key names already present in a context block."""
    keys: set[str] = set()
    for k in range(start, end):
        m = re.match(r"^\s+([a-zA-Z_]\w*):", lines[k])
        if m:
            keys.add(m.group(1))
    return keys


def _context_subkeys_delta(before: str, after: str) -> list[str]:
    """Return the context sub-keys present in `after` but not in `before`.

    Used for migrate reporting (which Token Saver sub-keys the nested merge
    added). Order follows MIGRATABLE_CONTEXT_SUBKEYS.
    """
    before_lines = before.split("\n")
    after_lines = after.split("\n")
    before_block = find_context_block(before_lines)
    after_block = find_context_block(after_lines)
    before_keys: set[str] = set()
    after_keys: set[str] = set()
    if before_block is not None:
        h, e, _ = before_block
        before_keys = _existing_context_subkeys(before_lines, h + 1, e)
    if after_block is not None:
        h, e, _ = after_block
        after_keys = _existing_context_subkeys(after_lines, h + 1, e)
    gained = after_keys - before_keys
    return [
        f"context.{k}" for k, _ in MIGRATABLE_CONTEXT_SUBKEYS if k in gained
    ]


def merge_context_subkeys(text: str, token_saver_value: str = "false") -> str:
    """Add any missing Token Saver sub-keys to an existing `context:` block.

    Targeted, comment-preserving, in-place text edit — NOT a yaml round-trip.
    Existing sub-keys are left byte-for-byte untouched (never overwritten), so
    re-running this is idempotent and non-destructive. Returns the text
    unchanged when there is no top-level `context:` block (the caller handles
    the whole-block-add path).

    Delegates locating the block to the shared config_loader editor
    (find_context_block) but keeps this function's own additive-only,
    skip-if-present policy local — the opposite of config_loader's
    splice_context_block, which ALWAYS replaces an existing key.
    token_saver._write_back() rides that replace-if-present policy instead;
    routing this function through it would silently overwrite a user's
    already-calibrated Token Saver values on every --migrate.

    `token_saver_value` overrides the literal written for the `token_saver`
    toggle (so generation can honour --token-saver while migration defaults to
    "false").
    """
    lines = text.split("\n")
    block = find_context_block(lines)
    if block is None:
        return text
    header_idx, end, subkey_indent = block
    existing = _existing_context_subkeys(lines, header_idx + 1, end)

    additions: list[str] = []
    for sub_key, default in MIGRATABLE_CONTEXT_SUBKEYS:
        if sub_key in existing:
            continue
        value = token_saver_value if sub_key == "token_saver" else default
        additions.append(f"{subkey_indent}{sub_key}: {value}")

    if not additions:
        return text

    new_lines = lines[:end] + additions + lines[end:]
    return "\n".join(new_lines)


def extract_top_level_block(text: str, key: str) -> str | None:
    """Return the raw text of the top-level `key:` block in `text`, or None.

    Locates the unindented `{key}:` line and captures through to the line before
    the next top-level construct (any unindented non-blank line, comment lines
    included — a column-0 comment introduces the block BELOW it, so it belongs
    to the next key). Trailing blank lines are trimmed off the captured block.

    The contiguous run of comment lines immediately above the key is carried
    with the block so the template's hand-authored commentary travels with the
    key it documents. One exception: a run that reaches line 0 is the FILE
    header, not a block comment, and is dropped — the destination file already
    has its own header.

    Used by the migrate merge to splice a missing key into the user's config as
    text, so no part of the user's file is ever re-emitted through a YAML dumper.
    """
    lines = text.split("\n")
    start = None
    for i, line in enumerate(lines):
        if re.match(rf"^{re.escape(key)}:", line):
            start = i
            break
    if start is None:
        return None

    end = len(lines)
    for j in range(start + 1, len(lines)):
        line = lines[j]
        if line.strip() == "":
            continue
        if re.match(r"^\s", line):
            continue
        end = j
        break

    # Trim trailing blank lines and any comment run that introduces the next key.
    while end - 1 > start:
        prev = lines[end - 1]
        if prev.strip() == "" or prev.lstrip().startswith("#"):
            end -= 1
        else:
            break

    head = start
    while head - 1 >= 0 and lines[head - 1].lstrip().startswith("#"):
        head -= 1
    if head == 0:
        # The comment run runs to the top of the file — that is the file header.
        head = start

    return "\n".join(lines[head:end])


class ConfigResult(Enum):
    CREATED = "created"
    SKIPPED_EXISTS = "skipped_exists"
    SKIPPED_NO_TEMPLATE = "skipped_no_template"
    SKIPPED_NO_YAML = "skipped_no_yaml"
    CREATED_FROM_DEFAULT = "created_from_default"
    SKIPPED_BAD_CONFIG = "skipped_bad_config"


@dataclasses.dataclass
class InitConfig:
    project_name: str
    project_root: Path
    plugin_root: Path
    planwise_root: str = "planwise"
    plans_dir: str = "Plans"
    backlog_dir: str = "Backlog"
    lessons_dir: str = "LessonsLearned"
    install_scope: str = "project"
    plan_tier: str = "pro"
    plugin_version: str = "0.0.0"
    token_saver: bool = False

    @property
    def context_window(self) -> int:
        return PLAN_TIER_WINDOWS[self.plan_tier]


def get_plugin_root() -> Path:
    """Return the plugin root (parent of scripts/)."""
    return Path(__file__).resolve().parent.parent


def read_plugin_version(plugin_root: Path) -> str:
    """Read the plugin version from .claude-plugin/plugin.json.

    Returns the version string. Falls back to "0.0.0" if the file is
    missing or malformed — callers use this as the "unknown / never pinned"
    sentinel so the upgrade flow treats the project as pre-versioning.
    """
    plugin_json = plugin_root / ".claude-plugin" / "plugin.json"
    try:
        data = json.loads(plugin_json.read_text(encoding="utf-8"))
        return str(data.get("version", "0.0.0"))
    except (FileNotFoundError, json.JSONDecodeError):
        return "0.0.0"


def generate_config(cfg: InitConfig) -> tuple[ConfigResult, str]:
    """Generate config.yaml from template. Returns (status, path)."""
    template_path = cfg.plugin_root / "config.yaml.template"
    config_rel = f"{cfg.planwise_root}/config.yaml"
    dst = cfg.project_root / cfg.planwise_root / "config.yaml"

    try:
        content = template_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ConfigResult.SKIPPED_NO_TEMPLATE, config_rel

    content = content.replace("{plugin-root}", str(get_plugin_root()).replace("\\", "/"))
    content = content.replace("{project-name}", cfg.project_name)
    content = content.replace("{install-scope}", cfg.install_scope)
    content = content.replace("{planwise-root}", cfg.planwise_root)
    content = content.replace("{plans-dir}", cfg.plans_dir)
    content = content.replace("{backlog-dir}", cfg.backlog_dir)
    content = content.replace("{lessons-dir}", cfg.lessons_dir)
    content = content.replace("{plan-tier}", cfg.plan_tier)
    content = content.replace("{context-window}", str(cfg.context_window))
    content = content.replace("{plugin-version}", cfg.plugin_version)
    content = content.replace("{token-saver}", "true" if cfg.token_saver else "false")

    # Ensure the six Token Saver sub-keys are present even if the shipped
    # template predates them (older template, or a fixture without them) —
    # the nested merge is additive and respects the --token-saver toggle.
    content = merge_context_subkeys(
        content, token_saver_value="true" if cfg.token_saver else "false"
    )

    try:
        with open(dst, "x", encoding="utf-8") as f:
            f.write(content)
    except FileExistsError:
        return ConfigResult.SKIPPED_EXISTS, config_rel

    # Same invariant the editing writers hold: never leave an unparseable config
    # on disk. Exclusive-create mode means the file is ours and did not exist a
    # moment ago, so the rollback is simply to remove it — the caller sees a
    # loud failure instead of an init that "succeeded" into a broken file.
    if HAS_YAML:
        try:
            yaml.safe_load(dst.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            dst.unlink(missing_ok=True)
            raise RuntimeError(
                f"{dst}: rendered config does not parse as YAML — the file was removed. "
                f"Parser said: {exc}"
            ) from exc
    return ConfigResult.CREATED, config_rel


def migrate_config(cfg: InitConfig) -> tuple[str, list[str], list[str]]:
    """Merge missing top-level keys from config.yaml.template into the user's config.

    Idempotent. Existing top-level keys are NEVER overwritten. Reports both
    the keys that were added and the keys that were already present so the
    caller can build a Step 10 banner section.

    Returns (config_path_str, added_keys, present_keys).
    Raises FileNotFoundError when the user's config is absent (run /planwise
    init before --migrate).
    """
    if not HAS_YAML:
        raise RuntimeError(
            "PyYAML is required for --migrate. Install with `pip install pyyaml`."
        )

    config_path = cfg.project_root / cfg.planwise_root / "config.yaml"
    if not config_path.exists():
        raise FileNotFoundError(
            f"{config_path} does not exist — run /planwise init before --migrate."
        )

    template_path = cfg.plugin_root / "config.yaml.template"
    template_text = template_path.read_text(encoding="utf-8")

    # Render template placeholders before parsing so the merged values are
    # concrete (e.g., `context_window: 200000` instead of `{context-window}`).
    template_text = template_text.replace("{plugin-root}", str(cfg.plugin_root).replace("\\", "/"))
    template_text = template_text.replace("{project-name}", cfg.project_name)
    template_text = template_text.replace("{install-scope}", cfg.install_scope)
    template_text = template_text.replace("{planwise-root}", cfg.planwise_root)
    template_text = template_text.replace("{plans-dir}", cfg.plans_dir)
    template_text = template_text.replace("{backlog-dir}", cfg.backlog_dir)
    template_text = template_text.replace("{lessons-dir}", cfg.lessons_dir)
    template_text = template_text.replace("{plan-tier}", cfg.plan_tier)
    template_text = template_text.replace("{context-window}", str(cfg.context_window))
    template_text = template_text.replace("{plugin-version}", cfg.plugin_version)
    # Migration is toggle-neutral: a whole-block add lands the engine OFF, matching
    # the nested-merge default below. The --token-saver flag is applied afterwards
    # by the separate flip step, so rendering it here would double-apply it.
    template_text = template_text.replace("{token-saver}", "false")

    template_data = yaml.safe_load(template_text) or {}
    user_text = config_path.read_text(encoding="utf-8")
    user_data = yaml.safe_load(user_text) or {}

    if not isinstance(user_data, dict) or not isinstance(template_data, dict):
        raise RuntimeError(f"{config_path} is not a YAML mapping — cannot merge.")

    added: list[str] = []
    present: list[str] = []
    for key in MIGRATABLE_TOP_LEVEL_KEYS:
        if key in template_data and key not in user_data:
            added.append(key)
        elif key in user_data:
            present.append(key)

    if not added:
        # No top-level keys to add — but an existing `context:` block may still
        # be missing the Token Saver sub-keys. Do a targeted, comment-preserving
        # nested merge directly on the user's file text (NO yaml round-trip, so
        # comments/order survive and re-running stays byte-for-byte idempotent).
        merged_text = merge_context_subkeys(user_text)
        if merged_text != user_text:
            write_config_checked(config_path, merged_text)
            sub_added = _context_subkeys_delta(user_text, merged_text)
            added.extend(sub_added)
        return str(config_path), added, present

    # Adding a key is the SAME targeted, comment-preserving text edit as the
    # branch above — each missing key's block is spliced onto the user's own
    # file text. The user's bytes are never round-tripped through a YAML dumper:
    # a whole-file re-emit rewrites every value in the dumper's default style
    # (collapsing inline flow mappings and inline lists into multi-line blocks)
    # and destroys every interior comment. That reflow is not merely cosmetic —
    # the targeted line editor that later writes the measured context values
    # matches a key's value on ONE line, so a value reflowed into a block
    # mapping is left with orphaned children and the file stops parsing.
    #
    # Each block is lifted from the rendered template as TEXT, so the template's
    # own layout and commentary come across intact. A key that cannot be located
    # as text falls back to a dump of THAT KEY'S BLOCK ONLY.
    merged_text = user_text
    for key in added:
        block = extract_top_level_block(template_text, key)
        if block is None:
            block = yaml.safe_dump(
                {key: template_data[key]},
                sort_keys=False,
                default_flow_style=False,
                indent=2,
                allow_unicode=True,
            ).rstrip("\n")
        merged_text = merged_text.rstrip("\n") + "\n\n" + block + "\n"

    # The whole-block-add path (context copied from the template) may still
    # lack the Token Saver sub-keys when the shipped template predates them —
    # backfill them into the freshly-appended block so every migrate target
    # ends up with the full surface.
    merged_text = merge_context_subkeys(merged_text)

    write_config_checked(config_path, merged_text)
    return str(config_path), added, present


def _bump_plugin_version(config_path: Path, new_version: str) -> None:
    """Update the plugin_version: line in config.yaml in-place, preserving formatting.

    Prefers a line-level edit over PyYAML round-trip so the user's comment
    layout is preserved. Falls back to appending the key as text if the line
    isn't found (e.g., legacy config that never got the migrate-added key) —
    never a whole-file re-emit, which would drop every interior comment and
    reflow every inline flow value. Both paths write through the parse-checked
    writer, so a bad edit is rolled back instead of bricking the config.
    """
    text = config_path.read_text(encoding="utf-8")
    pattern = re.compile(r'^(\s*plugin_version:\s*)("[^"]*"|\S+)\s*$', re.MULTILINE)
    if pattern.search(text):
        new_text = pattern.sub(rf'\1"{new_version}"', text)
        write_config_checked(config_path, new_text)
        return
    # Fallback — append the key as text after the existing top-level set.
    data = yaml.safe_load(text) or {}
    if not isinstance(data, dict):
        raise RuntimeError(f"{config_path} is not a YAML mapping — cannot pin version.")
    write_config_checked(
        config_path,
        text.rstrip("\n") + f'\n\nplugin_version: "{new_version}"\n',
    )


def _flip_token_saver_on(config_path: Path) -> bool:
    """Flip `token_saver: false` to `true` in the config, comment-preserving.

    Targets the bare `token_saver:` key only — never touches `token_saver_*`
    measured lines (they have a different key suffix before the colon).
    Only flips false -> true; an existing `true` is a no-op and is never
    reverted to false. Idempotent: re-running on an already-true config
    returns False without writing the file.

    Returns True when the value was changed, False when it was already true
    or the key was absent (so the caller can decide whether to print a banner).
    """
    text = config_path.read_text(encoding="utf-8")
    # The pattern anchors on line boundaries (MULTILINE) and matches exactly
    # `token_saver:` followed by optional whitespace, the literal `false`, and
    # an optional trailing inline comment. `token_saver_session_target:` etc.
    # cannot match because the underscore separator comes before the colon.
    pattern = re.compile(
        r'^(\s*token_saver:[ \t]*)false([ \t]*(?:#[^\n]*)?)$',
        re.MULTILINE,
    )
    if not pattern.search(text):
        return False
    new_text = pattern.sub(r'\g<1>true\g<2>', text)
    write_config_checked(config_path, new_text)
    return True

