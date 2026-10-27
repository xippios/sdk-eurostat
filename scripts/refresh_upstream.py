# /// script
# requires-python = ">=3.12"
# dependencies = []
#
# [tool.uv]
# exclude-newer = "2026-10-27T00:00:00Z"
# ///
"""Refresh the upstream documentation snapshot in ``docs/upstream/`` (``/refresh-upstream``).

Eurostat documents its dissemination API in the user guide "Data access via API"
(https://ec.europa.eu/eurostat/web/user-guides/data-browser/api-data-access/), a set of
server-rendered pages, and describes the services in WADL files and one OpenAPI document
served beside them. This script writes:

- ``user-guide/<page path>.md``: each user-guide page in ``GUIDE_PAGES``, converted to
  Markdown with the standard library's ``html.parser``: the page title (its ``h1``) and
  the page's main region, headings, paragraphs, lists, tables, code and links, without
  the site's header, footer, in-page navigation, scripts and styles. A table with merged
  cells or a nested table stays HTML (conventions §3); links and images are absolute.
- ``api/<file>``: the WADL files and the OpenAPI document in ``DOCUMENTS``, verbatim. The
  service generates its WADL files per request, with sibling elements in an order that
  changes between requests; a WADL answer whose lines, each with the lines enclosing it by
  indentation, are those of the file already here leaves the file as it is (the namespace
  prefixes a line declares for itself, which the service numbers in document order, are
  masked for the comparison).
- ``samples/<file>``: two small answers, verbatim: the Statistics API's JSON-stat answer
  ``JSON_STAT_URL`` and the SDMX 2.1 API's SDMX-CSV answer ``SDMX_CSV_URL``, structural
  samples of the formats (test fixtures are recorded separately, never here).
- ``FETCHED.md``: regenerated entirely: what was fetched, when, its size and sha256, the
  pages not fetched and why, and the attribution quoted from Eurostat's copyright notice.

Two Confluence pages (``WIKI_PAGES``) are requested once each without credentials; they
redirect an anonymous client to EU Login, and the script records that and stops
following there. The copyright notice is fetched for its licence and reuse lines, its
exceptions to commercial reuse, its clause on modified reuse and its citation wording,
which ``FETCHED.md`` quotes beside the snapshot's own disclaimer; the page itself is not
kept.

Everything is fetched before anything is written, one request at a time after a pause
of ``PAUSE`` seconds, each URL retried at most once: after a network error or a 5xx, and
after a 429, which waits as long as the answer asks (at least ``RETRY_PAUSE``, at most
``MAX_QUOTA_WAIT``). The website reports its remaining request budget in
``X-Rate-Limit-Remaining``, which the log shows. Files under the snapshot's
subdirectories that the run does not produce are removed; nothing else under
``docs/upstream/`` is touched. ``Fetched`` is the UTC time of the run in ISO 8601 with an
explicit ``Z``, taken once at the start (conventions §3). The pages carry a per-request
token in their HTML, which the Markdown drops, so the same upstream gives the same files
and ``FETCHED.md`` differs between runs only in ``Fetched``. No key exists or is read.
Run from the repository root::

    uv run scripts/refresh_upstream.py
"""

import argparse
import csv
import hashlib
import html
import http.client
import io
import json
import re
import textwrap
import time
import tomllib
import urllib.error
import urllib.request
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.message import Message
from html.parser import HTMLParser
from pathlib import Path
from typing import IO, Any
from urllib.parse import urljoin, urlsplit

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "docs/upstream"
COMMAND = "uv run scripts/refresh_upstream.py"
VERSION = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
USER_AGENT = f"xippios-eurostat/{VERSION} (+https://github.com/xippios)"
"""The package's own version, read from ``pyproject.toml``, so the name never goes stale."""

