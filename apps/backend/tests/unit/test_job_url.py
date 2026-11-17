"""Unit tests for app.services.job_url."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.job_url import (
    JobUrlError,
    _blocked_hostname,
    _find_job_posting,
    _is_blocked_ip,
    extract_html_job,
    extract_json_ld_job,
    validate_job_url,
)


class TestBlockedAddresses:
    @pytest.mark.parametrize(
        "ip",
        [
            "127.0.0.1",
            "10.0.0.5",
            "172.16.0.1",
            "192.168.1.10",
            "169.254.1.1",
            "::1",
            "fe80::1",
            "0.0.0.0",
        ],
    )
    def test_blocks_private_loopback_and_link_local(self, ip):
        import ipaddress

        assert _is_blocked_ip(ipaddress.ip_address(ip))

    @pytest.mark.parametrize("ip", ["93.184.216.34", "8.8.8.8", "1.1.1.1"])
    def test_allows_public_ips(self, ip):
        import ipaddress

        assert not _is_blocked_ip(ipaddress.ip_address(ip))

    @pytest.mark.parametrize(
        "host", ["localhost", "localhost.localdomain", "foo.local", "printer.home.arpa"]
    )
    def test_blocks_local_hostnames(self, host):
        assert _blocked_hostname(host)

    @pytest.mark.parametrize(
        "host", ["example.com", "jobs.gupy.io", "boards.greenhouse.io"]
    )
    def test_allows_public_hostnames(self, host):
        assert not _blocked_hostname(host)


class TestValidateUrl:
    async def test_rejects_non_http_schemes(self):
        with pytest.raises(JobUrlError):
            await validate_job_url("ftp://example.com/job")

    async def test_rejects_empty_url(self):
        with pytest.raises(JobUrlError):
            await validate_job_url("")

    async def test_rejects_private_ip(self):
        with pytest.raises(JobUrlError):
            await validate_job_url("http://192.168.0.1/job")

    async def test_rejects_localhost(self):
        with pytest.raises(JobUrlError):
            await validate_job_url("http://localhost:8000/job")

    async def test_rejects_host_resolving_to_private_ip(self, monkeypatch):
        loop = MagicMock()
        loop.getaddrinfo = AsyncMock(return_value=[(2, 1, 6, "", ("10.0.0.7", 0))])
        monkeypatch.setattr(asyncio, "get_running_loop", lambda: loop)
        with pytest.raises(JobUrlError):
            await validate_job_url("https://example.com/job")

    async def test_allows_public_resolution(self, monkeypatch):
        loop = MagicMock()
        loop.getaddrinfo = AsyncMock(return_value=[(2, 1, 6, "", ("93.184.216.34", 0))])
        monkeypatch.setattr(asyncio, "get_running_loop", lambda: loop)
        assert (
            await validate_job_url("https://example.com/job")
            == "https://example.com/job"
        )


JSON_LD_DIRECT = """
<html><head>
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "JobPosting",
  "title": "Full Stack Developer",
  "hiringOrganization": {"@type": "Organization", "name": "Acme Corp"},
  "description": "<h2>Role</h2><p>Build web apps with <strong>PHP</strong> and WordPress.</p>"
}
</script>
</head><body></body></html>
"""

JSON_LD_GRAPH = """
<html><head>
<script type="application/ld+json">
{"@context": "https://schema.org", "@graph": [
  {"@type": "Organization", "name": "Acme Corp"},
  {"@type": "JobPosting", "title": "WordPress Engineer", "description": "Maintain themes and plugins."}
]}
</script>
</head><body></body></html>
"""


class TestJsonLdExtraction:
    def test_extracts_direct_job_posting(self):
        job = extract_json_ld_job(JSON_LD_DIRECT)
        assert job is not None
        assert job.source == "json-ld"
        assert job.title == "Full Stack Developer"
        assert job.company == "Acme Corp"
        assert "PHP" in job.content
        assert "Full Stack Developer" in job.content

    def test_extracts_from_graph_array(self):
        job = extract_json_ld_job(JSON_LD_GRAPH)
        assert job is not None
        assert job.title == "WordPress Engineer"
        assert "Maintain themes and plugins" in job.content

    def test_returns_none_without_job_posting(self):
        assert extract_json_ld_job("<html><body>no json</body></html>") is None

    def test_find_job_posting_in_nested_graph(self):
        posting = _find_job_posting(
            {"@context": "x", "@graph": [{"@type": "JobPosting", "title": "T"}]}
        )
        assert posting is not None
        assert posting["title"] == "T"


class TestHtmlFallback:
    def test_strips_boilerplate_and_keeps_content(self):
        html = """
        <html><head><title>x</title></head>
        <body>
          <nav>Home</nav>
          <script>alert('x')</script>
          <style>.x{}</style>
          <main><h1>Software Engineer</h1><p>Join us to build WordPress plugins.</p></main>
          <footer>Copyright</footer>
        </body></html>
        """
        job = extract_html_job(html)
        assert job.source == "html"
        assert "Software Engineer" in job.content
        assert "WordPress plugins" in job.content
        assert "alert('x')" not in job.content
        assert "Home" not in job.content
        assert "Copyright" not in job.content
