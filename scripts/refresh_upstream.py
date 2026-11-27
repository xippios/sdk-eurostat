"""Refresh the upstream documentation snapshot in ``docs/upstream/`` (``/refresh-upstream``).

Eurostat documents its dissemination API in the user guide "Data access via API"
(https://ec.europa.eu/eurostat/web/user-guides/data-browser/api-data-access/), a set of
server-rendered pages, and describes the services in WADL files and one OpenAPI document
served beside them. The script declares its snapshot, ``SNAPSHOT``, to core's frame,
``xippios.core.refresh``, which fetches every page, checks the attribution, writes the files
and ``FETCHED.md`` and compares with ``--check`` (sdk-core ADR-0062; conventions §3). The
snapshot keeps:

- ``user-guide/<page path>.md``: each user-guide page in ``GUIDE_PAGES``, converted to
  Markdown with the standard library's ``html.parser``: the page title (its ``h1``) and
  the page's main region, headings, paragraphs, lists, tables, code and links, without
  the site's header, footer, in-page navigation, scripts and styles. A table with merged
  cells or a nested table stays HTML (conventions §3); links and images are absolute.
- ``api/<file>``: the WADL files and the OpenAPI document in ``DOCUMENTS``, verbatim; those
  of the second base, ``COMEXT_BASE``, which serves the ``DS-`` datasets of Comext and
  Prodcom, under ``api/comext/``.
- ``samples/<file>``: small answers, verbatim, two for each dataset in ``SAMPLES``, one
  dataset of each base: the Statistics API's JSON-stat answer and the SDMX 2.1 API's
  SDMX-CSV answer, structural samples of the formats (test fixtures are recorded
  separately, never here);

and records Eurostat's copyright notice, the page that states the terms the attribution
quotes, as a row without a file. It requests nothing of Eurostat's wiki: the two Confluence
pages of ``WIKI_PAGES`` require EU Login, and ``CAPTURE`` names them with their subjects.

Every request goes through ``CLIENT``, a client of Eurostat's website on core's
``AsyncClient`` that sends no credential, one request at a time, ``PAUSE`` seconds apart.
After a 429 its retry policy gives the frame's one retry the wait the website names in
``X-Rate-Limit-Retry-After-Seconds`` or ``Retry-After``, ``QUOTA_PAUSE`` where it names
none, and stops the run where it asks for more than ``MAX_QUOTA_WAIT``; ``observe`` logs
the request budget the website reports in ``X-Rate-Limit-Remaining``.

The script's own code is its hooks. ``reduce`` converts a user-guide page to Markdown and
keeps a WADL file as recorded where the service sent the same elements in another order,
which ``canonical`` reads in a form with the order fixed. ``note`` checks each page the
script recognises and writes its row's note. ``sections`` checks the samples against each
other and against the data-query page's statement of the key's order, with every row read,
and writes no section of its own. A page that changed in a way the script does not know
stops the run before anything is written. The frame stops, too, on a copyright, a licence
or terms of use that ``ATTRIBUTION`` does not record, read in the whole visible text of each
page, the site's header and footer included, but not in the samples or in the copyright
notice, which is the terms and must print each statement recorded from it. No key exists
or is read. Run from the repository root::

    uv run scripts/refresh_upstream.py              # fetch, then write the snapshot
    uv run scripts/refresh_upstream.py --check      # fetch and compare; write nothing

``--check`` exits 1 when a file differs from what upstream serves now, a WADL file compared
in the form with its order fixed, or when ``FETCHED.md`` would change in more than its rows'
measures.
"""

import csv
import html
import io
import re
import textwrap
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import httpx
from xippios.core import AsyncClient, ClientConfig, RateLimitError, RetryPolicy, parse_retry_after
from xippios.core.refresh import (
    NotFetched,
    Page,
    Response,
    Row,
    Section,
    Snapshot,
    Statement,
    changed,
    decode,
    parse_json,
    run,
)

from xippios.eurostat._client import SOURCE
from xippios.eurostat._version import __version__

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "upstream"
"""The snapshot's directory, where ``reduce`` reads a WADL file as recorded."""