GUIDE_BASE = "https://ec.europa.eu/eurostat/web/user-guides/data-browser/api-data-access/"
GUIDE_PAGES = (
    "api-introduction",
    "api-getting-started",
    "api-getting-started/api",
    "api-getting-started/sdmx2.1",
    "api-getting-started/catalogue-api",
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
DOCUMENTS = (
    (
        "api/statistics-rest.wadl",
        "statistics/1.0/statistics-rest.wadl",
        "WADL of the Statistics API",
    ),
    ("api/sdmx-rest.wadl", "sdmx/2.1/sdmx-rest.wadl", "WADL of the SDMX 2.1 API"),
    ("api/catalogue.wadl", "catalogue/catalogue.wadl", "WADL of the Catalogue API"),
    ("api/async.wadl", "1.0/async/async.wadl", "WADL of the asynchronous API"),
    (
        "api/sdmx-rest.yaml",
        "swagger-ui/sdmx-rest.yaml",
        'OpenAPI 3.0 document "Eurostat SDMX RESTful API", the user guide\'s consolidated '
        "Open API specification: SDMX 2.1 and 3.0, asynchronous and catalogue paths; served "
        "under `swagger-ui/`, stored without `swagger` in its path, which detect-secrets' "
        "`is_swagger_file` filter would skip",
    ),
)
"""Upstream documents kept verbatim: snapshot path, URL relative to ``API_BASE``, note."""

SAMPLE_DATASET = "apro_mk_cola"
JSON_STAT_FILE = "samples/apro_mk_cola-json-stat.json"
JSON_STAT_URL = (
    f"{API_BASE}statistics/1.0/data/{SAMPLE_DATASET}?format=JSON&lang=EN&geo=AT&time=2022&time=2023"
)
SDMX_CSV_FILE = "samples/apro_mk_cola-sdmx-csv.csv"
SDMX_KEY = "A...THS_T.AT"
SDMX_CSV_URL = (
    f"{API_BASE}sdmx/2.1/data/{SAMPLE_DATASET}/{SDMX_KEY}"
    "?format=SDMX-CSV&startPeriod=2022&endPeriod=2023"
)
KEY_ORDER_PAGE = "api-detailed-guidelines/sdmx2-1/data-query"
KEY_ORDER_SENTENCE = "The key parameter defines values of the dimensions in the order of structure."
"""The data-query page's statement of the key's positions, checked to be there."""
JSON_STAT_SPEC = "https://json-stat.org/format/"

WIKI_PAGES = (
    ("https://wikis.ec.europa.eu/x/-AD9B", "SDMX 2.1 and asynchronous answers"),
    ("https://wikis.ec.europa.eu/x/c4eBBg", "the TSV format"),
)
"""Confluence pages the briefing names, requested once each without credentials."""
LOGIN_HOST = "webgate.ec.europa.eu"
"""EU Login, where an anonymous client is sent; never requested."""

NOT_REQUESTED = (
    (
        f"{GUIDE_BASE}api-getting-started/comext-database",
        "Comext and Prodcom (`DS-` datasets) are 0.2.0 (D44)",
    ),
    (
        "https://ec.europa.eu/eurostat/api/comext/dissemination",
        "the Comext host and its WADL files; Comext and Prodcom are 0.2.0 (D44)",
    ),
    (f"{GUIDE_BASE}api-detailed-guidelines/sdmx3-0", "SDMX 3.0 is out of 0.1.0's scope"),
    (f"{GUIDE_BASE}api-detailed-guidelines/sdmx3-0/data-query", "SDMX 3.0 is out of 0.1.0's scope"),
    (
        f"{GUIDE_BASE}api-detailed-guidelines/sdmx3-0/structure-queries",
        "SDMX 3.0 is out of 0.1.0's scope",
    ),
    (f"{API_BASE}sdmx/3.0/sdmx-rest.wadl", "SDMX 3.0 is out of 0.1.0's scope"),
    (f"{GUIDE_BASE}api-detailed-guidelines/catalogue-api/rss", "the RSS feed is not used here"),
    (
        f"{GUIDE_BASE}api-detailed-guidelines/catalogue-api/metabase",
        "the metabase file is not used here",
    ),
    (f"{GUIDE_BASE}api-faq/examples", "a FAQ child page outside this snapshot's list"),
    (f"{GUIDE_BASE}api-faq/excel-power-query", "a FAQ child page outside this snapshot's list"),
    (JSON_STAT_SPEC, "JSON-stat 2.0 is a third-party specification: cited, not snapshotted"),
)
"""Pages linked from the user guide that are deliberately not requested, with the reason."""

COPYRIGHT_URL = "https://ec.europa.eu/eurostat/web/main/help/copyright-notice"
LICENCE_START = "The copyright for the editorial content of this website"
REUSE_START = "Reuse of statistical data"
EXCEPTIONS_START = (
    "The following Eurostat data and documents may not be reused for commercial purposes"
)
EXCEPTIONS_ITEMS = (
    "Data identified as belonging to sources other than Eurostat",
    "Data for countries other than",
    "Trade data originating from Liechtenstein and Switzerland",
    "Trade data originating from Austria",
)
"""The notice's exceptions to commercial reuse that must be quoted; their absence stops the run."""
MODIFICATION_START = (
    "When reuse involves translations of publications or modifications to the data or text"
)
"""The notice's clause on modified reuse, which the Markdown conversion is."""
CITE_HEADING = "How to cite Eurostat products"
CITE_SUBHEADING = "Datasets"

SUBDIRS = ("user-guide", "api", "samples")
"""The snapshot's subdirectories, which this script owns entirely."""

TIMEOUT = 60.0
PAUSE = 5.0
"""Seconds before every request; requests never run in parallel. The website reports a
small request budget in ``X-Rate-Limit-Remaining`` that a series of requests a few seconds
apart drains (429 "Quota Exhausted"); five seconds apart, a run seldom meets a 429, and the
one retry covers it."""
RETRY_PAUSE = 10.0
"""Seconds before the one retry after a network error or a 5xx."""
QUOTA_PAUSE = 60.0
"""Seconds before the one retry after a 429 that names no wait of its own; a 429 that
names one is retried after it, but never sooner than ``RETRY_PAUSE``."""
MAX_QUOTA_WAIT = 900.0
"""The longest wait for a 429 the script accepts; a longer one stops the run."""
MIN_PAGE_CHARS = 400
"""A converted page shorter than this has lost its content; the run stops."""
TOKEN_MARKERS = ("p_auth", "authToken")
"""Per-request values of the site's HTML that must never reach a snapshot file."""

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
_SENTENCE = re.compile(r"(.+?\.)(?:\s|$)")
_CODE_OPEN, _CODE_CLOSE = "\x01", "\x02"
"""Code spans are marked while a line is built, so that adjacent ones merge into one."""
_CODE_SPAN = re.compile(f"{_CODE_OPEN}(.*?){_CODE_CLOSE}", re.DOTALL)
_BREAK = "\x00"
_LOCAL_PREFIX = re.compile(rb"xmlns:([A-Za-z_][\w.-]*)=")


def _log(message: str) -> None:
    print(message, flush=True)  # noqa: T201


# --- HTTP -------------------------------------------------------------------------------


@dataclass(frozen=True)
class Response:
    """One GET as served: the final status and body, and the redirects on the way."""

    url: str
    status: int
    body: bytes
    content_type: str | None
    location: str | None
    redirects: tuple[tuple[int, str], ...]


class _RetryableError(Exception):
    """A network error, a 5xx or a 429: worth one more attempt after ``wait`` seconds."""

    def __init__(self, message: str, wait: float) -> None:
        super().__init__(message)
        self.wait = wait


class _SameHostRedirects(urllib.request.HTTPRedirectHandler):
    """Follow redirects within the requested host only, remembering each hop.

    A redirect to another host is not followed: urllib then raises it as an
    ``HTTPError`` carrying the 3xx status and its ``Location``.
    """

    def __init__(self, host: str) -> None:
        super().__init__()
        self.host = host
        self.hops: list[tuple[int, str]] = []

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: IO[bytes],
        code: int,
        msg: str,
        headers: http.client.HTTPMessage,
        newurl: str,
    ) -> urllib.request.Request | None:
        """Follow ``newurl`` when it stays on the requested host; stop otherwise."""
        if urlsplit(newurl).hostname != self.host:
            return None
        self.hops.append((code, newurl))
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class _Counter:
    """Every request sent on the wire, redirect hops and retries included."""

    sent = 0


