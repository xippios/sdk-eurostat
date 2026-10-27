"""Refresh the packaged reference data from upstream (``/refresh-reference-data``).

Every list in ``LISTS`` or ``ID_LISTS`` is fetched through the layer-1 wrappers in
``api/``, never through a task that might answer from the package, and written to
``reference/<name>.json`` with the fetch date, an id list as upstream's records under
upstream's field names; then ``enums.py`` is regenerated with one
``xippios.core.reference.render_enums`` call, ASCII-only, and formatted with
``ruff format`` and ``ruff check --fix``, to be committed as formatted (ADR-0008,
amendment 2026-10-27). A value list in ``LISTS`` becomes a ``StrEnum``; a list of integer
ids and names in ``ID_LISTS`` becomes, through ``id_name_pairs``, an ``IntEnum``, so that a
member compares equal to the id in upstream's data (conventions §3). One module holds
both kinds; a list's name is in one of the two mappings, never in both.

Only lists that are the same for every caller are packaged; a multi-tenant source
packages no tenant data (ADR-0014). Run from the repository root, with whatever the list
endpoints need in the environment (a key only where they take one)::

    uv run python scripts/refresh_reference.py

``--render-only`` regenerates ``enums.py`` from the packaged ``reference/*.json`` alone,
without a request and without a key: after a core release changes the renderer
(conventions §15, item 6), it changes ``enums.py`` and nothing else.
"""

import argparse
import json
import subprocess
import sys
from collections.abc import Callable, Coroutine, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from xippios.core import UpstreamModel, sync
from xippios.core.reference import id_name_pairs, render_enums

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DIR = ROOT / "src/xippios/eurostat"
REFERENCE = PACKAGE_DIR / "reference"
ENUMS = PACKAGE_DIR / "enums.py"
GENERATOR = "scripts/refresh_reference.py"

LISTS: dict[str, Callable[[], Coroutine[Any, Any, list[str]]]] = {
    # name of the list, as upstream calls it, to an async fetcher through api/, e.g.
    # "country_code": lambda: api.list_countries(),
}
"""Value lists, one ``StrEnum`` each; keep ``params.PACKAGED_LISTS`` in step with the keys."""

ID_LISTS: dict[str, tuple[str, str, Callable[[], Coroutine[Any, Any, Sequence[UpstreamModel]]]]] = {
    # name of the list to (id field, name field, async fetcher of its records through api/),
    # the fields as upstream names them, e.g.
    # "unit_id": ("unitId", "unitDescription", lambda: api.list_units()),
}
"""Lists of integer ids and names, one ``IntEnum`` each (conventions §3).

Packaged as upstream's records under upstream's field names (``upstream_record``), as a
table keeps upstream's column names; ``params.packaged_values`` reads value lists only, so
these stay out of ``params.PACKAGED_LISTS``.
"""


def upstream_record(record: UpstreamModel) -> dict[str, Any]:
    """``record`` as JSON under upstream's field names, for ``reference/<name>.json``.

    A field's upstream name is its ``Field(validation_alias=...)`` where the model has a
    string one, else the field's own name. The models set no serialisation alias
    (``models.py``), so ``model_dump(by_alias=True)`` would not restore upstream's names;
    values are dumped as JSON, a ``Decimal`` as a number, a date as ISO text.
    """
    upstream = {
        name: info.validation_alias if isinstance(info.validation_alias, str) else name
        for name, info in type(record).model_fields.items()
    }
    dumped = record.model_dump(mode="json")
    return {upstream.get(name, name): value for name, value in dumped.items()}


def write(name: str, fetched: str, key: str, rows: Sequence[object]) -> None:
    """Write ``reference/<name>.json``: the list's name, the fetch date and ``rows`` as ``key``."""
    path = REFERENCE / f"{name}.json"
    payload = {"param": name, "fetched": fetched, key: list(rows)}
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"{path.name}: {len(rows)} {key}")  # noqa: T201


def read(name: str) -> dict[str, Any]:
    """The packaged ``reference/<name>.json``, as ``write`` wrote it."""
    path = REFERENCE / f"{name}.json"
    if not path.is_file():
        raise SystemExit(f"{path.name} is not packaged yet: run the script without --render-only")
    payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return payload


def render(
    lists: Mapping[str, Sequence[str] | Sequence[tuple[int, str]]],
    fetched: Mapping[str, str],
) -> None:
    """Write ``enums.py`` with one ``render_enums`` call, then format it with ruff.

    A value list renders a ``StrEnum``, a list of ``(id, name)`` pairs an ``IntEnum``, each
    class docstring naming its list's date in ``fetched``. ``ruff format`` and
    ``ruff check --fix`` then choose the quotes, wrap what fits and sort ``__all__``; the
    module is committed as formatted (ADR-0008, amendment 2026-10-27).
    """
    ENUMS.write_text(render_enums(lists, fetched=fetched, generator=GENERATOR), encoding="utf-8")
    for command in (["format"], ["check", "--fix"]):
        subprocess.run([sys.executable, "-m", "ruff", *command, str(ENUMS)], check=True, cwd=ROOT)


def refresh() -> None:
    """Fetch every list, write its file and regenerate ``enums.py``."""
    today = datetime.now(UTC).date().isoformat()
    REFERENCE.mkdir(exist_ok=True)
    lists: dict[str, Sequence[str] | Sequence[tuple[int, str]]] = {}
    for name, fetch in LISTS.items():
        values = sync(fetch)()
        write(name, today, "values", values)
        lists[name] = values
    for name, (id_field, name_field, fetch_records) in ID_LISTS.items():
        records = [upstream_record(record) for record in sync(fetch_records)()]
        write(name, today, "records", records)
        lists[name] = id_name_pairs(records, id_field=id_field, name_field=name_field)
    render(lists, dict.fromkeys(lists, today))
    print(f"{ENUMS.name}: {len(lists)} enums")  # noqa: T201


def render_only() -> None:
    """Regenerate ``enums.py`` from the packaged files, without a request.

    Each list keeps the date its file records, so lists fetched on different days render
    with their own dates.
    """
    lists: dict[str, Sequence[str] | Sequence[tuple[int, str]]] = {}
    fetched: dict[str, str] = {}
    for name in LISTS:
        payload = read(name)
        lists[name] = payload["values"]
        fetched[name] = payload["fetched"]
    for name, (id_field, name_field, _) in ID_LISTS.items():
        payload = read(name)
        lists[name] = id_name_pairs(payload["records"], id_field=id_field, name_field=name_field)
        fetched[name] = payload["fetched"]
    render(lists, fetched)
    print(f"{ENUMS.name}: {len(lists)} enums, from the packaged files")  # noqa: T201


def main() -> None:
    """Refresh from upstream, or with ``--render-only`` regenerate ``enums.py`` alone."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument(
        "--render-only",
        action="store_true",
        help="regenerate enums.py from the packaged reference/*.json, without a request or a key",
    )
    args = parser.parse_args()
    if shared := sorted(LISTS.keys() & ID_LISTS.keys()):
        raise SystemExit(f"a list is named in both LISTS and ID_LISTS: {shared}")
    if args.render_only:
        render_only()
    else:
        refresh()


if __name__ == "__main__":
    main()
