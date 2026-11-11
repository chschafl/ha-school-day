"""Checks that the translation files render in the Home Assistant frontend."""

from __future__ import annotations

import json
from pathlib import Path
import re

import pytest

TRANSLATIONS = (
    Path(__file__).parent.parent / "custom_components/school_day/translations"
)


def _strings(node: object, path: str = ""):
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _strings(value, f"{path}.{key}" if path else key)
    elif isinstance(node, str):
        yield path, node


@pytest.mark.parametrize(
    "file", sorted(TRANSLATIONS.glob("*.json")), ids=lambda p: p.name
)
def test_strings_are_valid_messages(file: Path) -> None:
    """The frontend parses strings as ICU messages.

    "<...>" is read as a markup tag ("Translation error: INVALID_TAG") and
    braces may only wrap a simple placeholder name.
    """
    for path, text in _strings(json.loads(file.read_text(encoding="utf-8"))):
        assert "<" not in text and ">" not in text, f"{file.name} {path}: {text}"
        braces = re.sub(r"\{[a-z_]+\}", "", text)
        assert "{" not in braces and "}" not in braces, f"{file.name} {path}: {text}"


def test_languages_have_the_same_keys() -> None:
    """Every language translates the same strings as English."""
    english = {
        path for path, _ in _strings(json.loads((TRANSLATIONS / "en.json").read_text()))
    }
    for file in TRANSLATIONS.glob("*.json"):
        keys = {
            path for path, _ in _strings(json.loads(file.read_text(encoding="utf-8")))
        }
        assert keys == english, file.name