def _quota_wait(headers: Message) -> tuple[float, str]:
    """The wait a 429 names, at least ``RETRY_PAUSE``, and the header that named it."""
    for name in ("Retry-After", "X-Rate-Limit-Retry-After-Seconds"):
        value = headers.get(name)
        if value is not None and value.strip().isdigit():
            return max(float(value.strip()), RETRY_PAUSE), f"{name}: {value.strip()}"
    return QUOTA_PAUSE, "no wait named"


def _rate_note(headers: Message) -> str:
    remaining = headers.get("X-Rate-Limit-Remaining")
    return f", X-Rate-Limit-Remaining {remaining}" if remaining is not None else ""


def _unexpected(url: str, expect: str, got: str) -> SystemExit:
    return SystemExit(
        f"GET {url}: expected {expect}, got {got}.\nLook at the URL by hand and update "
        "scripts/refresh_upstream.py. Nothing was written."
    )


def _get(url: str, expect_redirect: bool) -> Response:
    host = urlsplit(url).hostname or ""
    redirects = _SameHostRedirects(host)
    opener = urllib.request.build_opener(redirects)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    _Counter.sent += 1
    try:
        with opener.open(request, timeout=TIMEOUT) as response:
            body: bytes = response.read()
            status: int = response.status
            headers: Message = response.headers
    except urllib.error.HTTPError as error:
        _Counter.sent += len(redirects.hops)
        status, headers = error.code, error.headers
        if status == 429:
            wait, named = _quota_wait(headers)
            message = f"HTTP 429 {error.reason} ({named}){_rate_note(headers)}"
            raise _RetryableError(message, wait) from None
        if status >= 500:
            raise _RetryableError(f"HTTP {status} {error.reason}", RETRY_PAUSE) from None
        if not (expect_redirect and 300 <= status < 400):
            raise _unexpected(url, "HTTP 200", f"HTTP {status} {error.reason}") from None
        body = error.read()
    except (http.client.HTTPException, OSError) as error:  # URLError is an OSError
        _Counter.sent += len(redirects.hops)
        raise _RetryableError(str(error), RETRY_PAUSE) from None
    else:
        _Counter.sent += len(redirects.hops)
        if expect_redirect:
            raise _unexpected(url, f"a redirect to {LOGIN_HOST}", f"HTTP {status}")
    encoding = headers.get("Content-Encoding", "identity").strip().lower()
    if encoding != "identity":
        raise SystemExit(f"GET {url}: unexpected Content-Encoding {encoding!r}")
    _log(
        f"  {url}: HTTP {status}"
        + "".join(f", {code} to {target}" for code, target in redirects.hops)
        + f", {len(body)} bytes ({headers.get_content_type()}){_rate_note(headers)}"
    )
    return Response(
        url,
        status,
        body,
        headers.get_content_type() if headers.get("Content-Type") else None,
        headers.get("Location"),
        tuple(redirects.hops),
    )


