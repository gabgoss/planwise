# Skill Authoring

## Invocation Control

A skill declares how it may be invoked. The AUTO-MODE tag marks a skill the router
may invoke without an explicit user request.

## Tag Forms

Two spellings are recognized and the summary keeps both:

- `AUTO-MODE` — the canonical hyphenated form.
- `AUTO-MODE-OFF` — the explicit opt-out.

A skill carrying neither tag inherits the project default.

## Migration Notes

Older skills used a bare boolean. Rewrite each to the AUTO-MODE form.

When a skill is split, both halves inherit the AUTO-MODE setting of the original.

A skill whose AUTO-MODE setting is ambiguous MUST be treated as opted out.

## Router Behaviour

The router reads the AUTO-MODE tag before considering the description field.

If the AUTO-MODE tag is absent, the router falls back to explicit invocation only.

## Verification

Confirm the AUTO-MODE tag survives a skill rename.

Confirm the AUTO-MODE tag is not duplicated across a split.

Confirm the AUTO-MODE tag round-trips through an upgrade.
