"""Integration tests for POST /api/v1/jobs/from-url."""

import httpx
import respx
from httpx import ASGITransport, AsyncClient

from app.main import app

# A literal public IP keeps validate_job_url from doing a real DNS lookup.
JOB_URL = "https://93.184.216.34/job"

JSON_LD_HTML = """
<html><head>
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"JobPosting",
 "title":"Full Stack Developer","hiringOrganization":{"@type":"Organization","name":"Acme Corp"},
 "description":"<p>Build WordPress plugins and themes.</p>"}
</script>
</head><body></body></html>
"""


async def _post(client: AsyncClient, url: str) -> httpx.Response:
    return await client.post("/api/v1/jobs/from-url", json={"url": url})


@respx.mock
async def test_fetch_job_from_url_returns_content():
    respx.get(JOB_URL).mock(return_value=httpx.Response(200, text=JSON_LD_HTML))
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await _post(client, JOB_URL)
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "Full Stack Developer"
    assert data["company"] == "Acme Corp"
    assert "WordPress plugins" in data["content"]
    assert data["source"] == "json-ld"


@respx.mock
async def test_fetch_job_from_url_blocks_private_ip():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await _post(client, "http://127.0.0.1:8000/admin")
    assert resp.status_code == 422
    assert (
        "private" in resp.json()["detail"].lower()
        or "local" in resp.json()["detail"].lower()
    )


@respx.mock
async def test_fetch_job_from_url_rejects_non_http():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await _post(client, "ftp://example.com/job")
    assert resp.status_code == 422


@respx.mock
async def test_fetch_job_from_url_blocks_blocked_site():
    respx.get(JOB_URL).mock(return_value=httpx.Response(403, text="blocked"))
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await _post(client, JOB_URL)
    assert resp.status_code == 422
    assert "paste" in resp.json()["detail"].lower()
