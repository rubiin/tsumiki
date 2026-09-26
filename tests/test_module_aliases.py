"""Static check: every ``module_alias.attribute`` reference must resolve.

``import utils.functions as helpers`` followed by ``helpers.some_name(...)`` is
only checked at runtime, so moving or renaming a helper leaves a working import
and an ``AttributeError`` the first time a user hovers a widget. These reference
bugs shipped twice in ``modules/notification.py`` (``set_cursor`` and
``load_file_pixbuf``, both of which live elsewhere), so the whole repo is
checked here instead.
"""

import ast
import importlib
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
# Only first-party module trees: resolving `fabric.*` would import GTK.
FIRST_PARTY = {"utils", "services", "shared", "widgets", "modules"}
SKIP_DIRS = {".venv", "docs", "tests", "example", ".git", "__pycache__", "node_modules"}


def iter_source_files():
    for path in sorted(REPO_ROOT.rglob("*.py")):
        if SKIP_DIRS & set(path.relative_to(REPO_ROOT).parts):
            continue
        yield path


def module_aliases(tree: ast.AST) -> dict[str, str]:
    """Map local alias -> dotted module for ``import x.y as z``."""
    aliases = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname:
                    aliases[alias.asname] = alias.name
    return aliases


def aliased_attribute_refs(tree: ast.AST) -> list[tuple[str, str, int]]:
    """Every ``alias.attr`` reference, as (alias, attr, lineno)."""
    aliases = module_aliases(tree)
    return [
        (node.value.id, node.attr, node.lineno)
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id in aliases
    ]


class ModuleAliasReferenceTest(unittest.TestCase):
    """A module alias must never be used for an attribute it does not have."""

    def test_every_aliased_attribute_exists(self):
        missing = []
        for path in iter_source_files():
            rel = path.relative_to(REPO_ROOT)
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(rel))
            for alias, attr, lineno in aliased_attribute_refs(tree):
                module = module_aliases(tree)[alias]
                if module.split(".")[0] not in FIRST_PARTY:
                    continue
                try:
                    mod = importlib.import_module(module)
                except Exception as exc:  # pragma: no cover - import failure
                    missing.append(f"{rel}:{lineno} cannot import {module}: {exc}")
                    continue
                if not hasattr(mod, attr):
                    missing.append(f"{rel}:{lineno} {module} has no attribute {attr!r}")

        self.assertEqual([], missing, "\n".join(missing))

    def test_the_check_actually_detects_a_missing_attribute(self):
        """Guard the guard: a typo in this file must not pass silently."""
        tree = ast.parse("import utils.functions as helpers\nhelpers.nope_xyz()\n")
        self.assertEqual(
            [("helpers", "nope_xyz", 2)], aliased_attribute_refs(tree)
        )

    def test_notification_cursor_helper_is_imported_from_its_real_home(self):
        """The reported bug: helpers.set_cursor does not exist."""
        from utils import functions
        from utils.widget_utils import set_cursor

        self.assertFalse(hasattr(functions, "set_cursor"))
        self.assertTrue(callable(set_cursor))


if __name__ == "__main__":
    unittest.main()
