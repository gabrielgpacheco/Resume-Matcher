"""Fetch a job description from a URL.

Extraction order:
  1. ``JobPosting`` JSON-LD (``application/ld+json``), which most modern job
     boards (Greenhouse, Lever, Gupy, Workable, ...) emit;
  2. HTML fallback: strip navigation/boilerplate and convert the main content
     to Markdown.

SSRF protection: only ``http``/``https`` URLs whose host does not resolve to a
loopback/private/link-local/reserved address are fetched, so a job URL cannot be
used to reach ``localhost`` or the machine's internal network.
"""

import asyncio
import ipaddress
import json
import logging
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx
from bs4 import BeautifulSoup
from markdownify import markdownify as _markdownify

logger = logging.getLogger(__name__)

#: Maximum HTML body we accept before rejecting the page.
MAX_BODY_BYTES = 3 * 1024 * 1024
#: Fetch timeout: connect + read.
FETCH_TIMEOUT_SECONDS = 15.0
#: Identify ourselves; several job boards refuse a generic HTTP-library UA.
USER_AGENT = "resume-matcher/1.4.0 (+job-url)"

#: Hostnames that never point at a public job board.
_LOCAL_HOSTNAME_SUFFIXES = (
    ".local",
    ".internal",
    ".localhost",
    ".lan",
    ".home",
    ".home.arpa",
    ".invalid",
)
_LOCAL_HOSTNAMES = frozenset({"localhost", "localhost.localdomain"})


class JobUrlError(ValueError):
    """Raised when a URL is invalid or points at a blocked address."""


@dataclass
class FetchedJob:
    """A job description extracted from a URL."""

    content: str
    title: str = ""
    company: str = ""
    source: str = "url"


def _is_blocked_ip(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_reserved
        or address.is_multicast
        or address.is_unspecified
    )


def _blocked_hostname(host: str) -> bool:
    lowered = host.lower()
    if lowered in _LOCAL_HOSTNAMES:
        return True
    return any(lowered.endswith(suffix) for suffix in _LOCAL_HOSTNAME_SUFFIXES)


async def validate_job_url(url: str) -> str:
    """Return the trimmed URL, or raise :class:`JobUrlError` when it is not fetchable.

    Blocks non-http(s) schemes, literal private/loopback IPs, local hostnames,
    and hostnames that resolve to a blocked address (DNS-rebinding guard).
    """
    stripped = (url or "").strip()
    if not stripped:
        raise JobUrlError("A URL is required")

    parts = urlsplit(stripped)
    if parts.scheme not in ("http", "https"):
        raise JobUrlError("Only http:// and https:// URLs are supported")
    host = parts.hostname
    if not host:
        raise JobUrlError("Invalid URL")

    # Literal IP address?
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None

    if address is not None:
        if _is_blocked_ip(address):
            raise JobUrlError("This URL points to a private or local address")
        return stripped

    if _blocked_hostname(host):
        raise JobUrlError("This URL points to a local address")

    # DNS-rebinding guard: every address the host resolves to must be public.
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None:
        try:
            infos = await loop.getaddrinfo(host, None)
        except OSError as exc:
            raise JobUrlError("Could not resolve this URL") from exc
        for info in infos:
            try:
                resolved = ipaddress.ip_address(info[4][0])
            except (IndexError, ValueError):
                continue
            if _is_blocked_ip(resolved):
                raise JobUrlError("This URL resolves to a private or local address")

    return stripped


def _find_job_posting(node: object) -> dict | None:
    """Return the first ``JobPosting`` dict inside a JSON-LD object, list, or ``@graph``."""
    if isinstance(node, dict):
        node_type = node.get("@type")
        if node_type == "JobPosting" or (
            isinstance(node_type, list) and "JobPosting" in node_type
        ):
            return node
        for value in node.values():
            found = _find_job_posting(value)
            if found is not None:
                return found
    elif isinstance(node, list):
        for item in node:
            found = _find_job_posting(item)
            if found is not None:
                return found
    return None


def _html_to_markdown(html: str) -> str:
    return _markdownify(html, heading_style="ATX").strip()