def fetch(url: str, *, expect_redirect: bool = False) -> Response:
    """GET ``url`` after a polite pause; retry once after a network error, a 5xx or a 429."""
    time.sleep(PAUSE)
    try:
        return _get(url, expect_redirect)
    except _RetryableError as error:
        if error.wait > MAX_QUOTA_WAIT:
            raise SystemExit(
                f"GET {url}: {error}; the answer asks for a wait of {error.wait:.0f} s, more "
                f"than {MAX_QUOTA_WAIT:.0f} s. Run again later. Nothing was written."
            ) from None
        _log(f"  {url}: {error}; retrying once in {error.wait:.0f} s")
        time.sleep(error.wait)
        try:
            return _get(url, expect_redirect)
        except _RetryableError as again:
            raise SystemExit(
                f"GET {url}: {again} (after one retry). Nothing was written."
            ) from None


def _text(response: Response) -> str:
    try:
        return response.body.decode("utf-8")
    except UnicodeDecodeError as error:
        raise SystemExit(f"GET {response.url}: body is not UTF-8 ({error})") from None


# --- HTML to Markdown -------------------------------------------------------------------


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
class Page:
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
        raise SystemExit(f"GET {url}: no element with id main-content. Nothing was written.")
    return main


def convert(text: str, url: str) -> Page:
    """Convert one user-guide page: its ``h1`` as the title, its main region as the body."""
    root = parse_html(text)
    heading = root.find(lambda e: e.tag == "h1")
    title = _squash(_Markdown(url).inline_children(heading)).replace("\n", " ") if heading else ""
    if not title:
        raise SystemExit(f"GET {url}: no h1 title. Nothing was written.")
    main = _main_region(root, url)
    renderer = _Markdown(url)
    blocks = [block for block in renderer.blocks(main) if block.strip()]
    modified = sorted(
        {int(match[:10]) for comment in main.comments() for match in _MODIFIED.findall(comment)}
    )
    page = Page(title, blocks, renderer.html_tables, modified)
    markdown = page.markdown
    leaked = [marker for marker in TOKEN_MARKERS if marker in markdown]
    if leaked:
        raise SystemExit(
            f"GET {url}: per-request values {leaked} in the Markdown. Nothing was written."
        )
    if len(markdown) < MIN_PAGE_CHARS:
        raise SystemExit(
            f"GET {url}: only {len(markdown)} characters of Markdown; the page's layout may "
            "have changed. Look at it by hand and update scripts/refresh_upstream.py. "
            "Nothing was written."
        )
    return page


# --- What is captured -------------------------------------------------------------------


