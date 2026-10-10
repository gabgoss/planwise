"""Parse and validate the answers file that `--migration-answers` carries into an upgrade.

The upgrade handler asks the user the questions a migration cannot settle alone, then writes
each answer into one JSON file. The file is a top-level object. Each key answers one kind of
question, and each value is validated here before the upgrade writes anything.

    {"edge_drops": ["002->001", "003<->004:both"]}

`edge_drops` settles a reciprocal `blocks:` pair. `{a}->{b}` drops the edge from a to b,
and `{a}<->{b}:both` drops both directions. Ids are the bare numeric item ids.

A later question registers its key in `KNOWN_KEYS` with a validator. Nothing else changes.
"""
import json
import re
from pathlib import Path

_EDGE_ONE_WAY = re.compile(r"([0-9]+)->([0-9]+)")
_EDGE_BOTH = re.compile(r"([0-9]+)<->([0-9]+):both")

_EDGE_SHAPE = ('"edge_drops": ["<id>-><id>", "<id><-><id>:both"], '
               'for example ["002->001", "001<->002:both"]')


class AnswersError(Exception):
    """A malformed answers file. `reason` says what is wrong and `fix` says how to repair it."""

    def __init__(self, reason: str, fix: str) -> None:
        super().__init__(f"{reason} -- {fix}")
        self.reason = reason
        self.fix = fix


def parse_edge_drop(entry: object) -> list[tuple[str, str]] | None:
    """Return the (blocker, blocked) edges an `edge_drops` entry drops, or None if malformed.

    The one grammar for an entry: ASCII-digit ids, matched whole, ids returned as written.
    `{a}->{b}` drops [(a, b)]. `{a}<->{b}:both` drops [(a, b), (b, a)]. A pair of one id, in any zero padding, is None.
    """
    if not isinstance(entry, str):
        return None
    one_way = _EDGE_ONE_WAY.fullmatch(entry)
    both = _EDGE_BOTH.fullmatch(entry)
    match = one_way or both
    if match is None or match.group(1).lstrip("0") == match.group(2).lstrip("0"):  # '002->2' is a self pair
        return None
    a, b = match.groups()
    return [(a, b)] if one_way else [(a, b), (b, a)]


EDGE_DROP_FIX = (f"write each entry as <id>-><id> or <id><-><id>:both with two different "
                 f"ASCII-digit ids and no spaces, as in {_EDGE_SHAPE}")


def bad_edge_drop_reason(entry: object) -> str:
    """The reason text for an `edge_drops` entry `parse_edge_drop` rejects. The fix is `EDGE_DROP_FIX`."""
    return f'"edge_drops" entry {entry!r} has an unrecognised shape'


def _check_edge_drops(value: object) -> None:
    if not isinstance(value, list):
        raise AnswersError(
            f'"edge_drops" is a {type(value).__name__}, not a list',
            f"write it as {_EDGE_SHAPE}")
    for entry in value:
        if parse_edge_drop(entry) is None:
            raise AnswersError(bad_edge_drop_reason(entry), EDGE_DROP_FIX)


# The single place a later question registers its key: key -> validator.
KNOWN_KEYS = {"edge_drops": _check_edge_drops}


def load_answers(path: Path) -> dict:
    """Read and validate the answers file. Raises AnswersError on any violation."""
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        raise AnswersError(f"answers file {path} does not exist",
                           "pass the path of the JSON file the handler wrote") from None
    except (OSError, UnicodeDecodeError) as exc:
        raise AnswersError(f"answers file {path} cannot be read ({exc})",
                           "pass a readable UTF-8 JSON file") from exc
    except json.JSONDecodeError as exc:
        raise AnswersError(f"answers file {path} is not valid JSON ({exc})",
                           'rewrite it as one JSON object such as {"edge_drops": []}') from exc
    if not isinstance(data, dict):
        raise AnswersError(f"answers file {path} holds a {type(data).__name__}, not an object",
                           'rewrite it as one JSON object such as {"edge_drops": []}')
    for key, value in data.items():
        if key not in KNOWN_KEYS:
            raise AnswersError(
                f'answers file {path} has an unknown key "{key}"',
                f"use only these keys: {', '.join(sorted(KNOWN_KEYS))}")
        KNOWN_KEYS[key](value)
    return data
