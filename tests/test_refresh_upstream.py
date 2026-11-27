"""The capture script's declaration and its hooks on core's frame, offline: nothing is fetched.

``scripts/refresh_upstream.py`` declares its snapshot, ``SNAPSHOT``, to ``xippios.core.refresh``,
whose fetch, redirects, retry, attribution check, ``FETCHED.md`` with its row of
``OBSERVED.md``, write and ``--check`` core's tests hold (sdk-core ADR-0062), as core's family
check holds the notes of ``OBSERVED.md`` (sdk-core ADR-0044). What stays here is the script's
own: its pages, its client of the website and the wait it gives a 429, its attribution, and its
hooks, the converter of the user-guide pages, the rule that keeps a WADL file as recorded, the
rows' notes and the checks of the samples, and the sentence that names the two pages of
Eurostat's wiki, which it never requests. A hook
is handed an answer built from a file under ``docs/upstream/`` or from a literal of the page's
shape, never one fetched.
"""

import ast
import importlib.util
import re
from pathlib import Path
from types import ModuleType
from urllib.parse import urlsplit

import pytest
from xippios.core import RetryPolicy
from xippios.core.refresh import Page, Response, Row

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "refresh_upstream.py"
UPSTREAM = ROOT / "docs" / "upstream"
GUIDE = "https://ec.europa.eu/eurostat/web/user-guides/data-browser/api-data-access/"
API = "https://ec.europa.eu/eurostat/api/dissemination/"
COMEXT = "https://ec.europa.eu/eurostat/api/comext/dissemination/"