@dataclass(frozen=True)
class Row:
    """One file of the snapshot and its ``FETCHED.md`` row."""

    path: str
    url: str
    content: bytes
    note: str


@dataclass(frozen=True)
class Missing:
    """One page recorded without a file: its URL, status and the reason."""

    url: str
    status: str
    reason: str


@dataclass(frozen=True)
class Attribution:
    """The lines ``FETCHED.md`` quotes from Eurostat's copyright notice."""

    licence: str
    reuse: str
    exceptions: str
    modification: str
    citation: list[str]


def _date(epoch: int) -> str:
    return datetime.fromtimestamp(epoch, UTC).strftime("%Y-%m-%d")


def guide_page(path: str) -> tuple[Row, Page]:
    """Fetch and convert one user-guide page."""
    url = GUIDE_BASE + path
    response = fetch(url)
    if response.content_type != "text/html":
        raise _unexpected(url, "text/html", str(response.content_type))
    page = convert(_text(response), url)
    note = "converted from HTML"
    if page.html_tables:
        plural = "s" if page.html_tables > 1 else ""
        note += (
            f"; {page.html_tables} table{plural} with merged cells or a nested table kept as HTML"
        )
    if page.modified:
        note += f"; its content items were last modified {_date(page.modified[-1])} (UTC)"
    content = page.markdown.encode("utf-8")
    _log(f"  user-guide/{path}.md: {len(content)} bytes, {len(page.blocks)} blocks")
    return Row(f"user-guide/{path}.md", url, content, note), page


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


def document(out: Path, path: str, relative: str, note: str) -> Row:
    """Fetch one upstream document, kept verbatim.

    The service generates its WADL files per request and orders sibling elements
    differently from one request to the next. A WADL answer whose lines, each with the
    lines enclosing it, are those of the file already in the snapshot leaves that file as
    it is, so a refresh shows real changes only. Other documents compare byte for byte.
    """
    url = API_BASE + relative
    body = fetch(url).body
    if not body.strip():
        raise _unexpected(url, "a document", "an empty body")
    existing = out / path
    if path.endswith(".wadl") and existing.is_file():
        kept = existing.read_bytes()
        if kept != body and _placed_lines(kept) == _placed_lines(body):
            _log(f"  {path}: the same elements in another order; the file is kept as it is")
            body = kept
    return Row(path, url, body, f"verbatim; {note}")


def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    keys = [key for key, _ in pairs]
    if len(set(keys)) != len(keys):
        raise ValueError(f"duplicate keys in {keys}")
    return dict(pairs)


def samples(key_order: str) -> list[Row]:
    """Fetch the two samples; check the dimension order and that the CSV rows lie in the key."""
    stat = fetch(JSON_STAT_URL)
    try:
        cube = json.loads(stat.body, object_pairs_hook=_no_duplicates)
    except ValueError as error:
        raise SystemExit(f"GET {JSON_STAT_URL}: not usable JSON ({error})") from None
    if not isinstance(cube, dict) or cube.get("class") != "dataset" or "id" not in cube:
        raise SystemExit(f"GET {JSON_STAT_URL}: not a JSON-stat dataset (no class or id)")
    ids = [str(name) for name in cube["id"]]
    dimensions = [name for name in ids if name != "time"]
    stat_note = (
        f"verbatim; a JSON-stat {cube.get('version', '(no version)')} dataset "
        f"(specification: {JSON_STAT_SPEC}, cited, not snapshotted) with the dimensions "
        f"{', '.join(f'`{name}`' for name in ids)}; a structural sample of the Statistics "
        "API's answer, not a test fixture"
    )

    sdmx = fetch(SDMX_CSV_URL)
    rows = list(csv.reader(io.StringIO(_text(sdmx))))
    if len(rows) < 2:
        raise SystemExit(f"GET {SDMX_CSV_URL}: no data rows")
    header = rows[0]
    if "TIME_PERIOD" not in header or len(header) < 3:
        raise SystemExit(f"GET {SDMX_CSV_URL}: no TIME_PERIOD column in {header}")
    columns = header[2 : header.index("TIME_PERIOD")]
    key = SDMX_KEY.split(".")
    if columns != dimensions or len(key) != len(dimensions):
        raise SystemExit(
            f"The SDMX-CSV dimension columns {columns}, the JSON-stat dimensions "
            f"{dimensions} and the key {SDMX_KEY} do not line up. Look at both by hand."
        )
    for row in rows[1:]:
        values = dict(zip(header, row, strict=True))
        wrong = [
            name
            for name, code in zip(dimensions, key, strict=True)
            if code and values[name] != code
        ]
        if wrong:
            raise SystemExit(f"GET {SDMX_CSV_URL}: a row outside the key in {wrong}: {row}")
    order = ".".join(dimensions)
    sdmx_note = (
        f"verbatim; SDMX-CSV with the columns {', '.join(f'`{name}`' for name in header)}; "
        f"the key `{SDMX_KEY}` follows the dimension order {order}, as the CSV header and the "
        f"JSON-stat sample's `id` list it, and `user-guide/{KEY_ORDER_PAGE}.md` states "
        f'"{key_order}"; a structural sample of the SDMX 2.1 API\'s answer, not a test fixture'
    )
    return [
        Row(JSON_STAT_FILE, JSON_STAT_URL, stat.body, stat_note),
        Row(SDMX_CSV_FILE, SDMX_CSV_URL, sdmx.body, sdmx_note),
    ]