def _first_text(value: object) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        for item in value:
            text = _first_text(item)
            if text:
                return text
    return ""


def _company_from_posting(posting: dict) -> str:
    org = posting.get("hiringOrganization") or posting.get("organization") or {}
    if isinstance(org, dict):
        return _first_text(org.get("name"))
    return _first_text(org)


def _description_from_posting(posting: dict) -> str:
    description = _first_text(posting.get("description"))
    if description:
        # The description is frequently HTML even though the field is "text".
        return _html_to_markdown(description)
    # Some boards split the description into structured fields.
    extra: list[str] = []
    for key in (
        "responsibilities",
        "qualifications",
        "skills",
        "experienceRequirements",
    ):
        value = posting.get(key)
        if not value:
            continue
        if isinstance(value, list):
            extra.extend(_first_text(item) for item in value)
        else:
            extra.append(_first_text(value))
    return "\n".join(item for item in extra if item).strip()


def _posting_to_job(posting: dict) -> FetchedJob:
    title = _first_text(posting.get("title"))
    company = _company_from_posting(posting)
    description = _description_from_posting(posting)

    header = " — ".join(part for part in (title, company) if part)
    content = "\n\n".join(part for part in (header, description) if part).strip()
    return FetchedJob(content=content, title=title, company=company, source="json-ld")


def extract_json_ld_job(html: str) -> FetchedJob | None:
    """Extract a ``JobPosting`` from any ``application/ld+json`` blocks."""
    soup = BeautifulSoup(html, "html.parser")
    for script in soup.find_all("script", type="application/ld+json"):
        raw = script.string or script.get_text() or ""
        if not raw.strip():
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        posting = _find_job_posting(data)
        if posting is not None:
            return _posting_to_job(posting)
    return None


#: Candidate containers for the HTML fallback, in order of preference.
_HTML_CONTAINER_SELECTORS = (
    "article",
    "main",
    ".posting",
    "#content",
    ".job-description",
    ".job__description",
    "[data-automation='jobPostingDescription']",
)


def extract_html_job(html: str) -> FetchedJob:
    """Fallback: strip boilerplate and convert the main page content to Markdown."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(
        [
            "script",
            "style",
            "nav",
            "footer",
            "header",
            "aside",
            "noscript",
            "iframe",
            "form",
            "svg",
        ]
    ):
        tag.decompose()

    container = None
    for selector in _HTML_CONTAINER_SELECTORS:
        found = soup.select_one(selector)
        if found is not None:
            container = found
            break

    root = container or soup.body or soup
    content = _html_to_markdown(str(root))
    return FetchedJob(content=content, source="html")


async def fetch_job_from_url(url: str) -> FetchedJob:
    """Validate, fetch, and extract a job description from ``url``.

    Raises :class:`JobUrlError` for a blocked/invalid URL, a failed fetch, or a
    page that yields no usable text.
    """
    clean_url = await validate_job_url(url)

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(FETCH_TIMEOUT_SECONDS),
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
        ) as client:
            async with client.stream("GET", clean_url) as response:
                response.raise_for_status()
                chunks: list[bytes] = []
                total = 0
                async for chunk in response.aiter_bytes():
                    chunks.append(chunk)
                    total += len(chunk)
                    if total > MAX_BODY_BYTES:
                        raise JobUrlError("This page is too large to process")
                body = b"".join(chunks)
                encoding = response.encoding or "utf-8"
    except JobUrlError:
        raise
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if status in (401, 403, 429):
            raise JobUrlError(
                "This site is blocking automated access. Paste the job "
                "description text instead."
            ) from exc
        raise JobUrlError("Could not fetch this URL") from exc
    except httpx.HTTPError as exc:
        raise JobUrlError("Could not fetch this URL") from exc

    html = body.decode(encoding, errors="replace")

    job = extract_json_ld_job(html)
    if job is None:
        job = extract_html_job(html)

    if not job.content or not job.content.strip():
        raise JobUrlError(
            "No job description could be found on this page. Paste the text instead."
        )

    return job