GUIDE_BASE = "https://ec.europa.eu/eurostat/web/user-guides/data-browser/api-data-access/"
GUIDE_PAGES = (
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
"""User-guide pages, relative to ``GUIDE_BASE``; each is written to ``user-guide/<path>.md``."""

API_BASE = "https://ec.europa.eu/eurostat/api/dissemination/"
COMEXT_BASE = "https://ec.europa.eu/eurostat/api/comext/dissemination/"
"""The second base, for the ``DS-`` datasets of Comext and Prodcom (``prefixed-datasets``)."""
DOCUMENTS = (
    (
        "api/statistics-rest.wadl",
        f"{API_BASE}statistics/1.0/statistics-rest.wadl",
        "WADL of the Statistics API",
    ),
    ("api/sdmx-rest.wadl", f"{API_BASE}sdmx/2.1/sdmx-rest.wadl", "WADL of the SDMX 2.1 API"),
    ("api/catalogue.wadl", f"{API_BASE}catalogue/catalogue.wadl", "WADL of the Catalogue API"),
    ("api/async.wadl", f"{API_BASE}1.0/async/async.wadl", "WADL of the asynchronous API"),
    (
        "api/sdmx-rest.yaml",
        f"{API_BASE}swagger-ui/sdmx-rest.yaml",
        'OpenAPI 3.0 document "Eurostat SDMX RESTful API", the user guide\'s consolidated '
        "Open API specification: SDMX 2.1 and 3.0, asynchronous and catalogue paths; served "
        "under `swagger-ui/`, stored without `swagger` in its path, which detect-secrets' "
        "`is_swagger_file` filter would skip",
    ),
    (
        "api/comext/statistics-rest.wadl",
        f"{COMEXT_BASE}statistics/1.0/statistics-rest.wadl",
        "WADL of the Statistics API on the Comext base",
    ),
    (
        "api/comext/sdmx-rest.wadl",
        f"{COMEXT_BASE}sdmx/2.1/sdmx-rest.wadl",
        "WADL of the SDMX 2.1 API on the Comext base",
    ),
    (
        "api/comext/sdmx-rest-3.0.wadl",
        f"{COMEXT_BASE}sdmx/3.0/sdmx-rest.wadl",
        "WADL of the SDMX 3.0 API on the Comext base, kept as one of the base's five; SDMX "
        "3.0 itself is not wrapped",
    ),
    (
        "api/comext/catalogue.wadl",
        f"{COMEXT_BASE}catalogue/catalogue.wadl",
        "WADL of the Catalogue API on the Comext base",
    ),
    (
        "api/comext/async.wadl",
        f"{COMEXT_BASE}1.0/async/async.wadl",
        "WADL of the asynchronous API on the Comext base",
    ),
)
"""Upstream documents kept verbatim: snapshot path, URL, note."""


@dataclass(frozen=True)
class Sample:
    """One dataset the snapshot samples twice, once from each API, for 2022 and 2023.

    Attributes:
        base: The dataset's base URL, ``API_BASE`` or ``COMEXT_BASE``.
        dataset: The dataset's code.
        filters: The JSON-stat query's filters.
        key: The SDMX 2.1 data query's series key.
    """

    base: str
    dataset: str
    filters: str
    key: str

    @property
    def stat_url(self) -> str:
        """The Statistics API's JSON-stat query."""
        return f"{self.base}statistics/1.0/data/{self.dataset}?format=JSON&lang=EN&{self.filters}"

    @property
    def sdmx_url(self) -> str:
        """The SDMX 2.1 API's SDMX-CSV query."""
        return (
            f"{self.base}sdmx/2.1/data/{self.dataset}/{self.key}"
            "?format=SDMX-CSV&startPeriod=2022&endPeriod=2023"
        )

    @property
    def stat_file(self) -> str:
        """The JSON-stat sample's file under ``docs/upstream/``."""
        return f"samples/{self.dataset}-json-stat.json"

    @property
    def sdmx_file(self) -> str:
        """The SDMX-CSV sample's file under ``docs/upstream/``."""
        return f"samples/{self.dataset}-sdmx-csv.csv"

    @property
    def where(self) -> str:
        """The clause that names the Comext base, empty for the main base."""
        return "" if self.base == API_BASE else " on the Comext base"


SAMPLES = (
    Sample(API_BASE, "apro_mk_cola", "geo=AT&time=2022&time=2023", "A...THS_T.AT"),
    Sample(
        COMEXT_BASE,
        "DS-059358",
        "reporter=AT&product=10411200&sinceTimePeriod=2022&untilTimePeriod=2023",
        "A.AT.10411200.",
    ),
)
"""The sampled datasets: ``apro_mk_cola`` of the main base, ``DS-059358`` (Prodcom: sold
production, exports and imports) of the Comext base."""
_SAMPLE_FILES = {
    file: sample for sample in SAMPLES for file in (sample.stat_file, sample.sdmx_file)
}
KEY_ORDER_PAGE = "api-detailed-guidelines/sdmx2-1/data-query"
KEY_ORDER_SENTENCE = "The key parameter defines values of the dimensions in the order of structure."
"""The data-query page's statement of the key's positions, checked to be there."""
JSON_STAT_SPEC = "https://json-stat.org/format/"

WIKI_PAGES = (
    ("https://wikis.ec.europa.eu/x/-AD9B", "SDMX 2.1 and asynchronous answers"),
    ("https://wikis.ec.europa.eu/x/c4eBBg", "the TSV format"),
)
"""Eurostat's Confluence pages on these subjects, which require EU Login: ``CAPTURE`` names
them, and the snapshot never requests them."""

NOT_REQUESTED = (
    (
        "https://ec.europa.eu/eurostat/web/international-trade-in-goods/database#comext",
        "the Comext database's page on Eurostat's website, linked from the Comext page; not "
        "API documentation",
    ),
    (
        "https://ec.europa.eu/eurostat/web/prodcom/overview",
        "the PRODCOM statistics' overview page, linked from the Comext page; not API documentation",
    ),
    (
        f"{COMEXT_BASE}sdmx/2.1/dataflow/ESTAT/all",
        "the Comext base's list of its dataflows, linked from the Comext page; an API answer, "
        "not documentation",
    ),
    (
        "http://ec.europa.eu/eurostat/estat-navtree-portlet-prod/BulkDownloadListing"
        "?sort=1&dir=comext",
        "the Comext domain's bulk download listing (CSV files with their metadata), linked "
        "from the Comext page; files outside the API",
    ),
    (
        f"{GUIDE_BASE}api-detailed-guidelines/sdmx3-0",
        "SDMX 3.0 is not wrapped (https://github.com/xippios/sdk-eurostat/pull/11); the "
        "Comext base's SDMX 3.0 WADL is kept as one of its five",
    ),
    (
        f"{GUIDE_BASE}api-detailed-guidelines/sdmx3-0/data-query",
        "SDMX 3.0 is not wrapped (https://github.com/xippios/sdk-eurostat/pull/11); the "
        "Comext base's SDMX 3.0 WADL is kept as one of its five",
    ),
    (
        f"{GUIDE_BASE}api-detailed-guidelines/sdmx3-0/structure-queries",
        "SDMX 3.0 is not wrapped (https://github.com/xippios/sdk-eurostat/pull/11); the "
        "Comext base's SDMX 3.0 WADL is kept as one of its five",
    ),
    (
        f"{API_BASE}sdmx/3.0/sdmx-rest.wadl",
        "SDMX 3.0 is not wrapped (https://github.com/xippios/sdk-eurostat/pull/11); the "
        "Comext base's SDMX 3.0 WADL is kept as one of its five",
    ),
    (f"{GUIDE_BASE}api-detailed-guidelines/catalogue-api/rss", "the RSS feed is not used here"),
    (
        f"{GUIDE_BASE}api-detailed-guidelines/catalogue-api/metabase",
        "the metabase file is not used here",
    ),
    (f"{GUIDE_BASE}api-faq/examples", "a FAQ child page outside this snapshot's list"),
    (f"{GUIDE_BASE}api-faq/excel-power-query", "a FAQ child page outside this snapshot's list"),
    (JSON_STAT_SPEC, "JSON-stat 2.0 is a third-party specification: cited, not snapshotted"),
)
"""Pages and other resources linked from the user guide (an API answer, a bulk listing, a
specification among them) that are deliberately not requested, with the reason."""

COPYRIGHT_URL = "https://ec.europa.eu/eurostat/web/main/help/copyright-notice"
"""Eurostat's copyright notice: the terms of the website's content, read for ``ATTRIBUTION``
and kept as no file."""
NAVIGATION_NOTICE_URL = "https://ec.europa.eu/eurostat/en/help/copyright-notice"
"""The address at which the site's navigation links the copyright notice, which the snapshot
reads at ``COPYRIGHT_URL``: the link's target in ``ATTRIBUTION``, never requested."""

PAUSE = 5.0
"""Seconds before every request; requests never run in parallel. The website reports a
small request budget in ``X-Rate-Limit-Remaining`` that a series of requests a few seconds
apart drains (429 "Quota Exhausted"); five seconds apart, a run seldom meets a 429, and the
one retry covers it."""
RETRY_PAUSE = 10.0
"""The shortest wait before the one retry, the frame's own ``RETRY_PAUSE`` too."""
QUOTA_PAUSE = 60.0
"""Seconds before the one retry after a 429 that names no wait of its own."""
MAX_QUOTA_WAIT = 900.0
"""The longest wait for a 429 the script accepts; a longer one stops the run."""
QUOTA_WAIT_HEADERS = ("X-Rate-Limit-Retry-After-Seconds", "Retry-After")
"""The headers of a 429 that name the wait, the website's own first."""
REMAINING_HEADER = "X-Rate-Limit-Remaining"
"""The header in which the website reports the requests left in its budget."""
MIN_PAGE_CHARS = 400
"""A converted page shorter than this has lost its content; the run stops."""
TOKEN_MARKERS = ("p_auth", "authToken")
"""Per-request values of the site's HTML that must never reach a snapshot file."""


def _log(message: str) -> None:
    print(message, flush=True)  # noqa: T201


# --- the website's client ---------------------------------------------------------------


def quota_wait(headers: Mapping[str, str]) -> float:
    """The wait a 429 names, in seconds: ``QUOTA_PAUSE`` where it names none.

    ``X-Rate-Limit-Retry-After-Seconds``, the website's own header, is read first, then
    ``Retry-After``, in seconds or as an HTTP date. The frame waits no less than
    ``RETRY_PAUSE`` before its one retry, and the client's retry policy gives no retry for a
    wait past ``MAX_QUOTA_WAIT``, which stops the run (sdk-core ADR-0062, decision 4).
    """
    for name in QUOTA_WAIT_HEADERS:
        value = headers.get(name)
        if value is None:
            continue
        if name == "Retry-After":
            wait = parse_retry_after(value)
        else:
            wait = float(value.strip()) if value.strip().isdigit() else None
        if wait is not None:
            return wait
    return QUOTA_PAUSE


def classify(response: httpx.Response) -> RateLimitError | None:
    """A 429 as the ``RateLimitError`` whose ``retry_after`` the frame waits; else nothing.

    The frame asks the client's ``classify`` for the wait of a 429 alone, and gives no retry
    for any other error it names (sdk-core ADR-0062, decision 4), so every other answer is
    the frame's to judge.
    """
    if response.status_code != 429:
        return None
    remaining = response.headers.get(REMAINING_HEADER)
    budget = f", {REMAINING_HEADER} {remaining}" if remaining is not None else ""
    return RateLimitError(
        f"HTTP 429 {response.reason_phrase}{budget}",
        retry_after=quota_wait(response.headers),
        source=SOURCE,
    )


def observe(response: httpx.Response) -> None:
    """Log the request budget the website reports, where it reports one."""
    remaining = response.headers.get(REMAINING_HEADER)
    if remaining is not None:
        _log(f"  {response.request.url}: {REMAINING_HEADER} {remaining}")


CLIENT = AsyncClient(
    ClientConfig(
        source=SOURCE,
        version=__version__,
        base_url="https://ec.europa.eu",
        retry=RetryPolicy(
            max_attempts=2, backoff_base=RETRY_PAUSE, backoff_max=MAX_QUOTA_WAIT, jitter=False
        ),
        classify=classify,
        observe=observe,
    )
)
"""The client of Eurostat's website that every request of the snapshot goes through: no
credential, no cache, and the frame's pause for its pace. Its retry policy gives the one
retry after a 429 the wait ``quota_wait`` reads, at least ``RETRY_PAUSE`` and at most
``MAX_QUOTA_WAIT``, and it names itself ``xippios-eurostat/<version>`` as the package's
client does."""


# --- HTML to Markdown -------------------------------------------------------------------


_VOID = frozenset(
    (
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    )
)
_DROP = frozenset(
    (
        "head",
        "script",
        "style",
        "noscript",
        "svg",
        "template",
        "form",
        "input",
        "select",
        "textarea",
        "iframe",
        "link",
        "meta",
    )
)
_DROP_CLASSES = frozenset(
    (
        "lfr-layout-structure-item-nav-inpage",
        "estat-inpage-nav",
        "ecl-skip-link",
        "portlet-header",
        "estat-expand-all",
        "ecl-u-d-none",
    )
)
"""Site chrome inside the main region: in-page navigation, skip links, the portlets'
internal titles (hidden on the page), the "Expand all" button and hidden labels."""
_BLOCK = frozenset(
    (
        "address",
        "article",
        "aside",
        "blockquote",
        "details",
        "dialog",
        "div",
        "dl",
        "dt",
        "dd",
        "fieldset",
        "figcaption",
        "figure",
        "footer",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "hr",
        "li",
        "main",
        "nav",
        "ol",
        "p",
        "pre",
        "section",
        "summary",
        "table",
        "ul",
    )
)
_AUTO_CLOSE = frozenset(("p", "li", "tr", "td", "th", "dt", "dd"))
_TABLE_PARTS = frozenset(("thead", "tbody", "tfoot"))
_HEADING = re.compile(r"h[1-6]")
_SPACE = re.compile(r"[ \t\n\r\f]+")
_MODIFIED = re.compile(r"LAST-MODIFIED-DATE:\s*(\d{10,13})")
_TAG_LIKE = re.compile(r"<(?=[A-Za-z/!?])")
_INLINE_ESCAPE = re.compile(r"([\\*`])")
_CODE_OPEN, _CODE_CLOSE = "\x01", "\x02"
"""Code spans are marked while a line is built, so that adjacent ones merge into one."""
_CODE_SPAN = re.compile(f"{_CODE_OPEN}(.*?){_CODE_CLOSE}", re.DOTALL)
_BREAK = "\x00"
_LOCAL_PREFIX = re.compile(rb"xmlns:([A-Za-z_][\w.-]*)=")


@dataclass
class Element:
    """An HTML element with its attributes and children (text, elements and comments)."""

    tag: str
    attrs: dict[str, str]
    children: list["Element | str"] = field(default_factory=list)

    @property
    def classes(self) -> frozenset[str]:
        """The element's class names."""
        return frozenset(self.attrs.get("class", "").split())

    def find(self, predicate: Any) -> "Element | None":
        """The first descendant, in document order, for which ``predicate`` is true."""
        for child in self.children:
            if isinstance(child, Element):
                if predicate(child):
                    return child
                found = child.find(predicate)
                if found is not None:
                    return found
        return None

    def comments(self) -> list[str]:
        """The text of every comment below this element."""
        found: list[str] = []
        for child in self.children:
            if isinstance(child, Element):
                if child.tag == "#comment":
                    found.append(child.attrs["text"])
                else:
                    found += child.comments()
        return found


class _TreeBuilder(HTMLParser):
    """Build an ``Element`` tree; tolerant of the unclosed tags HTML allows."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Element("#root", {})
        self.stack = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Open an element; a ``p``, ``li`` or table cell closes an open one of its kind."""
        if tag in _AUTO_CLOSE and self.stack[-1].tag == tag:
            self.stack.pop()
        element = Element(tag, {name: value or "" for name, value in attrs})
        self.stack[-1].children.append(element)
        if tag not in _VOID:
            self.stack.append(element)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """A self-closed element opens nothing."""
        self.stack[-1].children.append(Element(tag, {name: value or "" for name, value in attrs}))

    def handle_endtag(self, tag: str) -> None:
        """Close the innermost open element of this name; ignore a stray end tag."""
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                return

    def handle_data(self, data: str) -> None:
        """Keep text as it stands; whitespace is collapsed when rendering."""
        self.stack[-1].children.append(data)

    def handle_comment(self, data: str) -> None:
        """Keep comments apart from text; the renderer skips them."""
        self.stack[-1].children.append(Element("#comment", {"text": data}))


def parse_html(text: str) -> Element:
    """Parse a whole HTML document into an ``Element`` tree."""
    builder = _TreeBuilder()
    builder.feed(text)
    builder.close()
    return builder.root


def _dropped(element: Element) -> bool:
    if element.tag in _DROP or element.tag == "#comment":
        return True
    if element.classes & _DROP_CLASSES:
        return True
    if element.tag == "button" and "ecl-accordion__toggle" not in element.classes:
        return True
    if element.tag == "img":
        src = element.attrs.get("src", "")
        return src.startswith("data:") or element.attrs.get("role") == "presentation"
    return False


def _code_span(match: re.Match[str]) -> str:
    code = " ".join(match.group(1).split())
    if not code:
        return ""
    if "`" in code:
        return f"`` {code} ``"
    return f"`{code}`"


def _squash(text: str) -> str:
    """Collapse spaces, trim each line, drop empty ones at both ends; resolve code spans."""
    text = text.replace(_CODE_CLOSE + _CODE_OPEN, "").replace("\u200b", "")
    text = _CODE_SPAN.sub(_code_span, text)
    lines = [" ".join(line.replace("\xa0", " ").split()) for line in text.split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip("\n")


def _plain(block: str) -> str:
    """A Markdown block without emphasis and code markers."""
    return re.sub(r"[*`]", "", block)


def _escape(text: str) -> str:
    return _TAG_LIKE.sub(r"\\<", _INLINE_ESCAPE.sub(r"\\\1", text))


def _fence(code: str, language: str) -> str:
    fence = "~~~~" if "```" in code else "```"
    return f"{fence}{language}\n{code}\n{fence}"


def _language(element: Element) -> str:
    for name in sorted(element.classes):
        if name.startswith("language-"):
            return name.removeprefix("language-")
    return ""


def _raw_text(element: Element, br: str = "\n") -> str:
    """The element's text with whitespace as written; ``br`` becomes ``br``."""
    parts: list[str] = []
    for child in element.children:
        if isinstance(child, str):
            parts.append(child)
        elif child.tag == "br":
            parts.append(br)
        elif child.tag not in _DROP and child.tag != "#comment":
            parts.append(_raw_text(child, br))
    return "".join(parts)


@dataclass
class Converted:
    """A converted page: its title, Markdown blocks and what the conversion found."""

    title: str
    blocks: list[str]
    html_tables: int
    modified: list[int]

    @property
    def markdown(self) -> str:
        """The whole Markdown file."""
        return "\n\n".join([f"# {self.title}", *self.blocks]) + "\n"


class _Markdown:
    """Render an ``Element`` subtree as Markdown blocks."""

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url
        self.html_tables = 0
        self.depth = {"**": 0, "*": 0}
        """Open emphasis by marker: emphasis inside the same emphasis adds no markers."""
        self.in_link = False
        """A link inside a link is rendered as its text."""

    def url(self, value: str) -> str:
        """An absolute URL for ``href`` or ``src``."""
        return urljoin(self.base_url, value.strip())

    # Blocks

    def blocks(self, element: Element) -> list[str]:
        """The element's children as Markdown blocks; inline runs become paragraphs."""
        out: list[str] = []
        run: list[str] = []

        def flush() -> None:
            text = _squash("".join(run))
            if text:
                out.append(text)
            run.clear()

        for child in element.children:
            if isinstance(child, str):
                run.append(self.text(child))
            elif _dropped(child):
                continue
            elif child.tag in _BLOCK or "code-snippet-fragment" in child.classes:
                flush()
                out += self.block(child)
            else:
                run.append(self.inline(child))
        flush()
        return out

    def block(self, element: Element) -> list[str]:
        """One block-level element as Markdown blocks."""
        tag = element.tag
        if "code-snippet-fragment" in element.classes:
            return self.snippet(element)
        if _HEADING.fullmatch(tag):
            self.depth["**"] += 1
            try:
                text = _squash(self.inline_children(element)).replace("\n", " ")
            finally:
                self.depth["**"] -= 1
            return [f"{'#' * int(tag[1])} {text}"] if text else []
        if tag in ("ul", "ol"):
            text = self.listing(element)
            return [text] if text else []
        if tag == "pre":
            code = _raw_text(element).replace("\xa0", " ").strip("\n")
            code_element = element.find(lambda e: e.tag == "code")
            language = _language(element) or (_language(code_element) if code_element else "")
            return [_fence(code, language)] if code.strip() else []
        if tag == "table":
            return [self.table(element)]
        if tag == "hr":
            return ["---"]
        if tag == "blockquote":
            inner = "\n\n".join(self.blocks(element))
            return ["\n".join(f"> {line}".rstrip() for line in inner.split("\n"))] if inner else []
        return self.blocks(element)

    def snippet(self, element: Element) -> list[str]:
        """A Liferay code-snippet fragment: its text, ``br`` as line breaks, fenced."""
        body = element.find(lambda e: e.tag == "div")
        script = element.find(lambda e: e.tag == "script")
        if body is None:
            return []
        # The page shows the fragment's textContent, whose lines are the source's line
        # breaks; a ``br`` that no line break follows still ends a line here.
        text = _raw_text(body, _BREAK).replace(_BREAK + "\r\n", "\n")
        text = text.replace(_BREAK + "\n", "\n").replace(_BREAK, "\n")
        lines = [line.replace("\xa0", " ").rstrip() for line in text.split("\n")]
        code = "\n".join(lines).strip("\n")
        return [_fence(code, _language(script) if script else "")] if code.strip() else []

    def listing(self, element: Element) -> str:
        """A ``ul`` or ``ol``, nested lists indented under their item."""
        ordered = element.tag == "ol"
        number = int(element.attrs.get("start", "1") or "1")
        items: list[str] = []
        loose = False
        for child in element.children:
            if not isinstance(child, Element) or _dropped(child):
                continue
            if child.tag in ("ul", "ol") and items:
                nested = self.listing(child)
                if nested:
                    items[-1] += "\n" + textwrap.indent(nested, "  ")
                continue
            if child.tag != "li":
                continue
            marker = f"{number}." if ordered else "-"
            number += 1
            parts = self.blocks(child)
            body = ""
            for part in parts:
                if not body:
                    body = part
                elif part.startswith(("- ", "1. ")) or re.match(r"\d+\. ", part):
                    body += "\n" + part
                else:
                    body += "\n\n" + part
                    loose = True
            pad = " " * (len(marker) + 1)
            lines = body.split("\n")
            first = f"{marker} {lines[0]}".rstrip()
            items.append("\n".join([first, *(pad + line if line else "" for line in lines[1:])]))
        return ("\n\n" if loose else "\n").join(items)

    # Tables

    @staticmethod
    def rows(table: Element) -> list[Element]:
        """The table's own rows, in order, without those of a nested table."""
        found: list[Element] = []
        for child in table.children:
            if isinstance(child, Element):
                if child.tag == "tr":
                    found.append(child)
                elif child.tag in _TABLE_PARTS:
                    found += [
                        row
                        for row in child.children
                        if isinstance(row, Element) and row.tag == "tr"
                    ]
        return found

    @staticmethod
    def cells(row: Element) -> list[Element]:
        """The row's ``th`` and ``td`` cells."""
        return [
            cell for cell in row.children if isinstance(cell, Element) and cell.tag in ("th", "td")
        ]

    def table(self, table: Element) -> str:
        """A pipe table, or the table as HTML where cells merge or a table nests in it."""
        rows = self.rows(table)
        merged = any(
            cell.attrs.get(span, "1").strip() not in ("", "1")
            for row in rows
            for cell in self.cells(row)
            for span in ("rowspan", "colspan")
        )
        nested = any(
            cell.find(lambda e: e.tag == "table") is not None
            for row in rows
            for cell in self.cells(row)
        )
        if merged or nested:
            self.html_tables += 1
            return self.html_table(table)
        grid = [[self.cell(cell) for cell in self.cells(row)] for row in rows]
        grid = [row for row in grid if row]
        if not grid:
            return ""
        width = max(len(row) for row in grid)
        grid = [row + [""] * (width - len(row)) for row in grid]
        return "\n".join(
            "|" + "|".join(f" {cell} " if cell else " " for cell in row) + "|"
            for row in (grid[0], ["---"] * width, *grid[1:])
        )

    def cell(self, cell: Element) -> str:
        """One cell's content on one line: blocks and line breaks joined by ``<br>``."""
        text = "<br>".join(block.replace("\n", "<br>") for block in self.blocks(cell))
        return text.replace("|", r"\|")

    def html_table(self, table: Element) -> str:
        """The table as plain HTML: structure, spans, links, images and emphasis only."""
        lines: list[str] = ["<table>"]
        for child in table.children:
            if not isinstance(child, Element):
                continue
            if child.tag == "caption":
                lines.append(f"<caption>{self.html_inline(child)}</caption>")
            elif child.tag in _TABLE_PARTS:
                lines.append(f"<{child.tag}>")
                for row in child.children:
                    if isinstance(row, Element) and row.tag == "tr":
                        lines += self.html_row(row)
                lines.append(f"</{child.tag}>")
            elif child.tag == "tr":
                lines += self.html_row(child)
        lines.append("</table>")
        return "\n".join(lines)

    def html_row(self, row: Element) -> list[str]:
        """One ``tr`` and its cells, a cell per line."""
        lines = ["<tr>"]
        for cell in self.cells(row):
            spans = "".join(
                f' {span}="{html.escape(cell.attrs[span].strip())}"'
                for span in ("rowspan", "colspan")
                if cell.attrs.get(span, "1").strip() not in ("", "1")
            )
            lines.append(f"<{cell.tag}{spans}>{self.html_inline(cell)}</{cell.tag}>")
        lines.append("</tr>")
        return lines

    def html_inline(self, element: Element) -> str:
        """A cell's content as HTML on one line; paragraphs and divs become ``<br>``."""
        parts: list[str] = []
        for child in element.children:
            if isinstance(child, str):
                parts.append(html.escape(_SPACE.sub(" ", child.replace("\xa0", " ")), quote=False))
            elif _dropped(child):
                continue
            elif child.tag == "table":
                parts.append(self.html_table(child).replace("\n", ""))
            elif child.tag == "br":
                parts.append("<br>")
            elif child.tag == "a" and child.attrs.get("href", "").strip()[:1] not in ("", "#"):
                href = html.escape(self.url(child.attrs["href"]))
                parts.append(f'<a href="{href}">{self.html_inline(child).strip()}</a>')
            elif child.tag == "img":
                src = html.escape(self.url(child.attrs.get("src", "")))
                alt = html.escape(child.attrs.get("alt", "").strip())
                parts.append(f'<img src="{src}" alt="{alt}">')
            elif child.tag in ("strong", "b", "em", "i", "code", "sup", "sub"):
                inner = self.html_inline(child)
                tag = {"b": "strong", "i": "em"}.get(child.tag, child.tag)
                parts.append(f"<{tag}>{inner.strip()}</{tag}>" if inner.strip() else inner)
            elif child.tag in ("ul", "ol"):
                items = [
                    f"<li>{self.html_inline(item).strip()}</li>"
                    for item in child.children
                    if isinstance(item, Element) and item.tag == "li"
                ]
                parts.append(f"<{child.tag}>{''.join(items)}</{child.tag}>")
            elif child.tag in _BLOCK:
                inner = self.html_inline(child).strip()
                if inner:
                    parts.append(f"<br>{inner}<br>")
            else:
                parts.append(self.html_inline(child))
        text = " ".join("".join(parts).split())
        text = re.sub(r"(\s*<br>\s*)+", "<br>", text)
        return re.sub(r"^<br>|<br>$", "", text.strip()).strip()

    # Inline

    @staticmethod
    def text(value: str) -> str:
        """A text node: whitespace collapsed (``nbsp`` kept until the line is squashed)."""
        return _escape(_SPACE.sub(" ", value))

    def inline_children(self, element: Element) -> str:
        """The children of ``element`` as inline Markdown."""
        parts: list[str] = []
        for child in element.children:
            if isinstance(child, str):
                parts.append(self.text(child))
            elif not _dropped(child):
                parts.append(self.inline(child))
        return "".join(parts)

    def inline(self, element: Element) -> str:
        """One inline element as Markdown."""
        tag = element.tag
        if tag == "br":
            return "\n"
        if tag == "img":
            src = element.attrs.get("src", "").strip()
            if not src:
                return ""
            alt = element.attrs.get("alt", "").strip().replace("]", r"\]")
            return f"![{alt}]({self.url(src)})"
        if tag in ("code", "kbd", "samp", "tt"):
            code = " ".join(_raw_text(element).replace("\xa0", " ").split())
            return f"{_CODE_OPEN}{code}{_CODE_CLOSE}" if code else ""
        marker = {"strong": "**", "b": "**", "em": "*", "i": "*"}.get(tag)
        if marker is not None:
            self.depth[marker] += 1
            try:
                inner = self.inline_children(element)
            finally:
                self.depth[marker] -= 1
            return inner if self.depth[marker] else self.wrap(inner, marker)
        if tag == "a":
            href = element.attrs.get("href", "").strip()
            if self.in_link or not href or href.startswith(("#", "javascript:")):
                return self.inline_children(element)
            self.in_link = True
            try:
                inner = self.inline_children(element)
            finally:
                self.in_link = False
            label = _squash(inner).replace("\n", " ")
            if not label:
                return inner
            target = self.url(href)
            if label == target:
                return f"<{target}>"
            if any(char in target for char in " ()<>"):
                target = f"<{target}>"
            return f"[{label}]({target})"
        inner = self.inline_children(element)
        return f"\n{inner}\n" if tag in _BLOCK else inner

    @staticmethod
    def wrap(inner: str, marker: str) -> str:
        """Emphasis around the text, with its outer whitespace moved outside the markers."""
        core = inner.strip(" \xa0\n")
        if not core:
            return " " if inner else ""
        lead = " " if inner[:1] in (" ", "\xa0", "\n") else ""
        trail = " " if inner[-1:] in (" ", "\xa0", "\n") else ""
        return f"{lead}{marker}{core}{marker}{trail}"


def _main_region(root: Element, url: str) -> Element:
    main = root.find(lambda e: e.attrs.get("id") == "main-content")
    if main is None:
        raise changed(url, "there is no element with id main-content")
    return main


def convert(text: str, url: str) -> Converted:
    """Convert one user-guide page: its ``h1`` as the title, its main region as the body."""
    root = parse_html(text)
    heading = root.find(lambda e: e.tag == "h1")
    title = _squash(_Markdown(url).inline_children(heading)).replace("\n", " ") if heading else ""
    if not title:
        raise changed(url, "there is no h1 title")
    main = _main_region(root, url)
    renderer = _Markdown(url)
    blocks = [block for block in renderer.blocks(main) if block.strip()]
    modified = sorted(
        {int(match[:10]) for comment in main.comments() for match in _MODIFIED.findall(comment)}
    )
    page = Converted(title, blocks, renderer.html_tables, modified)
    markdown = page.markdown
    leaked = [marker for marker in TOKEN_MARKERS if marker in markdown]
    if leaked:
        raise changed(url, f"the Markdown holds the per-request values {leaked}")
    if len(markdown) < MIN_PAGE_CHARS:
        raise changed(
            url,
            f"only {len(markdown)} characters of Markdown, so the page's layout may have changed",
        )
    return page


def guide_markdown(page: Page, response: Response) -> Converted:
    """A user-guide page converted, once its answer is HTML."""
    media = (response.content_type or "").split(";", 1)[0].strip().lower()
    if media != "text/html":
        raise changed(page.url, f"it answers {media or 'no content type'}, not text/html")
    return convert(decode(response), page.url)


# --- a WADL file in another order -------------------------------------------------------


def _masked(line: bytes) -> bytes:
    """The line with the namespace prefixes it declares for itself masked.

    The service names such a prefix ``ns3``, ``ns4`` and on in document order, so a
    reordering renumbers it without changing what the line says.
    """
    for prefix in set(_LOCAL_PREFIX.findall(line)):
        line = re.sub(rb"\b" + re.escape(prefix) + rb"\b", b"ns*", line)
    return line


def _placed_lines(text: bytes) -> Counter[tuple[tuple[bytes, ...], bytes]]:
    """Each line of an indented document with the lines enclosing it, by indentation.

    Two answers that differ only in the order of sibling elements give the same counter;
    a line moved under another parent does not. Lines are compared with the namespace
    prefixes they declare for themselves masked (``_masked``).
    """
    placed: Counter[tuple[tuple[bytes, ...], bytes]] = Counter()
    enclosing: list[tuple[int, bytes]] = []
    for line in map(_masked, text.split(b"\n")):
        if not line.strip():
            placed[((), line)] += 1
            continue
        indent = len(line) - len(line.lstrip(b" "))
        while enclosing and enclosing[-1][0] >= indent:
            enclosing.pop()
        placed[(tuple(parent for _, parent in enclosing), line)] += 1
        enclosing.append((indent, line))
    return placed


def _is_wadl(page: Page) -> bool:
    return (page.file or "").endswith(".wadl")


def canonical(page: Page, content: bytes) -> bytes:
    """A WADL file in a form with the order of its sibling elements fixed; any other as is.

    The service generates its WADL files per request and orders sibling elements differently
    from one request to the next. The form lists each line with the lines that enclose it by
    indentation, sorted, the namespace prefixes a line declares for itself masked, so two
    answers that differ only in that order read the same, and a line moved under another
    parent does not (sdk-core ADR-0062, decision 5).
    """
    if not _is_wadl(page):
        return content
    placed = _placed_lines(content)
    lines = (b"\x00".join((*parents, line)) for parents, line in sorted(placed.elements()))
    return b"\n".join(lines)


def kept_as_recorded(page: Page, recorded: bytes | None, body: bytes) -> bytes:
    """``recorded`` where ``body`` holds its lines in another order alone, else ``body``.

    So a refresh shows a WADL file's real changes only; a document that is no WADL, or one
    without a recorded file, is written as fetched.
    """
    if (
        recorded is not None
        and recorded != body
        and canonical(page, recorded) == canonical(page, body)
    ):
        _log(f"  {page.file}: the same elements in another order; the file is kept as recorded")
        return recorded
    return body


# --- the pages' checks and notes ---------------------------------------------------------


def _date(epoch: int) -> str:
    return datetime.fromtimestamp(epoch, UTC).strftime("%Y-%m-%d")


def guide_note(converted: Converted) -> str:
    """A user-guide page's note: the conversion, its tables kept as HTML, its last change."""
    note = (
        "converted from HTML; the page's HTML carries a per-request token, which the Markdown "
        "drops, so the row records no size or sha256 of its body"
    )
    if converted.html_tables:
        plural = "s" if converted.html_tables > 1 else ""
        note += (
            f"; {converted.html_tables} table{plural} with merged cells or a nested table "
            "kept as HTML"
        )
    if converted.modified:
        note += f"; its content items were last modified {_date(converted.modified[-1])} (UTC)"
    return note


def _names(names: Sequence[str]) -> str:
    return ", ".join(f"`{name}`" for name in names)


def _cube(sample: Sample, response: Response) -> dict[str, Any]:
    """The JSON-stat sample's dataset; one without its ``class`` or its ``id`` stops."""
    cube = parse_json(response)
    if not isinstance(cube, dict) or cube.get("class") != "dataset" or "id" not in cube:
        raise changed(sample.stat_url, "not a JSON-stat dataset (no class or id)")
    return cube


def _ids(cube: Mapping[str, Any]) -> list[str]:
    """The dataset's dimensions in order, ``time`` included."""
    return [str(name) for name in cube["id"]]


def _csv_rows(sample: Sample, response: Response) -> list[list[str]]:
    """The SDMX-CSV sample's rows, its header first; one without data or periods stops."""
    rows = list(csv.reader(io.StringIO(decode(response))))
    if len(rows) < 2:
        raise changed(sample.sdmx_url, "there are no data rows")
    header = rows[0]
    if "TIME_PERIOD" not in header or len(header) < 3:
        raise changed(sample.sdmx_url, f"there is no TIME_PERIOD column in {header}")
    return rows


def stat_note(sample: Sample, response: Response) -> str:
    """The JSON-stat sample's note: its version and its dimensions."""
    cube = _cube(sample, response)
    version = cube.get("version", "(no version)")
    return (
        f"a JSON-stat {version} dataset (specification: {JSON_STAT_SPEC}, cited, not "
        f"snapshotted) with the dimensions {_names(_ids(cube))}; the Statistics API's "
        f"answer{sample.where}"
    )


def sdmx_note(sample: Sample, response: Response) -> str:
    """The SDMX-CSV sample's note: its columns and the order its key follows."""
    header = _csv_rows(sample, response)[0]
    order = ".".join(header[2 : header.index("TIME_PERIOD")])
    return (
        f"SDMX-CSV with the columns {_names(header)}; the key `{sample.key}` follows the "
        f"dimension order {order}, as the CSV header and the JSON-stat sample's `id` list "
        f'it, and `user-guide/{KEY_ORDER_PAGE}.md` states "{KEY_ORDER_SENTENCE}"; the SDMX '
        f"2.1 API's answer{sample.where}"
    )


def check_samples(sample: Sample, stat: Response, sdmx: Response) -> None:
    """Stop where a dataset's two samples and its key do not line up.

    The SDMX-CSV's dimension columns follow the order of the JSON-stat ``id`` without
    ``time``, the key has one position per dimension, and every SDMX-CSV row lies inside
    the key.
    """
    dimensions = [name for name in _ids(_cube(sample, stat)) if name != "time"]
    rows = _csv_rows(sample, sdmx)
    header = rows[0]
    columns = header[2 : header.index("TIME_PERIOD")]
    key = sample.key.split(".")
    if columns != dimensions or len(key) != len(dimensions):
        raise changed(
            sample.sdmx_url,
            f"the SDMX-CSV dimension columns {columns}, the JSON-stat dimensions {dimensions} "
            f"and the key {sample.key} do not line up",
        )
    for row in rows[1:]:
        values = dict(zip(header, row, strict=True))
        wrong = [
            name
            for name, code in zip(dimensions, key, strict=True)
            if code and values[name] != code
        ]
        if wrong:
            raise changed(sample.sdmx_url, f"a row lies outside the key in {wrong}: {row}")


def check_key_order(content: bytes) -> None:
    """Stop where the data-query page no longer states the key's order in a block of its own."""
    blocks = content.decode("utf-8").split("\n\n")
    if not any(_plain(block.strip()) == KEY_ORDER_SENTENCE for block in blocks):
        raise changed(
            GUIDE_BASE + KEY_ORDER_PAGE,
            f"it no longer states {KEY_ORDER_SENTENCE!r}, which the samples' key order needs",
        )


# --- the hooks -------------------------------------------------------------------------


def reduce(page: Page, response: Response) -> bytes:
    """The content of a page's file.

    A user-guide page as Markdown; a WADL file as recorded where only the order of its
    elements moved; every other file, the OpenAPI document and the samples, as fetched. An
    empty document stops the run.
    """
    if (page.file or "").startswith("user-guide/"):
        return guide_markdown(page, response).markdown.encode("utf-8")
    if page.sample:
        return response.body
    if not response.body.strip():
        raise changed(page.url, "it answers an empty body, not a document")
    if _is_wadl(page) and page.file is not None:
        recorded = OUT / page.file
        kept = recorded.read_bytes() if recorded.is_file() else None
        return kept_as_recorded(page, kept, response.body)
    return response.body


def note(row: Row) -> str:
    """Check the page a row was read from and write the row's note.

    A page that changed in a way the script does not know stops the run with ``changed``,
    before anything is written.
    """
    page, response = row.page, row.response
    if (page.file or "").startswith("user-guide/"):
        return guide_note(guide_markdown(page, response))
    sample = _SAMPLE_FILES.get(page.file or "")
    if sample is not None and page.file == sample.stat_file:
        return stat_note(sample, response)
    if sample is not None:
        return sdmx_note(sample, response)
    return row.note


def sections(rows: Sequence[Row]) -> Sequence[Section]:
    """Check the samples against each other and the data-query page, with every row read.

    The checks of one page against another (sdk-core ADR-0062): they write no section of
    their own, ``()``, and stop the run with ``changed`` before anything is written. A run
    without one of the rows stops too, since a check that cannot run must not read as one
    that passed.
    """
    by_file = {row.page.file: row for row in rows if row.page.file}
    needed = [f"user-guide/{KEY_ORDER_PAGE}.md"]
    needed += [file for sample in SAMPLES for file in (sample.stat_file, sample.sdmx_file)]
    missing = [file for file in needed if file not in by_file]
    if missing:
        raise SystemExit(
            f"The samples are checked against each other and against user-guide/"
            f"{KEY_ORDER_PAGE}.md, and this run read no row of {', '.join(missing)}: declare "
            "them all. Nothing was written."
        )
    check_key_order(by_file[f"user-guide/{KEY_ORDER_PAGE}.md"].content or b"")
    for sample in SAMPLES:
        stat, sdmx = by_file[sample.stat_file], by_file[sample.sdmx_file]
        check_samples(sample, stat.response, sdmx.response)
    return ()


# --- the declaration -------------------------------------------------------------------

_LICENCE = "the notice's licence of the website's editorial content"
_REUSE = "the notice's reuse of the statistical data"
_EXCEPTION = "under Exceptions, the data and documents that may not be reused commercially"
_MODIFIED_REUSE = (
    "under Exceptions, the notice's clause on modified reuse, which the conversion of the "
    "user-guide pages is: How this is captured states the changes and the disclaimer"
)
_CITATION = "under How to cite Eurostat products, Datasets: the citation the notice asks for"
ATTRIBUTION = (
    Statement(
        "The copyright for the editorial content of this website, which is owned by the EU, "
        "is licensed under the Creative Commons Attribution 4.0 International licence.",
        COPYRIGHT_URL,
        where=_LICENCE,
    ),
    Statement(
        "Reuse of statistical data, metadata, publications, and other dissemination tools "
        "published on this website for commercial or non-commercial purposes is authorised "
        "provided the source is acknowledged.",
        COPYRIGHT_URL,
        where=_REUSE,
    ),
    Statement(
        "The following Eurostat data and documents may not be reused for commercial "
        "purposes, but non-commercial reuse is possible without restriction:",
        COPYRIGHT_URL,
        where=_EXCEPTION,
    ),
    Statement(
        "Data identified as belonging to sources other than Eurostat.",
        COPYRIGHT_URL,
        where=_EXCEPTION,
    ),
    Statement(
        "Publications or documents where the copyright belongs partly or fully to other "
        "organisations, for example concerning co-publications between Eurostat and other "
        "publishers.",
        COPYRIGHT_URL,
        where=_EXCEPTION,
    ),
    Statement("Data for countries other than:", COPYRIGHT_URL, where=_EXCEPTION),
    Statement("Member States of the European Union (EU)", COPYRIGHT_URL, where=_EXCEPTION),
    Statement(
        "Member States of the European Free Trade Association (EFTA)",
        COPYRIGHT_URL,
        where=_EXCEPTION,
    ),
    Statement("official EU acceding and candidate countries.", COPYRIGHT_URL, where=_EXCEPTION),
    Statement(
        "Trade data originating from Liechtenstein and Switzerland (as declaring countries), "
        "from 1995 onwards, and concerning the following commodity classifications: HS, SITC, "
        "BEC, NSTR and national commodity classifications.",
        COPYRIGHT_URL,
        where=_EXCEPTION,
    ),
    Statement(
        "Trade data originating from Austria (as a declaring country) for a level of detail "
        "of the Combined Nomenclature of 8 digits",
        COPYRIGHT_URL,
        where=_EXCEPTION,
    ),
    Statement(
        "When reuse involves translations of publications or modifications to the data or "
        "text, this must be stated clearly to the end user of the information. A disclaimer "
        "regarding the non-responsibility of Eurostat shall be included.",
        COPYRIGHT_URL,
        where=_MODIFIED_REUSE,
    ),
    Statement(
        "Source: [digital object identifier (DOI) number of the Eurostat dataset], [access date]",
        COPYRIGHT_URL,
        where=_CITATION,
    ),
    Statement(
        "Source: [Eurostat dataset datacode link], [access date]",
        COPYRIGHT_URL,
        where=f"{_CITATION} for a customised version of a dataset",
    ),
    Statement(
        "Copyright notice and free re-use of data",
        GUIDE_BASE + GUIDE_PAGES[0],
        where="the site's navigation on every user-guide page, its link to Eurostat's "
        f"copyright notice, which the snapshot reads at {COPYRIGHT_URL}",
        link=NAVIGATION_NOTICE_URL,
    ),
)
"""Every copyright line, licence or terms of use the pages state, as printed: those of
Eurostat's copyright notice, the terms themselves, which must print each of them on every
run, and the site's navigation's link to the notice, which the check reads past wherever it
stands as that link's text."""

CAPTURE = "\n\n".join(
    (
        f'The user guide "Data access via API" ({GUIDE_BASE}) is a set of server-rendered '
        "pages. Each page under `user-guide/` is converted to Markdown with the standard "
        "library's `html.parser`: the page's `h1` becomes the title and the page's main "
        'region (`id="main-content"`) the body, including the code snippets and notes the '
        "site places beside the articles; links and images are made absolute, and a table "
        "with merged cells or a nested table is kept as simplified HTML. The site's "
        "navigation, header, footer, scripts and styles are dropped. The pages' HTML carries "
        "a per-request token, which the Markdown drops, so a page's row records no size or "
        "sha256, and its file's diff shows a change.",
        "The user-guide pages are the website's editorial content, reproduced here as this "
        "package's reference with the source acknowledged in each row below; Eurostat's "
        "copyright notice asks that a modification be stated and that a disclaimer of "
        "Eurostat's responsibility be included. Changes made: each page is converted from "
        "HTML to Markdown, as the paragraph above says; the WADL files, the OpenAPI document "
        "and the samples are kept verbatim. The Markdown pages under `user-guide/` are this "
        "package's conversion of Eurostat's pages; Eurostat is not responsible for this "
        "reproduction or for any difference from the pages it serves. The copyright notice "
        "is read for the statements under Attribution, which it must print on every run, and "
        "is kept as no file.",
        f"The WADL files and the OpenAPI document come from {API_BASE}, those under "
        f"`api/comext/` from {COMEXT_BASE}, the second base, which serves the `DS-` datasets "
        "of Comext and Prodcom. The service generates its WADL files per request and orders "
        "sibling elements (`resource`, `method`) differently from one request to the next. A "
        "WADL answer whose lines, each taken with the lines that enclose it by indentation, "
        "are exactly those of the file already here leaves the file as it is, so a diff "
        "shows changes only, a line moved under another parent included; the namespace "
        "prefixes a line declares for itself (`ns3`, `ns4`, numbered by the service in "
        "document order) are masked for that comparison, and `--check` compares a WADL file "
        "in that form. The OpenAPI document is compared byte for byte.",
        "The samples are answers for one dataset of each base ("
        + ", ".join(f"`{sample.dataset}`" for sample in SAMPLES)
        + "), one country and two periods, each the Statistics API's JSON-stat and the SDMX "
        "2.1 API's SDMX-CSV; the script checks for each that the SDMX-CSV's dimension columns "
        "follow the order of the JSON-stat `id`, that the key has one position per "
        "dimension, that every SDMX-CSV row lies inside the key, and that the data-query "
        "page states the key's order. JSON-stat 2.0 is a third-party specification "
        f"({JSON_STAT_SPEC}): cited, not snapshotted.",
        "Eurostat's wiki holds two Confluence pages on the API: "
        + ", and ".join(f"{url}, on {subject}" for url, subject in WIKI_PAGES)
        + ". Both require EU Login, so the snapshot requests neither, and the public pages "
        "of the user guide are its statement of their subjects.",
        "After a 429 the one retry waits as long as the website asks in "
        "`X-Rate-Limit-Retry-After-Seconds` or `Retry-After`, "
        f"{QUOTA_PAUSE:g} s where it names no wait, and a wait over {MAX_QUOTA_WAIT:g} s stops "
        "the run.",
    )
)
"""``FETCHED.md``'s "How this is captured": what is converted, cut or left out, and why."""

SNAPSHOT = Snapshot(
    name="Eurostat dissemination API",
    slug=SOURCE,
    pages=(
        *(
            Page(
                GUIDE_BASE + path,
                f"user-guide/{path}.md",
                stable=False,
                note="converted from HTML",
            )
            for path in GUIDE_PAGES
        ),
        *(Page(url, file, note=f"verbatim; {note}") for file, url, note in DOCUMENTS),
        *(
            page
            for sample in SAMPLES
            for page in (
                Page(sample.stat_url, sample.stat_file, sample=True),
                Page(sample.sdmx_url, sample.sdmx_file, sample=True),
            )
        ),
        Page(
            COPYRIGHT_URL,
            stable=False,
            terms=True,
            note="Eurostat's copyright notice, the terms of the website's content: read for "
            "the statements under Attribution, which it must print on every run, and kept as "
            "no file; its HTML carries a per-request token, so the row records no size or "
            "sha256",
        ),
    ),
    attribution=ATTRIBUTION,
    not_fetched=tuple(NotFetched(url, reason) for url, reason in NOT_REQUESTED),
    capture=CAPTURE,
    out=OUT,
    pause=PAUSE,
    reduce=reduce,
    canonical=canonical,
    note=note,
    sections=sections,
    client=CLIENT,
)
"""The snapshot: the user-guide pages, the documents and the samples in the order of
``FETCHED.md``'s rows, then the copyright notice, whose statements the attribution quotes.
33 requests where no page redirects on its host and none is retried."""

if __name__ == "__main__":
    raise SystemExit(run(SNAPSHOT))
