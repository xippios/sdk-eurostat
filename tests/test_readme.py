"""``README.md``'s ``## Scope`` against the WADL files of the snapshot in ``docs/upstream/api/``.

The scope names each operation that the WADL files of Eurostat's main base document once, in
scope or out with its reason, and names each documented parameter of an operation the package
serves that a caller cannot set, with its public issue (sdk-core ``docs/conventions.md`` §2;
sdk-core ADR-0060, decision 8). The tests read the operations and their parameters from the
WADL files, so a capture that documents a new one fails here until the scope names it or a
task takes it. The README and ``get_data``'s docstring say which of Eurostat's two country
lists a filter takes, and the last test holds the codes they name against the packaged lists.
"""

import inspect
import re
import xml.etree.ElementTree as ElementTree
from collections import Counter
from pathlib import Path

from xippios.eurostat import params, tasks

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "docs" / "upstream" / "api"
GUIDE = ROOT / "docs" / "upstream" / "user-guide" / "api-detailed-guidelines"
WADL = "{http://wadl.dev.java.net/2009/02}"
MAIN_BASE = ("statistics-rest.wadl", "sdmx-rest.wadl", "catalogue.wadl", "async.wadl")
"""The WADL files of the main base: the Statistics, SDMX 2.1, Catalogue and asynchronous APIs.
The Comext base's under ``api/comext/`` are the same but for SDMX 3.0, which the scope leaves
out as one (https://github.com/xippios/sdk-eurostat/pull/11)."""
SERVED = {
    ("statistics-rest.wadl", "getData"): "get_data",
    ("sdmx-rest.wadl", "dataQuery"): "download_dataset",
    ("sdmx-rest.wadl", "codeListQuery"): "list_codes",
    ("catalogue.wadl", "getTocXml"): "list_datasets",
}
"""Each operation the package serves, by its WADL file and id, and the task that serves it."""
ISSUE = re.compile(r"https://github\.com/xippios/sdk-eurostat/issues/\d+")


def operations() -> dict[tuple[str, str], set[str]]:
    """Each ``GET`` operation of the main base's WADL files, by file and id, with every
    parameter of its resources and its request: a path's template and a query's names."""
    found: dict[tuple[str, str], set[str]] = {}

    def walk(file: str, resource: ElementTree.Element, inherited: set[str]) -> None:
        names = inherited | {p.get("name", "") for p in resource.findall(f"{WADL}param")}
        for method in resource.findall(f"{WADL}method"):
            if method.get("name") == "GET":
                query = {p.get("name", "") for p in method.iter(f"{WADL}param")}
                found.setdefault((file, method.get("id", "")), set()).update(names | query)
        for child in resource.findall(f"{WADL}resource"):
            walk(file, child, names)

    for file in MAIN_BASE:
        root = ElementTree.parse(API / file).getroot()
        for resources in root.findall(f"{WADL}resources"):
            for resource in resources.findall(f"{WADL}resource"):
                walk(file, resource, set())
    return found


def scope() -> str:
    """The text of the README's ``## Scope``, its lines joined by single spaces."""
    lines = (ROOT / "README.md").read_text(encoding="utf-8").splitlines()
    start = lines.index("## Scope") + 1
    end = next(i for i in range(start, len(lines)) if lines[i].startswith("## "))
    return " ".join(" ".join(lines[start:end]).split())


def cannot() -> list[str]:
    """The sentences of the scope that say what a caller cannot set."""
    return [part for part in re.split(r"(?<=\.) ", scope()) if "cannot set" in part]


def snake(name: str) -> str:
    """Upstream's camelCase name as the package spells it: ``flowRef``, ``flow_ref``."""
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def arguments() -> dict[tuple[str, str], set[str]]:
    """The arguments of the task that serves each served operation."""
    return {
        operation: set(inspect.signature(getattr(tasks, task)).parameters)
        for operation, task in SERVED.items()
    }


def sentences() -> list[str]:
    """The sentences of the scope."""
    return re.split(r"(?<=\.) ", scope())


def unnamed(taken: dict[tuple[str, str], set[str]]) -> list[str]:
    """Each documented parameter of a served operation that its task does not take, in
    ``taken``, by its snake_case name and no sentence of the scope names beside the task."""
    found = operations()
    return [
        f"{operation[1]}: {name}"
        for operation, arguments in taken.items()
        for name in sorted(found[operation])
        if snake(name) not in arguments
        and not any(
            f"`{name}`" in sentence and f"`{SERVED[operation]}`" in sentence
            for sentence in sentences()
        )
    ]


def page_row(page: str, parameter: str) -> str:
    """The row of a guide page's table of parameters that documents ``parameter``."""
    lines = (GUIDE / page).read_text(encoding="utf-8").splitlines()
    return next(line for line in lines if line.startswith(f"| {parameter} |"))


