"""GET /resumes/{id}/docx: HTTP layer over the DOCX export."""

import json
from io import BytesIO
from typing import Any

from docx import Document
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.services.docx_export import DOCX_MEDIA_TYPE

RESUME = {
    "personalInfo": {
        "name": "Jane Doe",
        "title": "Full Stack Developer",
        "email": "jane@example.com",
    },
    "summary": "Full stack developer focused on WordPress and PHP.",
    "workExperience": [
        {
            "id": 1,
            "title": "WordPress Developer",
            "company": "Studio",
            "years": "2022 - Present",
            "description": ["Built WooCommerce stores with PHP"],
        }
    ],
    "sectionMeta": [],
    "customSections": {},
}


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_downloads_an_ats_friendly_docx(
    isolated_db: Any, sample_resume: dict[str, Any]
) -> None:
    resume = await isolated_db.create_resume(
        content="# Jane Doe\n",
        processed_data=sample_resume,
        processing_status="ready",
    )

    async with _client() as client:
        response = await client.get(f"/api/v1/resumes/{resume['resume_id']}/docx")

    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == DOCX_MEDIA_TYPE
    assert (
        response.headers["content-disposition"]
        == f'attachment; filename="resume_{resume["resume_id"]}.docx"'
    )

    doc = Document(BytesIO(response.content))
    texts = [paragraph.text for paragraph in doc.paragraphs]
    assert texts[0] == "Jane Doe"
    assert "Experience" in texts
    assert any(text.startswith("MIT") for text in texts)
    assert doc.tables == []


async def test_a_builder_saved_resume_exports_from_its_json_content(
    isolated_db: Any,
) -> None:
    resume = await isolated_db.create_resume(
        content=json.dumps(RESUME),
        content_type="json",
        processing_status="ready",
    )

    async with _client() as client:
        response = await client.get(f"/api/v1/resumes/{resume['resume_id']}/docx")

    assert response.status_code == 200, response.text
    texts = [
        paragraph.text for paragraph in Document(BytesIO(response.content)).paragraphs
    ]
    assert "Built WooCommerce stores with PHP" in texts


async def test_an_unknown_resume_is_a_404(isolated_db: Any) -> None:
    async with _client() as client:
        response = await client.get("/api/v1/resumes/missing/docx")

    assert response.status_code == 404


async def test_an_unprocessed_resume_is_a_409(isolated_db: Any) -> None:
    resume = await isolated_db.create_resume(content="# Just markdown\n")

    async with _client() as client:
        response = await client.get(f"/api/v1/resumes/{resume['resume_id']}/docx")

    assert response.status_code == 409
    assert "Word document" in response.json()["detail"]


async def test_invalid_structured_data_is_a_409(isolated_db: Any) -> None:
    resume = await isolated_db.create_resume(
        content="{}",
        content_type="json",
        processed_data={"personalInfo": "not an object"},
        processing_status="ready",
    )

    async with _client() as client:
        response = await client.get(f"/api/v1/resumes/{resume['resume_id']}/docx")

    assert response.status_code == 409


async def test_structurally_empty_data_is_a_409(isolated_db: Any) -> None:
    resume = await isolated_db.create_resume(
        content="{}",
        content_type="json",
        processed_data={},
        processing_status="ready",
    )

    async with _client() as client:
        response = await client.get(f"/api/v1/resumes/{resume['resume_id']}/docx")

    assert response.status_code == 409
