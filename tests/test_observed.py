"""``docs/upstream/OBSERVED.md`` as committed: what Eurostat does but never documents.

sdk-core's conventions §3 keep these notes in one file written by hand, each with the probe
that showed it: its date, its operation and its sample, a recording under ``tests/fixtures/``,
a file of the snapshot or a packaged list, or its request where the probe kept no answer.
Core's family check holds the file's row in ``FETCHED.md``, the label and the date that open
each note's last paragraph and the files its code spans cite (sdk-core ADR-0044, decision 1).
What stays here is the package's own (decision 3): each probe's operation and sample, the day
of each recording it cites, that no dated note of what Eurostat answered stands outside
the file, in ``CLAUDE.md``, the README, a module of the package or the docstrings of the
tests and the scripts, and that the first three cite each note by its heading.
"""

import ast
import io
import json
import re
import tokenize
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "xippios" / "eurostat"
UPSTREAM = ROOT / "docs" / "upstream"
OBSERVED = UPSTREAM / "OBSERVED.md"
DATE = re.compile(r"\b20\d\d-\d\d-\d\d\b")
SAMPLE = re.compile(
    r"`((?:tests/fixtures|docs/upstream|src/xippios/eurostat/reference)/[^`\s]+\.[a-z]+)`"
)
"""A sample a probe names: a recording, a file of the snapshot or a packaged list."""
REQUEST = re.compile(r"`GET (?:https://\S+|[a-z][^`\s]*)`")
"""A request a probe names where it kept no answer, as sent: ``GET <path or URL>``."""
WEBSITE = re.compile(r"`GET https://ec\.europa\.eu/eurostat/web/\S+`")
"""A request to Eurostat's website, whose pages no WADL file lists as an operation."""
NOT_KEPT = re.compile(r"\bkept no answer\b|\bnot kept\b")
OPERATION = re.compile(r"`(\w+)`")
REFERENCE = re.compile(r"^\[[^\]\n]+\]: \S+\n?", re.MULTILINE)
"""A link reference definition, which renders as nothing and is no note's paragraph."""
DATED = re.compile(
    r"\b(?:recorded|probed|seen|observed|answered|measured|read)\b[^.;]*?"
    r"\b20\d\d-\d\d-\d\d\b"
    r"|\b20\d\d-\d\d-\d\d\b[^.;]*?\b(?:recorded|probed)\b"
    r"|\bnever seen\b|\bprobed\b",
    re.IGNORECASE,
)
"""How a text tells a probe of Eurostat: a date beside what was recorded, probed, seen,
answered, measured or read, a probe without one, or what was never seen, in any case, so
that a sentence that opens "Recorded on" counts. A date that an example prints, a release
time of a recorded answer, and a decision's date tell none."""
FENCE = re.compile(r"^```.*?^```", re.MULTILINE | re.DOTALL)
CITATION = re.compile(
    r"`docs/upstream/OBSERVED\.md`+(?P<headings>, \"[^\"]+\"(?:(?:,|,? and) \"[^\"]+\")*)?"
)
"""The path of the notes in code spans, as ``CLAUDE.md``, the README and a module write it,
with the headings of the notes it cites after a comma, one or several, ``"<heading>"``,
``"<heading>" and "<heading>"``; a path that no heading follows cites the file alone, however
its sentence goes on."""
DESCRIPTION = "What Eurostat does that its documentation does not state stands in"
"""How ``CLAUDE.md`` opens its description of the notes, the one place that names their path
and cites no note: it says what the file holds."""


def text() -> str:
    return OBSERVED.read_text(encoding="utf-8")


def notes() -> dict[str, list[str]]:
    """Each note's heading and its paragraphs, each paragraph's lines joined by a space.

    A ``##`` heading groups notes and is none itself.
    """
    parts = re.split(r"^(##|###) (.+)$", REFERENCE.sub("", text()), flags=re.MULTILINE)
    return {
        heading: [" ".join(block.split()) for block in body.split("\n\n") if block.strip()]
        for level, heading, body in zip(parts[1::3], parts[2::3], parts[3::3], strict=True)
        if level == "###"
    }


def operations() -> set[str]:
    """The id of every ``GET`` operation of the snapshot's WADL files, both bases'."""
    return {
        match
        for path in sorted((UPSTREAM / "api").rglob("*.wadl"))
        for match in re.findall(r'id="(\w+)" name="GET"', path.read_text(encoding="utf-8"))
    }


