"""``docs/upstream/OBSERVED.md`` as committed: what Eurostat does but never documents.

sdk-core's conventions §3 keep these notes in one file written by hand, each with the probe
that showed it: its date, its operation and its sample, a recording under ``tests/fixtures/``,
a file of the snapshot or a packaged list, or its request where the probe kept no answer.
Core's family check holds the file's row in ``FETCHED.md``, the label and the date that open
each note's last paragraph and the files its code spans cite (sdk-core ADR-0044, decision 1).
What stays here is the package's own (decision 3): each probe's operation and sample, the day
of each recording it cites, and that no dated note of what Eurostat answered stands outside
the file, in ``CLAUDE.md``, the README or a module of the package.
"""

import json
import re
from pathlib import Path

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
OPERATION = re.compile(r"`(\w+)`")
REFERENCE = re.compile(r"^\[[^\]\n]+\]: \S+\n?", re.MULTILINE)
"""A link reference definition, which renders as nothing and is no note's paragraph."""
DATED = re.compile(
    r"\b(?:recorded|probed|seen|observed|answered|measured|read)\b[^.;]*?"
    r"\b20\d\d-\d\d-\d\d\b"
    r"|\b20\d\d-\d\d-\d\d\b[^.;]*?\b(?:recorded|probed)\b"
    r"|\bnever seen\b|\bprobed\b"
)
"""How a text tells a probe of Eurostat: a date beside what was recorded, probed, seen,
answered, measured or read, a probe without one, or what was never seen. A date that an
example prints, a release time of a recorded answer, and a decision's date tell none."""
FENCE = re.compile(r"^```.*?^```", re.MULTILINE | re.DOTALL)


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
    """The last paragraph of each note names the operation it probed, by its WADL id, and a
    sample of the answer, or the request where the probe kept none."""
    known = operations()
    found = notes()
    assert found
    for heading, paragraphs in found.items():
        probe = paragraphs[-1]
        assert set(OPERATION.findall(probe)) & known, heading
        assert SAMPLE.search(probe) or REQUEST.search(probe), heading


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


def test_no_dated_note_stands_outside_the_notes() -> None:
    """What Eurostat was seen to do stands in ``OBSERVED.md`` alone, with its date and its
    recording: neither ``CLAUDE.md``, the README nor any module of the package tells it
    (sdk-core ``docs/conventions.md`` §3; https://github.com/xippios/sdk-eurostat/issues/49)."""
    paths = [ROOT / "CLAUDE.md", ROOT / "README.md", *sorted(PACKAGE.rglob("*.py"))]
    assert [found for path in paths for found in dated(path)] == []


def test_a_dated_note_is_found() -> None:
    """The check finds a probe where one stands: the note of ``OBSERVED.md`` that the README
    would repeat."""
    sentence = "the Comext base answers it with HTTP 404 (probed 2026-10-28)"
    assert DATED.search(sentence)
    assert not DATED.search("milk.meta.published_at  # 2026-10-05 23:00+02:00")


def test_the_rules_point_to_the_notes() -> None:
    """``CLAUDE.md`` and the README send a reader to the notes for what Eurostat does."""
    for path in (ROOT / "CLAUDE.md", ROOT / "README.md"):
        assert "docs/upstream/OBSERVED.md" in path.read_text(encoding="utf-8"), path.name
