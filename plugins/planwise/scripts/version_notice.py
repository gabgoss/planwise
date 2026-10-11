"""Print one line when config.yaml pins a different plugin version than the
plugin that is dispatching the current subcommand.

Read-only. Prints nothing and exits 0 when the versions match, when the config
is absent, or when either version cannot be read. It never blocks a subcommand.
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def _version_tuple(text: str) -> tuple:
    """Every numeric component. An empty tuple means the text has no number."""
    return tuple(int(p) for p in re.findall(r"\d+", text))


def _padded(a: tuple, b: tuple) -> tuple:
    """Pad the shorter tuple with zeros so 1.0.5.1 sorts above 1.0.5."""
    size = max(len(a), len(b))
    return a + (0,) * (size - len(a)), b + (0,) * (size - len(b))


def resolve_config(project_root: Path) -> "Path | None":
    """Find the config in the same order `/planwise list` does.

    Use `planwise/config.yaml` under the project root when it is a planwise
    config. Otherwise take the first planwise `config.yaml` at the root itself
    or one level down, in alphabetical order. A config without the planwise
    marker is skipped. Return None when none qualifies.
    """
    try:
        import config_loader

        preferred = project_root / "planwise" / "config.yaml"
        if preferred.is_file() and config_loader._is_planwise_config(preferred):
            return preferred
        return config_loader.find_config_upward(project_root, stop_at=project_root)
    except Exception:  # noqa: BLE001 - a notice must never block a subcommand
        return None


def _shipped_version(plugin_root: Path) -> str:
    manifest = plugin_root / ".claude-plugin" / "plugin.json"
    return str(json.loads(manifest.read_text(encoding="utf-8"))["version"])


def _pinned_version(config: Path) -> str:
    from config_loader import read_config_mapping

    pin = read_config_mapping(config).get("plugin_version")
    return "" if pin is None else str(pin)


def notice(config: Path, plugin_root: Path) -> str:
    """Return the notice line, or an empty string when there is nothing to say."""
    try:
        shipped = _shipped_version(plugin_root)
        pinned = _pinned_version(config)
        if not shipped or not pinned:
            return ""
        pin_nums, ship_nums = _version_tuple(pinned), _version_tuple(shipped)
        if not pin_nums or not ship_nums:
            return ""
        pin_nums, ship_nums = _padded(pin_nums, ship_nums)
        behind = pin_nums < ship_nums
        ahead = pin_nums > ship_nums
    except BaseException:  # noqa: BLE001 - a notice must never block a subcommand
        return ""
    if behind:
        return (
            f"planwise: dispatching from {shipped}, config pins {pinned}"
            " — run /planwise upgrade to refresh"
        )
    if ahead:
        return (
            f"planwise: config pins {pinned}, but this session is dispatching"
            f" the older {shipped}"
            " — update the plugin, or restart the session so the newer install dispatches"
        )
    return ""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", required=True, type=Path)
    ap.add_argument("--plugin-root", type=Path, default=Path(__file__).resolve().parent.parent)
    try:
        args = ap.parse_args()
    except SystemExit:
        return 0
    line = notice(args.config, args.plugin_root)
    if line:
        sys.stdout.buffer.write((line + "\n").encode("utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