def wiki_page(url: str, subject: str) -> Missing:
    """Request a Confluence page once without credentials; record where it sends us."""
    response = fetch(url, expect_redirect=True)
    target = urlsplit(urljoin(url, response.location or "")).hostname
    if target != LOGIN_HOST:
        raise _unexpected(url, f"a redirect to {LOGIN_HOST}", f"a redirect to {target}")
    hops = "".join(
        f"{code} within {urlsplit(hop).hostname}, then " for code, hop in response.redirects
    )
    return Missing(
        url,
        f"{hops}{response.status} to {target}",
        f"{subject}; EU Login is required, so the page is not fetched (no credentials are "
        "sent and no browser is imitated); the public user-guide pages above are the "
        "snapshot's statement of the subject",
    )


def _lines(page: Page) -> list[str]:
    """Every line of the page's blocks, without list and quote markers."""
    found: list[str] = []
    for block in page.blocks:
        for line in block.split("\n"):
            text = re.sub(r"^\s*(?:[-*>]|\d+\.)\s+", "", line).strip()
            if text:
                found.append(text)
    return found


def _changed(what: str) -> SystemExit:
    return SystemExit(
        f"{COPYRIGHT_URL}: {what}. The copyright notice changed: read it by hand and update "
        "scripts/refresh_upstream.py. Nothing was written."
    )


def _exceptions(page: Page) -> str:
    """The notice's list item on data excluded from commercial reuse, its sub-list included.

    The item and its nested lines are kept as converted, list markers and all, one level
    of indentation removed.
    """
    for block in page.blocks:
        lines = block.split("\n")
        starts = [i for i, line in enumerate(lines) if line.startswith(f"- {EXCEPTIONS_START}")]
        if not starts:
            continue
        start = starts[0]
        end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("- ")), None)
        nested = [line.removeprefix("  ") for line in lines[start + 1 : end]]
        present = {re.sub(r"^\s*- ", "", line) for line in nested}
        missing = [
            item for item in EXCEPTIONS_ITEMS if not any(p.startswith(item) for p in present)
        ]
        if missing:
            raise _changed(f"the exceptions to commercial reuse no longer name {missing}")
        return "\n".join([lines[start].removeprefix("- "), *nested]).strip("\n")
    raise _changed(f"no list item starting {EXCEPTIONS_START!r}")


def attribution() -> Attribution:
    """Fetch Eurostat's copyright notice and take the lines ``FETCHED.md`` quotes."""
    page = convert(_text(fetch(COPYRIGHT_URL)), COPYRIGHT_URL)
    lines = _lines(page)

    def sentence(prefix: str) -> str:
        found = [line for line in lines if line.startswith(prefix)]
        match = _SENTENCE.match(found[0]) if len(found) == 1 else None
        if match is None:
            raise _changed(f"expected one sentence starting {prefix!r}, found {len(found)} lines")
        return match.group(1)

    def line(prefix: str) -> str:
        found = [line for line in lines if line.startswith(prefix)]
        if len(found) != 1:
            raise _changed(f"expected one line starting {prefix!r}, found {len(found)}")
        return found[0]

    def heading(text: str, after: int) -> int:
        for index in range(after + 1, len(lines)):
            if lines[index].startswith("#") and lines[index].lstrip("# ") == text:
                return index
        raise _changed(f"no heading {text!r}")

    cite = heading(CITE_HEADING, -1)
    datasets = heading(CITE_SUBHEADING, cite)
    end = next((i for i in range(datasets + 1, len(lines)) if lines[i].startswith("#")), len(lines))
    citation = [*lines[cite + 1 : datasets], CITE_SUBHEADING, *lines[datasets + 1 : end]]
    if not any(line.startswith("Source:") for line in lines[datasets + 1 : end]):
        raise _changed(f"no 'Source:' line under {CITE_SUBHEADING!r}")
    return Attribution(
        sentence(LICENCE_START),
        sentence(REUSE_START),
        _exceptions(page),
        line(MODIFICATION_START),
        citation,
    )