def load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("refresh_upstream", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


script = load_script()


def declared(url: str) -> Page:
    """The page that ``SNAPSHOT`` declares at ``url``."""
    pages: tuple[Page, ...] = script.SNAPSHOT.pages
    (found,) = [page for page in pages if page.url == url]
    return found


def answer(
    url: str,
    body: bytes,
    *,
    status: int = 200,
    content_type: str | None = None,
    redirects: tuple[tuple[int, str], ...] = (),
) -> Response:
    """The answer at ``url`` as the frame hands it to a hook.

    The body is an input of the test, not an answer from Eurostat: a file under
    ``docs/upstream/`` as the snapshot keeps it, or a literal of the page's shape.
    """
    return Response(
        url=url,
        status=status,
        body=body,
        content_type=content_type,
        etag=None,
        last_modified=None,
        redirects=redirects,
    )


def kept(page: Page) -> Response:
    """The answer to ``page`` as the snapshot keeps its file under ``docs/upstream/``."""
    assert page.file is not None
    return answer(page.url, (UPSTREAM / page.file).read_bytes())


def kept_row(page: Page) -> Row:
    """The row of ``page`` with its file as the snapshot keeps it, its answer that file."""
    response = kept(page)
    return Row(page, response, response.body, page.note)


# --- the declaration -------------------------------------------------------------------


PAGES = (
    *(
        (f"{GUIDE}{path}", f"user-guide/{path}.md")
        for path in (
            "api-introduction",
            "api-getting-started",
            "api-getting-started/api",
            "api-getting-started/sdmx2.1",
            "api-getting-started/catalogue-api",
            "api-getting-started/comext-database",
            "api-detailed-guidelines",
            "api-detailed-guidelines/api-statistics",
            "api-detailed-guidelines/asynchronous-api",
            "api-detailed-guidelines/catalogue-api",
            "api-detailed-guidelines/catalogue-api/toc",
            "api-detailed-guidelines/catalogue-api/dcat",
            "api-detailed-guidelines/prefixed-datasets",
            "api-detailed-guidelines/sdmx2-1",
            "api-detailed-guidelines/sdmx2-1/data-query",
            "api-detailed-guidelines/sdmx2-1/structure-queries",
            "api-faq",
            "api-faq/tsv-format",
        )
    ),
    (f"{API}statistics/1.0/statistics-rest.wadl", "api/statistics-rest.wadl"),
    (f"{API}sdmx/2.1/sdmx-rest.wadl", "api/sdmx-rest.wadl"),
    (f"{API}catalogue/catalogue.wadl", "api/catalogue.wadl"),
    (f"{API}1.0/async/async.wadl", "api/async.wadl"),
    (f"{API}swagger-ui/sdmx-rest.yaml", "api/sdmx-rest.yaml"),
    (f"{COMEXT}statistics/1.0/statistics-rest.wadl", "api/comext/statistics-rest.wadl"),
    (f"{COMEXT}sdmx/2.1/sdmx-rest.wadl", "api/comext/sdmx-rest.wadl"),
    (f"{COMEXT}sdmx/3.0/sdmx-rest.wadl", "api/comext/sdmx-rest-3.0.wadl"),
    (f"{COMEXT}catalogue/catalogue.wadl", "api/comext/catalogue.wadl"),
    (f"{COMEXT}1.0/async/async.wadl", "api/comext/async.wadl"),
    (
        f"{API}statistics/1.0/data/apro_mk_cola?format=JSON&lang=EN&geo=AT&time=2022&time=2023",
        "samples/apro_mk_cola-json-stat.json",
    ),
    (
        f"{API}sdmx/2.1/data/apro_mk_cola/A...THS_T.AT"
        "?format=SDMX-CSV&startPeriod=2022&endPeriod=2023",
        "samples/apro_mk_cola-sdmx-csv.csv",
    ),
    (
        f"{COMEXT}statistics/1.0/data/DS-059358?format=JSON&lang=EN&reporter=AT"
        "&product=10411200&sinceTimePeriod=2022&untilTimePeriod=2023",
        "samples/DS-059358-json-stat.json",
    ),
    (
        f"{COMEXT}sdmx/2.1/data/DS-059358/A.AT.10411200."
        "?format=SDMX-CSV&startPeriod=2022&endPeriod=2023",
        "samples/DS-059358-sdmx-csv.csv",
    ),
    ("https://ec.europa.eu/eurostat/web/main/help/copyright-notice", None),
)
"""The 33 URLs the snapshot requests, each with its file, in the order of the requests."""


def test_the_snapshot_declares_its_33_pages_in_the_order_it_requests_them() -> None:
    """The 18 user-guide pages, the 10 documents and the 4 samples, then the copyright
    notice, the one row without a file; the hooks are the script's."""
    snapshot = script.SNAPSHOT
    assert len(PAGES) == 33
    assert [(page.url, page.file) for page in snapshot.pages] == list(PAGES)
    assert (snapshot.name, snapshot.slug) == ("Eurostat dissemination API", "eurostat")
    assert snapshot.out == UPSTREAM
    hooks = (snapshot.reduce, snapshot.canonical, snapshot.note, snapshot.sections)
    assert hooks == (script.reduce, script.canonical, script.note, script.sections)
    assert snapshot.variables == ()


def test_the_samples_are_marked_and_the_html_pages_record_no_size() -> None:
    """The four answers of the API are samples; the user-guide pages and the copyright
    notice carry a per-request token in their HTML, so their rows record no size or sha256,
    while the documents, kept verbatim, record theirs."""
    pages = script.SNAPSHOT.pages
    assert [page.file for page in pages if page.sample] == [
        file for _, file in PAGES if file and file.startswith("samples/")
    ]
    html = [page.url for page in pages if not page.stable]
    assert html == [url for url, file in PAGES if (file or "").startswith("user-guide/")] + [
        script.COPYRIGHT_URL
    ]


def test_every_request_goes_through_the_websites_client_five_seconds_apart() -> None:
    """The client sends no credential and keeps no answer; one retry, after the wait a 429
    names, at least 10 s and at most 900 s (sdk-core ADR-0062, decision 4)."""
    snapshot = script.SNAPSHOT
    assert snapshot.client is script.CLIENT
    assert snapshot.pause == 5.0
    config = script.CLIENT.config
    assert config.retry == RetryPolicy(
        max_attempts=2, backoff_base=10.0, backoff_max=900.0, jitter=False
    )
    assert (config.classify, config.observe) == (script.classify, script.observe)
    assert (config.source, config.cache) == ("eurostat", None)
    assert script.CLIENT._auth is None


@pytest.mark.parametrize(
    ("headers", "wait"),
    [
        ({"X-Rate-Limit-Retry-After-Seconds": "120", "Retry-After": "30"}, 120.0),
        ({"Retry-After": "30"}, 30.0),
        ({"X-Rate-Limit-Retry-After-Seconds": "soon", "Retry-After": "45"}, 45.0),
        ({"X-Rate-Limit-Remaining": "0"}, 60.0),
    ],
)
def test_a_429_waits_as_long_as_the_website_asks(headers: dict[str, str], wait: float) -> None:
    """The website's own header first, then ``Retry-After``, else 60 s. The headers are an
    input of the test, not an answer from Eurostat."""
    assert script.quota_wait(headers) == wait


@pytest.mark.parametrize(("asked", "waited"), [(None, 10.0), (60.0, 60.0), (900.0, 900.0)])
def test_the_retry_policy_waits_the_429_at_least_ten_seconds(
    asked: float | None, waited: float
) -> None:
    """The frame asks the client's policy for the wait of its one retry."""
    assert script.CLIENT.config.retry.delay(1, retry_after=asked) == waited


def test_a_429_that_asks_for_more_than_900_seconds_is_not_retried() -> None:
    """The policy gives no wait past its bound, so the run stops on the 429."""
    policy = script.CLIENT.config.retry
    assert policy.delay(1, retry_after=901.0) is None
    assert policy.delay(2, retry_after=10.0) is None


def test_the_script_fetches_through_the_frame_alone() -> None:
    """No fetch of its own: it imports no ``urllib.request`` and runs ``run(SNAPSHOT)``."""
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported |= {node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    assert not {name for name in imported if name.startswith("urllib.request")}
    assert "raise SystemExit(run(SNAPSHOT))" in SCRIPT.read_text(encoding="utf-8")
    assert not SCRIPT.read_text(encoding="utf-8").startswith("# /// script")


def test_the_pages_not_requested_are_the_ones_the_user_guide_links() -> None:
    """Thirteen pages and resources are listed under Not fetched with their reason."""
    listed = [(page.url, page.reason) for page in script.SNAPSHOT.not_fetched]
    assert listed == list(script.NOT_REQUESTED)
    assert len(listed) == 13
    assert all(reason for _, reason in listed)


# --- the attribution -------------------------------------------------------------------


def _recorded_attribution() -> str:
    """``FETCHED.md``'s text without Markdown's links, quotes and list markers, flattened."""
    lines = (UPSTREAM / "FETCHED.md").read_text(encoding="utf-8").splitlines()
    text = " ".join(re.sub(r"^[>\s]*(?:- )?", "", line) for line in lines)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    return " ".join(text.split())


def test_the_attribution_stands_on_the_copyright_notice_which_is_the_terms() -> None:
    """Every statement is printed in Eurostat's copyright notice, the one page marked
    ``terms``: each run checks that it prints them all, and searches nothing else on it."""
    snapshot = script.SNAPSHOT
    assert [page.url for page in snapshot.pages if page.terms] == [script.COPYRIGHT_URL]
    assert declared(script.COPYRIGHT_URL).file is None
    assert snapshot.attribution
    assert {statement.source for statement in snapshot.attribution} == {script.COPYRIGHT_URL}
    assert all(statement.where for statement in snapshot.attribution)


@pytest.mark.parametrize("index", range(len(script.ATTRIBUTION)))
def test_each_statement_is_the_notice_as_the_snapshot_records_it(index: int) -> None:
    """Each statement's text stands in ``FETCHED.md`` as recorded from the notice."""
    statement = script.ATTRIBUTION[index]
    assert " ".join(statement.text.split()) in _recorded_attribution()


def test_the_capture_states_the_changes_and_the_disclaimer_the_notice_asks() -> None:
    """The notice's clause on modified reuse asks that a change be stated and that a
    disclaimer of Eurostat's responsibility be included."""
    capture = " ".join(script.SNAPSHOT.capture.split())
    assert "Changes made: each page is converted from HTML to Markdown" in capture
    assert "Eurostat is not responsible for this reproduction" in capture


# --- the wiki's pages ------------------------------------------------------------------

WIKI_PAGES = (
    ("https://wikis.ec.europa.eu/x/-AD9B", "SDMX 2.1 and asynchronous answers"),
    ("https://wikis.ec.europa.eu/x/c4eBBg", "the TSV format"),
)
"""Eurostat's two Confluence pages on the API, which a client reads after EU Login alone."""


def test_the_snapshot_requests_nothing_of_eurostats_wiki() -> None:
    """Every page it requests stands on Eurostat's website and must answer 200, so no
    request goes to ``wikis.ec.europa.eu`` and no row records a redirect to a login."""
    pages = script.SNAPSHOT.pages
    assert {urlsplit(page.url).hostname for page in pages} == {"ec.europa.eu"}
    assert {page.status for page in pages} == {200}


def test_the_capture_names_the_wiki_pages_that_require_eu_login() -> None:
    """How this is captured names each page with its subject, says that EU Login is
    required, so that none is requested, and that the user guide's public pages state the
    subjects (conventions §3)."""
    capture = " ".join(script.SNAPSHOT.capture.split())
    for url, subject in WIKI_PAGES:
        assert f"{url}, on {subject}" in capture
    assert "Both require EU Login, so the snapshot requests neither" in capture
    assert "the public pages of the user guide are its statement of their subjects" in capture


# --- the user-guide pages ----------------------------------------------------------------

GUIDE_PAGE = """<!DOCTYPE html>
<html lang="en"><head><title>API - Getting started</title>
<script>var p_auth = "Xy12ab";</script></head>
<body>
<a class="ecl-skip-link" href="#main-content">Skip to main content</a>
<nav>Eurostat > Help > User guides</nav>
<h1 class="ecl-page-header__title">API - Getting started</h1>
<div id="main-content">
<!-- LAST-MODIFIED-DATE: 1730678400000 -->
<div class="estat-inpage-nav">On this page</div>
<p>The <strong>Statistics API</strong> answers a query on one dataset in <code>JSON-stat</code>
2.0, as the <a href="/eurostat/web/user-guides/data-browser/api-data-access/api-introduction">\
introduction</a> says.</p>
<h2>A query</h2>
<ul><li>one dataset per request</li><li>a filter per dimension, <em>case-insensitive</em></li></ul>
<pre><code class="language-text">\
https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/apro_mk_cola?geo=AT\
</code></pre>
<table><tr><th colspan="2">Parameters</th></tr><tr><td>lang</td><td>EN, FR or DE</td></tr></table>
<p>A query that names no filter asks for every code of every dimension, and Eurostat answers \
it with the whole dataset where it is small enough to be answered at once.</p>
</div>
<footer>Contact Eurostat</footer>
</body></html>
"""
"""A user-guide page's shape: the site's chrome, the title, the main region with a comment
of its last change, a table with merged cells and a code block."""

GUIDE_MARKDOWN = """\
# API - Getting started

The **Statistics API** answers a query on one dataset in `JSON-stat` 2.0, as the \
[introduction](https://ec.europa.eu/eurostat/web/user-guides/data-browser/api-data-access/\
api-introduction) says.

## A query

- one dataset per request
- a filter per dimension, *case-insensitive*

```text
https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/apro_mk_cola?geo=AT
```

<table>
<tr>
<th colspan="2">Parameters</th>
</tr>
<tr>
<td>lang</td>
<td>EN, FR or DE</td>
</tr>
</table>

A query that names no filter asks for every code of every dimension, and Eurostat answers it \
with the whole dataset where it is small enough to be answered at once.
"""

GETTING_STARTED = f"{GUIDE}api-getting-started"


def guide_answer(text: str, content_type: str = "text/html;charset=UTF-8") -> Response:
    """The user-guide page's answer, its body ``text``."""
    return answer(GETTING_STARTED, text.encode("utf-8"), content_type=content_type)


def test_a_user_guide_page_becomes_its_title_and_main_region_in_markdown() -> None:
    """The site's chrome, the in-page navigation and the script with the per-request token
    are dropped; links are absolute, and a table with merged cells stays HTML."""
    page = declared(GETTING_STARTED)
    assert script.reduce(page, guide_answer(GUIDE_PAGE)) == GUIDE_MARKDOWN.encode("utf-8")


def test_a_user_guide_pages_note_names_its_html_tables_and_its_last_change() -> None:
    page = declared(GETTING_STARTED)
    response = guide_answer(GUIDE_PAGE)
    note = script.note(Row(page, response, script.reduce(page, response), page.note))
    assert note == (
        "converted from HTML; the page's HTML carries a per-request token, which the Markdown "
        "drops, so the row records no size or sha256 of its body; 1 table with merged cells "
        "or a nested table kept as HTML; its content items were last modified 2024-11-04 "
        "(UTC)"
    )


@pytest.mark.parametrize(
    ("text", "content_type", "stop"),
    [
        (GUIDE_PAGE.replace('id="main-content"', 'id="content"'), "text/html", "main-content"),
        (GUIDE_PAGE.replace("<h1", "<h2").replace("</h1>", "</h2>"), "text/html", "h1"),
        (GUIDE_PAGE.replace("<p>A query that", "<p hidden>A query that"), None, "text/html"),
        (GUIDE_PAGE.replace("Statistics API", "authToken"), "text/html", "per-request"),
        (
            '<html><body><h1>API</h1><div id="main-content"><p>Moved.</p></div></body></html>',
            "text/html",
            "characters of Markdown",
        ),
    ],
    ids=["no-main-region", "no-title", "not-html", "token", "too-short"],
)
def test_a_user_guide_page_the_converter_does_not_recognise_stops_the_run(
    text: str, content_type: str | None, stop: str
) -> None:
    page = declared(GETTING_STARTED)
    response = answer(GETTING_STARTED, text.encode("utf-8"), content_type=content_type)
    with pytest.raises(SystemExit, match=stop):
        script.reduce(page, response)


def test_the_data_query_pages_statement_of_the_key_order_is_checked() -> None:
    """The recorded page states the key's order; a page without it stops the run."""
    page = f"user-guide/{script.KEY_ORDER_PAGE}.md"
    script.check_key_order((UPSTREAM / page).read_bytes())
    with pytest.raises(SystemExit, match="key parameter defines"):
        script.check_key_order(b"# Data query\n\nThe key is a path segment.\n")


# --- the documents ----------------------------------------------------------------------

WADL = b"""\
<application xmlns="http://wadl.dev.java.net/2009/02">
    <resources base="https://ec.europa.eu/eurostat/api/dissemination/">
        <resource path="statistics/1.0/data/{datasetCode}">
            <method name="GET" id="getData">
                <representation xmlns:ns3="urn:example" element="ns3:dataset"/>
            </method>
        </resource>
        <resource path="statistics/1.0/label/{datasetCode}">
            <method name="GET" id="getLabel"/>
        </resource>
    </resources>
</application>
"""
"""A WADL file's shape, as the snapshot records it: an input of the hooks."""
REORDERED = b"""\
<application xmlns="http://wadl.dev.java.net/2009/02">
    <resources base="https://ec.europa.eu/eurostat/api/dissemination/">
        <resource path="statistics/1.0/label/{datasetCode}">
            <method name="GET" id="getLabel"/>
        </resource>
        <resource path="statistics/1.0/data/{datasetCode}">
            <method name="GET" id="getData">
                <representation xmlns:ns4="urn:example" element="ns4:dataset"/>
            </method>
        </resource>
    </resources>
</application>
"""
"""The same elements in another order, their namespace prefix numbered anew."""
MOVED = WADL.replace(
    b'                <representation xmlns:ns3="urn:example" element="ns3:dataset"/>\n',
    b"",
).replace(
    b'            <method name="GET" id="getLabel"/>\n',
    b'            <method name="GET" id="getLabel">\n'
    b'                <representation xmlns:ns3="urn:example" element="ns3:dataset"/>\n'
    b"            </method>\n",
)
"""A line moved under another parent: a change."""

WADL_PAGE = Page(f"{API}statistics/1.0/statistics-rest.wadl", "api/statistics-rest.wadl")


def test_a_wadl_in_another_order_is_kept_as_recorded() -> None:
    assert script.canonical(WADL_PAGE, REORDERED) == script.canonical(WADL_PAGE, WADL)
    assert script.kept_as_recorded(WADL_PAGE, WADL, REORDERED) == WADL


def test_a_wadl_with_a_line_under_another_parent_is_written_as_fetched() -> None:
    assert script.canonical(WADL_PAGE, MOVED) != script.canonical(WADL_PAGE, WADL)
    assert script.kept_as_recorded(WADL_PAGE, WADL, MOVED) == MOVED
    assert script.kept_as_recorded(WADL_PAGE, None, REORDERED) == REORDERED


def test_reduce_reads_the_recorded_wadl_under_the_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``reduce`` compares an answer with the file the snapshot holds now."""
    (tmp_path / "api").mkdir()
    (tmp_path / "api" / "statistics-rest.wadl").write_bytes(WADL)
    monkeypatch.setattr(script, "OUT", tmp_path)
    assert script.reduce(WADL_PAGE, answer(WADL_PAGE.url, REORDERED)) == WADL
    assert script.reduce(WADL_PAGE, answer(WADL_PAGE.url, MOVED)) == MOVED


def test_a_document_that_is_no_wadl_is_compared_byte_for_byte() -> None:
    page = declared(f"{API}swagger-ui/sdmx-rest.yaml")
    assert script.canonical(page, REORDERED) == REORDERED
    assert script.reduce(page, kept(page)) == (UPSTREAM / "api" / "sdmx-rest.yaml").read_bytes()


def test_each_recorded_wadl_reads_as_itself() -> None:
    """The committed WADL files are kept as recorded, so ``--check`` compares the same."""
    for _, file in PAGES:
        if (file or "").endswith(".wadl"):
            page = declared(next(url for url, name in PAGES if name == file))
            body = kept(page).body
            assert script.kept_as_recorded(page, body, body) == body


def test_an_empty_document_stops_the_run() -> None:
    page = declared(f"{API}1.0/async/async.wadl")
    with pytest.raises(SystemExit, match="empty body"):
        script.reduce(page, answer(page.url, b" \n"))


# --- the samples -----------------------------------------------------------------------


def sample_rows() -> list[Row]:
    """The rows of the data-query page and the four samples, as the snapshot keeps them."""
    files = [f"user-guide/{script.KEY_ORDER_PAGE}.md"]
    files += [file for sample in script.SAMPLES for file in (sample.stat_file, sample.sdmx_file)]
    return [kept_row(declared(next(url for url, name in PAGES if name == f))) for f in files]


def test_the_recorded_samples_line_up_with_their_keys() -> None:
    assert script.sections(sample_rows()) == ()


def test_a_csv_row_outside_the_key_stops_the_run() -> None:
    rows = sample_rows()
    sdmx = next(row for row in rows if row.page.file == "samples/apro_mk_cola-sdmx-csv.csv")
    changed = sdmx.response.body.replace(
        b",A,PRD,D1110D,THS_T,AT,2022,", b",A,PRD,D1110D,T,AT,2022,"
    )
    assert changed != sdmx.response.body
    rows[rows.index(sdmx)] = Row(sdmx.page, answer(sdmx.page.url, changed), changed)
    with pytest.raises(SystemExit, match="outside the key"):
        script.sections(rows)


def test_a_json_stat_sample_in_another_order_than_the_csv_stops_the_run() -> None:
    rows = sample_rows()
    stat = next(row for row in rows if row.page.file == "samples/DS-059358-json-stat.json")
    swapped = stat.response.body.replace(
        b'"id":["freq","reporter","product","indicators","time"]',
        b'"id":["freq","product","reporter","indicators","time"]',
    )
    assert swapped != stat.response.body
    rows[rows.index(stat)] = Row(stat.page, answer(stat.page.url, swapped), swapped)
    with pytest.raises(SystemExit, match="do not line up"):
        script.sections(rows)


def test_a_run_without_a_sample_stops_in_sections() -> None:
    """A check that cannot run must not read as one that passed."""
    with pytest.raises(SystemExit, match="declare them all"):
        script.sections(sample_rows()[:-1])


def test_each_samples_note_names_its_dimensions_or_its_columns() -> None:
    notes = {row.page.file: script.note(row) for row in sample_rows()[1:]}
    assert notes["samples/apro_mk_cola-json-stat.json"] == (
        "a JSON-stat 2.0 dataset (specification: https://json-stat.org/format/, cited, not "
        "snapshotted) with the dimensions `freq`, `milkitem`, `dairyprod`, `unit`, `geo`, "
        "`time`; the Statistics API's answer"
    )
    assert notes["samples/DS-059358-sdmx-csv.csv"] == (
        "SDMX-CSV with the columns `DATAFLOW`, `LAST UPDATE`, `freq`, `reporter`, `product`, "
        "`indicators`, `TIME_PERIOD`, `OBS_VALUE`; the key `A.AT.10411200.` follows the "
        "dimension order freq.reporter.product.indicators, as the CSV header and the "
        "JSON-stat sample's `id` list it, and "
        '`user-guide/api-detailed-guidelines/sdmx2-1/data-query.md` states "The key '
        'parameter defines values of the dimensions in the order of structure."; the SDMX 2.1 '
        "API's answer on the Comext base"
    )
