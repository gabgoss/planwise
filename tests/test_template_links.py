#!/usr/bin/env python3
"""Guard: no markdown link in a template resolves only from `templates/`.

Plan creation and session closeout copy template content into a generated
plan folder (an Orchestration, a Recovery file, a Summary under `Outputs/`).
A link written relative to `templates/` resolves while the file sits in the
plugin, and points at nothing once the content is copied. The session
templates once linked `summary-template.md` and `../references/...` this way,
so every generated Orchestration, Recovery and Summary file shipped with dead
links, including the pointers to the rules a runner needs while filling in
the Recovery tables.

A template names a plugin file as inline code instead
(`references/read-confirm-act-protocol.md` §1.2), so nothing claims to be
navigable when it is not. A link whose target carries a `{placeholder}` names
a generated file and stays legal.

Run with:  python -m pytest tests/test_template_links.py -q
"""

import re
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent / "plugins" / "planwise"
TEMPLATES_DIR = PLUGIN_ROOT / "templates"

# An inline markdown link target, with an optional "title" after it.
_LINK_RE = re.compile(r"\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
_EXTERNAL_PREFIXES = ("http://", "https://", "mailto:", "#")


def plugin_relative_links(text: str, base_dir: Path) -> list[tuple[int, str]]:
    """Return (line number, target) for each link that only resolves from base_dir.

    A target counts when it climbs out of its folder (`../`) or names a file
    that exists relative to base_dir. Both resolve only where the template
    sits, never where its content is copied to.
    """
    offenders = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        for match in _LINK_RE.finditer(line):
            target = match.group(1)
            if target.startswith(_EXTERNAL_PREFIXES) or "{" in target:
                continue
            path_part = target.split("#", 1)[0]
            if path_part.startswith("../") or (base_dir / path_part).exists():
                offenders.append((lineno, target))
    return offenders


class TemplateLinksTests(unittest.TestCase):
    def test_scan_sees_templates_and_links(self):
        # Empty is not clean: the scan must see real files and real links.
        templates = sorted(TEMPLATES_DIR.glob("*.md"))
        self.assertGreaterEqual(len(templates), 10, f"templates seen: {templates}")
        link_count = sum(
            len(_LINK_RE.findall(t.read_text(encoding="utf-8"))) for t in templates
        )
        self.assertGreater(link_count, 0, "no markdown links seen in any template")

    def test_predicate_flags_plugin_relative_links(self):
        # Mutation control: the shapes that shipped broken must be caught.
        bad = (
            "see [rca §1.2](../references/read-confirm-act-protocol.md#12-x)\n"
            "fields in [summary](summary-template.md#consumption-record)\n"
            "per [orchestration.md](orchestration.md)'s checklist\n"
        )
        found = plugin_relative_links(bad, TEMPLATES_DIR)
        self.assertEqual([n for n, _ in found], [1, 2, 3], found)

    def test_predicate_passes_generated_and_external_links(self):
        good = (
            "| 1 | [{Abbrev}-S{XX}-01.md]({Abbrev}-S{XX}-01.md) |\n"
            "| [Outputs/](../Meta-{ABBREV}/Outputs/) |\n"
            "[issue](https://github.com/example/repo/issues/1) and [top](#top)\n"
            "see `references/read-confirm-act-protocol.md` §1.2\n"
        )
        self.assertEqual(plugin_relative_links(good, TEMPLATES_DIR), [])

    def test_no_template_links_resolve_only_from_templates_dir(self):
        offenders = []
        for template in sorted(TEMPLATES_DIR.glob("*.md")):
            text = template.read_text(encoding="utf-8")
            for lineno, target in plugin_relative_links(text, TEMPLATES_DIR):
                offenders.append(f"templates/{template.name}:{lineno}: ]({target})")
        self.assertEqual(
            offenders,
            [],
            "template links that resolve only from templates/ and break once "
            "the content is copied into a plan folder -- name the file as "
            "inline code instead:\n" + "\n".join(offenders),
        )


if __name__ == "__main__":
    unittest.main()