def test_every_probe_names_an_operation_of_the_snapshot_and_its_sample() -> None:
    """The last paragraph of each note names the operation it probed, by its WADL id, or
    the request to Eurostat's website that it sent, and a sample of the answer, or the
    request where the probe kept none."""
    known = operations()
    found = notes()
    assert found
    for heading, paragraphs in found.items():
        probe = paragraphs[-1]
        assert set(OPERATION.findall(probe)) & known or WEBSITE.search(probe), heading
        assert SAMPLE.search(probe) or REQUEST.search(probe), heading


def test_a_probe_that_kept_no_answer_names_its_request() -> None:
    """Where no recording holds the answer, the request stands in its place, in the sentence
    or the clause that says so (sdk-core ``docs/conventions.md`` §3: a probe names "its
    sample, a request or the fixture that holds the answer")."""
    found = [
        f"{heading}: {clause}"
        for heading, paragraphs in notes().items()
        for clause in re.split(r"(?<=[.;]) ", paragraphs[-1])
        if NOT_KEPT.search(clause) and not REQUEST.search(clause)
    ]
    assert found == []


def test_every_recording_a_probe_cites_has_its_day_among_the_probe_s_dates() -> None:
    """A recording's day, from its ``recorded_at``, is a date of its ``Probe:`` paragraph."""
    for heading, paragraphs in notes().items():
        probe = paragraphs[-1]
        for path in SAMPLE.findall(probe):
            if path.startswith("tests/fixtures/") and path.endswith(".json"):
                recorded = json.loads((ROOT / path).read_text(encoding="utf-8"))["recorded_at"]
                assert recorded[:10] in DATE.findall(probe), f"{heading}: {path}"


def dated(path: Path) -> list[str]:
    """What tells a probe in ``path``, its fenced code blocks, a README's examples, left out."""
    body = " ".join(FENCE.sub("", path.read_text(encoding="utf-8")).split())
    return [f"{path.relative_to(ROOT)}: {match.group(0)}" for match in DATED.finditer(body)]


def docstrings(path: Path) -> list[str]:
    """The docstrings and the comments of a module of the tests or the scripts: the module's,
    each class's and function's docstring, each string that stands as a statement, a
    constant's docstring, and each comment, the comments of one block joined."""
    source = path.read_text(encoding="utf-8")
    strings = [
        node.value.value
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    ]
    blocks: list[list[str]] = []
    last = -2
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type == tokenize.COMMENT:
            line = token.start[0]
            if line != last + 1 or not blocks:
                blocks.append([])
            blocks[-1].append(token.string.lstrip("#"))
            last = line
    return strings + [" ".join(block) for block in blocks]


def dated_docstrings(path: Path) -> list[str]:
    """What tells a probe in the docstrings and the comments of ``path``."""
    return [
        f"{path.relative_to(ROOT)}: {match.group(0)}"
        for text in docstrings(path)
        for match in DATED.finditer(" ".join(text.split()))
    ]


def test_no_dated_note_stands_outside_the_notes() -> None:
    """What Eurostat was seen to do stands in ``OBSERVED.md`` alone, with its date and its
    recording: neither ``CLAUDE.md``, the README nor any module of the package tells it
    (sdk-core ``docs/conventions.md`` §3; https://github.com/xippios/sdk-eurostat/issues/49)."""
    paths = [ROOT / "CLAUDE.md", ROOT / "README.md", *sorted(PACKAGE.rglob("*.py"))]
    assert [found for path in paths for found in dated(path)] == []


def test_no_dated_note_stands_in_the_docstrings_of_the_tests_and_the_scripts() -> None:
    """A test or a script says what it replays or sends and cites the note for what Eurostat
    answered: no docstring or comment of ``tests/`` or ``scripts/`` tells a probe. This
    module spells the pattern it looks for and is left out."""
    paths = [
        *sorted((ROOT / "tests").glob("*.py")),
        *sorted((ROOT / "scripts").glob("*.py")),
    ]
    found = [
        hit for path in paths if path.name != Path(__file__).name for hit in dated_docstrings(path)
    ]
    assert found == []


