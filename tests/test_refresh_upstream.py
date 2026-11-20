"""``scripts/refresh_upstream.py``'s ``FETCHED.md``, rendered offline from rows of the test's own.

Nothing here sends a request: ``render_fetched`` takes what a capture run fetched, here a
row and a quoted notice made up for the render alone, never written to ``docs/upstream/``.
"""

import importlib.util
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "refresh_upstream.py"
FETCHED = "2026-11-20T09:00:00Z"
HAND = "written by hand: what upstream does but never documents; not fetched or checked"


def load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("refresh_upstream", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


script = load_script()


def render(*, observed: bool) -> str:
    row = script.Row("user-guide/page.md", "https://example.test/page", b"# Page\n", "a note")
    quoted = script.Attribution("licence", "reuse", "exceptions", "modification", ["cite"])
    text: str = script.render_fetched([row], [], quoted, FETCHED, observed)
    return text


def test_fetched_md_lists_observed_md_in_a_row_of_its_own() -> None:
    """``OBSERVED.md``, the one file under ``docs/upstream/`` written by hand, has a row
    that says so once it exists (conventions §3, sdk-core ADR-0028 decision 5)."""
    text = render(observed=True)
    assert f"| {script.OBSERVED} | - | - | - | - | {HAND} |" in text.splitlines()
    assert f"edited by hand but `{script.OBSERVED}`" in " ".join(text.split())


def test_fetched_md_names_no_observed_md_while_there_is_none() -> None:
    text = render(observed=False)
    assert script.OBSERVED not in text
    assert "Nothing here was edited by hand." in " ".join(text.split())
