"""The tailoring pipeline feeds the domain vocabulary pack into its prompt."""

import json
from typing import Any
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.database import Database
from app.main import app
from app.routers import resumes
from app.schemas.models import ImproveDiffResult, ResumeData
from app.services import domain_pack

WORDPRESS_JOB = (
    "Desenvolvedor WordPress e WooCommerce para temas filhos, plugins "
    "próprios e Core Web Vitals."
)


@pytest.fixture
async def wordpress_case(
    isolated_db: Database,
    sample_resume: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[AsyncClient, dict[str, str], AsyncMock]:
    source = ResumeData.model_validate(sample_resume).model_dump()
    original = await isolated_db.create_resume_atomic_master(
        content=json.dumps(source), processed_data=source, processing_status="ready"
    )
    job = await isolated_db.create_job(WORDPRESS_JOB)
    monkeypatch.setattr(resumes, "_load_config", lambda: {})
    monkeypatch.setattr(resumes, "get_content_language", lambda: "en")
    monkeypatch.setattr(resumes, "_get_default_prompt_id", lambda: "keywords")
    monkeypatch.setattr(
        resumes,
        "extract_job_keywords",
        AsyncMock(return_value={"keywords": ["WordPress"], "required_skills": []}),
    )
    diff = AsyncMock(return_value=ImproveDiffResult(changes=[]))
    monkeypatch.setattr(resumes, "generate_resume_diffs", diff)
    monkeypatch.setattr(
        resumes,
        "refine_resume",
        AsyncMock(side_effect=RuntimeError("Synthetic unavailable refinement")),
    )
    monkeypatch.setattr(
        resumes, "generate_resume_title", AsyncMock(return_value="WordPress dev")
    )
    monkeypatch.setattr(domain_pack, "load_config", lambda: {"domain_pack": "auto"})
    client = AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    )
    return client, {"resume_id": original["resume_id"], "job_id": job["job_id"]}, diff


async def test_auto_pack_reaches_the_diff_prompt(
    wordpress_case: tuple[AsyncClient, dict[str, str], AsyncMock],
) -> None:
    client, payload, diff = wordpress_case
    async with client:
        response = await client.post("/api/v1/resumes/improve", json=payload)

    assert response.status_code == 200, response.text
    section = diff.call_args.kwargs["domain_pack_section"]
    assert "DOMAIN VOCABULARY" in section
    assert "WooCommerce" in section
    assert "Never add a tool, plugin, platform" in section


async def test_off_setting_sends_no_pack(
    wordpress_case: tuple[AsyncClient, dict[str, str], AsyncMock],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, payload, diff = wordpress_case
    monkeypatch.setattr(domain_pack, "load_config", lambda: {"domain_pack": "off"})

    async with client:
        response = await client.post("/api/v1/resumes/improve", json=payload)

    assert response.status_code == 200, response.text
    assert diff.call_args.kwargs["domain_pack_section"] == ""