# --- FETCHED.md ---------------------------------------------------------------------------


def _paragraph(*sentences: str) -> list[str]:
    text = " ".join(sentences)
    wrapped = textwrap.fill(text, width=88, break_long_words=False, break_on_hyphens=False)
    return [*wrapped.splitlines(), ""]


def _quote(paragraphs: list[str]) -> list[str]:
    """One blockquote, its paragraphs separated by an empty quoted line."""
    lines: list[str] = []
    for paragraph in paragraphs:
        if lines:
            lines.append(">")
        lines += [f"> {line}".rstrip() for line in paragraph.split("\n")]
    return [*lines, ""]


def _cell(value: str) -> str:
    return value.replace("|", r"\|").replace("\n", " ")


def render_fetched(
    rows: list[Row], missing: list[Missing], quoted: Attribution, fetched: str
) -> str:
    """The whole of ``FETCHED.md``."""
    lines = [
        "# Upstream documentation snapshot \N{EM DASH} Eurostat dissemination API",
        "",
        *_paragraph(
            "Source of truth for every endpoint wrapper (ADR-0003). The files in this",
            "directory are written by `scripts/refresh_upstream.py` (`/refresh-upstream`)",
            "from the pages and documents in the tables below and refreshed deliberately by",
            "PR, so that changes show up as diffs. This file is generated by the same script.",
            "Nothing here was edited by hand.",
        ),
        "## Attribution",
        "",
        *_paragraph(f"Eurostat's copyright notice, {COPYRIGHT_URL}, as fetched in this run:"),
        *_quote([quoted.licence, quoted.reuse]),
        *_paragraph('The same notice, under "Exceptions", on commercial reuse:'),
        *_quote([quoted.exceptions]),
        *_paragraph(
            "The user-guide pages are the website's editorial content, reproduced here as",
            "this package's reference (ADR-0003) with the source acknowledged in each row",
            "below. Changes made: each page is converted from HTML to Markdown, keeping its",
            "title, headings, paragraphs, lists, tables, code and links and dropping the",
            "site's navigation, header, footer, scripts and styles; tables with merged cells",
            "or a nested table are kept as simplified HTML. The WADL files, the OpenAPI",
            "document and the two samples are kept verbatim. A publisher's objection is met",
            "by replacing the text with a summary that keeps the names and semantics the",
            "wrappers rely on.",
        ),
        *_paragraph('The same notice, under "Exceptions", on modified reuse:'),
        *_quote([quoted.modification]),
        *_paragraph(
            "The Markdown pages under `user-guide/` are this package's conversion of",
            "Eurostat's pages, with the changes made stated in the paragraph above; Eurostat",
            "is not responsible for this reproduction or for any difference from the pages",
            "it serves.",
        ),
        *_paragraph(f'The same notice, under "{CITE_HEADING}":'),
        *_quote(quoted.citation),
        "## How this is captured",
        "",
        *_paragraph(
            f'The user guide "Data access via API" ({GUIDE_BASE}) is a set of',
            "server-rendered pages. Each page in the first table is converted to Markdown",
            "with the standard library's `html.parser`: the page's `h1` becomes the title and",
            'the page\'s main region (`id="main-content"`) the body, including the code',
            "snippets and notes the site places beside the articles. Links and images are",
            "made absolute. The pages' HTML carries a per-request token, which the Markdown",
            "drops, so a page's Bytes and sha256 are those of the Markdown file; for every",
            "other file they are those of the body as fetched, which is the file.",
        ),
        *_paragraph(
            f"The WADL files and the OpenAPI document come from {API_BASE}. The service",
            "generates its WADL files per request and orders sibling elements (`resource`,",
            "`method`) differently from one request to the next. A WADL answer whose lines,",
            "each taken with the lines that enclose it by indentation, are exactly those of",
            "the file already here leaves the file as it is, so a diff shows changes only,",
            "a line moved under another parent included; the namespace prefixes a line",
            "declares for itself (`ns3`, `ns4`, numbered by the service in document order)",
            "are masked for that comparison. The OpenAPI document is compared byte for",
            "byte. The two samples",
            f"are answers for one dataset (`{SAMPLE_DATASET}`), one country and two periods,",
            "the Statistics API's JSON-stat and the SDMX 2.1 API's SDMX-CSV; the script",
            "checks that the SDMX-CSV's dimension columns follow the order of the JSON-stat",
            "`id`, that the key has one position per dimension, and that every SDMX-CSV row",
            "lies inside the key. JSON-stat 2.0 is a third-party",
            f"specification ({JSON_STAT_SPEC}): cited, not snapshotted.",
        ),
        *_paragraph(
            "The second table lists pages that were requested without a file, with the",
            "status they answered, and pages deliberately not requested, with the reason.",
        ),
        *_paragraph(
            "`Fetched` is the UTC time of the run in ISO 8601 with an explicit `Z`, taken once",
            "at its start and the same in every row (conventions §3). Requests go one at a",
            f"time, {PAUSE:.0f} seconds apart, identified as `{USER_AGENT}`; no API key exists,",
            "and none is sent or read.",
        ),
        "## Files",
        "",
        "| File | URL | Fetched | Bytes | sha256 | Note |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        cells = [
            row.path,
            row.url,
            fetched,
            str(len(row.content)),
            hashlib.sha256(row.content).hexdigest(),
            row.note,
        ]
        lines.append("| " + " | ".join(_cell(cell) for cell in cells) + " |")
    lines += [
        "",
        "## Not fetched",
        "",
        "| URL | Status | Reason |",
        "| --- | --- | --- |",
    ]
    for item in missing:
        lines.append(f"| {_cell(item.url)} | {_cell(item.status)} | {_cell(item.reason)} |")
    lines += ["", f"Regenerate: `{COMMAND}`"]
    return "\n".join(lines) + "\n"