def test_a_dated_note_is_found() -> None:
    """The check finds a probe where one stands: the note of ``OBSERVED.md`` that the README
    would repeat."""
    sentence = "the Comext base answers it with HTTP 404 (probed 2026-10-28)"
    assert DATED.search(sentence)
    assert DATED.search("Recorded on the Comext base on 2026-10-28: an empty cube")
    assert not DATED.search("milk.meta.published_at  # 2026-10-05 23:00+02:00")


def cited(match: re.Match[str]) -> list[str]:
    """The headings that a citation names, none where it cites the path alone."""
    return re.findall(r"\"([^\"]+)\"", match["headings"] or "")


def citations(path: Path) -> list[re.Match[str]]:
    """Each citation of the notes in ``path``, its lines joined by single spaces, but the
    description of the notes in ``CLAUDE.md``."""
    body = " ".join(path.read_text(encoding="utf-8").split())
    return [
        match
        for match in CITATION.finditer(body)
        if not (path.name == "CLAUDE.md" and body[: match.start()].rstrip().endswith(DESCRIPTION))
    ]


def test_every_citation_of_the_notes_names_a_heading_of_the_file() -> None:
    """``CLAUDE.md``, the README and the package's modules cite a note by its heading, as the
    file's opening paragraph has it: no citation names the path alone, and each heading named
    stands in the file as written (https://github.com/xippios/sdk-eurostat/issues/97)."""
    headings = notes().keys()
    paths = [ROOT / "CLAUDE.md", ROOT / "README.md", *sorted(PACKAGE.rglob("*.py"))]
    found = [(path.relative_to(ROOT), match) for path in paths for match in citations(path)]
    assert [f"{path}: {match.group(0)}" for path, match in found if not cited(match)] == []
    assert [
        f"{path}: {heading}"
        for path, match in found
        for heading in cited(match)
        if heading not in headings
    ] == []


@pytest.mark.parametrize(
    "alone",
    [
        "answers with HTTP 404 (``docs/upstream/OBSERVED.md``)",
        "(``tests/fixtures/data_query/``; ``docs/upstream/OBSERVED.md``).",
        "is answered (`docs/upstream/OBSERVED.md`); and",
        "the snapshot does not state it, as ``docs/upstream/OBSERVED.md``.",
        "(``docs/upstream/OBSERVED.md``, each note with its probe)",
        "as the notes of ``docs/upstream/OBSERVED.md`` give each with its probe:",
    ],
    ids=["parenthesis", "after a semicolon", "before a semicolon", "full stop", "words", "prose"],
)
def test_a_citation_of_the_path_alone_is_found(alone: str) -> None:
    """The check finds the path that no heading follows, however its sentence goes on."""
    match = CITATION.search(alone)
    assert match is not None
    assert cited(match) == []


def test_the_headings_after_the_path_are_the_notes_cited() -> None:
    """One heading after the path, or several joined by commas and ``and``."""
    one = CITATION.search(
        '(``docs/upstream/OBSERVED.md``, "A leaf may print its number of values empty")'
    )
    assert one is not None
    assert cited(one) == ["A leaf may print its number of values empty"]
    three = CITATION.search(
        '(``docs/upstream/OBSERVED.md``, "The refusal of `geo` with `geoLevel` comes as an'
        ' array", "The asynchronous answer comes as an `error` array" and "The Comext base'
        ' reads a filter on a dimension the dataset lacks as none"):'
    )
    assert three is not None
    assert cited(three) == [
        "The refusal of `geo` with `geoLevel` comes as an array",
        "The asynchronous answer comes as an `error` array",
        "The Comext base reads a filter on a dimension the dataset lacks as none",
    ]


def test_the_description_of_the_notes_in_claude_md_cites_none() -> None:
    """``CLAUDE.md``'s description of the notes names the file and no note, and the check
    leaves it out, that alone."""
    path = ROOT / "CLAUDE.md"
    body = " ".join(path.read_text(encoding="utf-8").split())
    assert f"{DESCRIPTION} `docs/upstream/OBSERVED.md` once" in body
    assert len(list(CITATION.finditer(body))) == len(citations(path)) + 1


def test_the_rules_point_to_the_notes() -> None:
    """``CLAUDE.md``, the README and the capture script, whose pace answers the website's
    request budget, send a reader to the notes for what Eurostat does."""
    for path in (ROOT / "CLAUDE.md", ROOT / "README.md", ROOT / "scripts" / "refresh_upstream.py"):
        assert "docs/upstream/OBSERVED.md" in path.read_text(encoding="utf-8"), path.name