def forms() -> dict[str, set[str]]:
    """The values of ``format`` that the user guide documents for each served operation that
    takes one, by its task: the Statistics API's one value, the data query's and the
    codelist query's beside their default, SDMX-ML."""
    statistics = (GUIDE / "api-statistics.md").read_text(encoding="utf-8")
    return {
        "get_data": set(re.findall(r'only possible value is "(\w+)"', statistics)),
        "download_dataset": set(
            re.findall(r"\*\*([A-Z0-9_.-]+)\*\* for", page_row("sdmx2-1/data-query.md", "format"))
        ),
        "list_codes": set(
            re.findall(r"- (\w+) for", page_row("sdmx2-1/structure-queries.md", "format"))
        ),
    }


def test_the_main_base_documents_24_operations() -> None:
    """The count the scope states: 3 of the Statistics API, 8 of the SDMX 2.1 API, 11 of the
    Catalogue API and 2 of the asynchronous API, its ``getData`` beside the Statistics API's."""
    found = Counter(file for file, _ in operations())
    assert found == {
        "statistics-rest.wadl": 3,
        "sdmx-rest.wadl": 8,
        "catalogue.wadl": 11,
        "async.wadl": 2,
    }
    assert "24 operations" in scope()


def test_the_scope_names_each_documented_operation_once() -> None:
    """Each operation id stands in the scope as often as the WADL files document it: once,
    and ``getData`` twice, the Statistics API's and the asynchronous API's."""
    documented = Counter(operation for _, operation in operations())
    named = Counter(re.findall(r"`(\w+)`", scope()))
    assert {operation: named[operation] for operation in documented} == dict(documented)


def test_every_parameter_of_a_served_operation_is_an_argument_or_named() -> None:
    """A parameter that the WADL documents for an operation the package serves is an argument
    of its task, by its snake_case name, or the scope names it in a sentence with its task,
    as one the task sends fixed, or leaves out, or one a caller cannot set yet: ``get_data``
    takes ``datasetCode``, and a packaged list's task takes none of its operation's
    parameters."""
    assert unnamed(arguments()) == []


def test_a_parameter_that_no_task_takes_is_held_to_the_scope_s_word() -> None:
    """Were ``dataset_code`` no argument of ``get_data``, ``datasetCode`` would be a documented
    parameter that no task takes, and no sentence of the scope names it beside ``get_data``:
    the check finds it."""
    taken = arguments()
    taken[("statistics-rest.wadl", "getData")] -= {"dataset_code"}
    assert unnamed(taken) == ["getData: datasetCode"]


def test_each_documented_form_is_placed_beside_its_task() -> None:
    """Each value of ``format`` that the user guide documents stands in the scope in one
    sentence with its task, so the scope says of each whether the package sends it, leaves it
    out or leaves it to an issue: ``JSON``, the Statistics API's one value, the data query's
    four and the codelist query's two (``api-statistics.md:89``, ``sdmx2-1/data-query.md:23``,
    ``sdmx2-1/structure-queries.md:38``)."""
    documented = forms()
    assert documented == {
        "get_data": {"JSON"},
        "download_dataset": {"SDMX_2.1_STRUCTURED", "SDMX-CSV", "JSON", "TSV"},
        "list_codes": {"JSON", "TSV"},
    }
    missing = [
        task
        for task, values in documented.items()
        if not any(
            f"`{task}`" in sentence and all(f"`{value}`" in sentence for value in values)
            for sentence in sentences()
        )
    ]
    assert missing == []


def test_each_sentence_on_what_a_caller_cannot_set_cites_its_issue() -> None:
    """A documented parameter that a caller cannot set yet stands while the scope names it
    with its public issue (sdk-core ADR-0060, decision 8;
    https://github.com/xippios/sdk-core/issues/611)."""
    sentences = cannot()
    assert sentences, "the scope says what a caller cannot set"
    assert [sentence for sentence in sentences if not ISSUE.search(sentence)] == []


def test_the_two_country_lists_hold_the_codes_the_texts_name() -> None:
    """GEO writes Greece and the United Kingdom ``EL`` and ``UK``, and CXT_FREE_ISO ``GR`` and
    ``GB``, as the packaged lists hold them; the README and ``get_data``'s docstring say so in
    the lists' own labels, and which dimension takes which, with no table of the package's own
    (sdk-core ``docs/conventions.md`` §14, sentence 3)."""
    geo = {code.code: code.label for code in params.codes("geo")}
    free_iso = {code.code: code.label for code in params.codes("cxt_free_iso")}
    assert (geo["EL"], geo["UK"]) == ("Greece", "United Kingdom")
    assert (free_iso["GR"], free_iso["GB"]) == ("Greece", "United Kingdom")
    assert not {"GR", "GB"} & geo.keys()
    assert not {"EL", "UK"} & free_iso.keys()
    readme = " ".join((ROOT / "README.md").read_text(encoding="utf-8").split())
    docstring = " ".join((tasks.get_data_async.__doc__ or "").split())
    for text in (readme, docstring):
        for code in ("EL", "UK", "GR", "GB", "GEO", "CXT_FREE_ISO"):
            assert re.search(rf"\b{code}\b", text), code