def write_snapshot(out: Path, rows: list[Row], fetched_md: str) -> None:
    """Write the files and ``FETCHED.md``; remove files the run no longer produces.

    Only files under ``SUBDIRS`` are removed, and directories left empty there.
    """
    if out.exists() and any(out.iterdir()) and not (out / "FETCHED.md").is_file():
        raise SystemExit(f"{out} is neither empty nor a snapshot (no FETCHED.md); not writing")
    files = {row.path: row.content for row in rows}
    for subdir in SUBDIRS:
        directory = out / subdir
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*"), reverse=True):
            relative = path.relative_to(out).as_posix()
            if path.is_file() and relative not in files:
                path.unlink()
                _log(f"  removed {relative}: no longer produced")
            elif path.is_dir() and not any(path.iterdir()):
                path.rmdir()
    for name, content in files.items():
        target = out / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    (out / "FETCHED.md").write_bytes(fetched_md.encode("utf-8"))


def main() -> None:
    """Fetch every page and document, then write the snapshot."""
    parser = argparse.ArgumentParser(description="Refresh docs/upstream/ from Eurostat.")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="snapshot directory")
    out: Path = parser.parse_args().out
    fetched = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    _log(f"Run {fetched}. User guide: {GUIDE_BASE}")
    rows: list[Row] = []
    pages: dict[str, Page] = {}
    for path in GUIDE_PAGES:
        row, page = guide_page(path)
        rows.append(row)
        pages[path] = page
    if not any(_plain(block) == KEY_ORDER_SENTENCE for block in pages[KEY_ORDER_PAGE].blocks):
        raise SystemExit(
            f"user-guide/{KEY_ORDER_PAGE}.md no longer states {KEY_ORDER_SENTENCE!r}; the "
            "sample's key order needs a look by hand. Nothing was written."
        )
    _log(f"Documents: {API_BASE}")
    rows += [document(out, *entry) for entry in DOCUMENTS]
    _log("Samples")
    rows += samples(KEY_ORDER_SENTENCE)
    _log("Confluence pages (not fetched past the login redirect)")
    missing = [wiki_page(url, subject) for url, subject in WIKI_PAGES]
    missing += [Missing(url, "not requested", reason) for url, reason in NOT_REQUESTED]
    _log(f"Copyright notice: {COPYRIGHT_URL}")
    quoted = attribution()

    write_snapshot(out, rows, render_fetched(rows, missing, quoted, fetched))
    _log(f"Wrote {len(rows)} files and FETCHED.md under {out}; {_Counter.sent} requests sent")


if __name__ == "__main__":
    main()
