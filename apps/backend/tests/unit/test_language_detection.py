"""Edit Mode language detection: explicit setting first, resume text otherwise."""

from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.routers import writing
from app.schemas.writing_report import WritingReport
from app.services.language_detection import (
    detect_language_from_text,
    detect_resume_language,
    resolve_resume_language,
    resolve_text_language,
)

PT_RESUME = {
    "personalInfo": {"name": "João Silva", "title": "Desenvolvedor Full Stack"},
    "summary": (
        "Desenvolvedor com experiência em WordPress e PHP, responsável por "
        "projetos de e-commerce e melhoria de processos da equipe."
    ),
    "workExperience": [
        {
            "id": 1,
            "title": "Desenvolvedor",
            "company": "Empresa",
            "description": [
                "Implementação de sistemas com integração de dados e atendimento a clientes",
                "Gestão de projetos com foco em resultados e soluções",
            ],
        }
    ],
    "additional": {"languages": ["Português", "Inglês"]},
}

EN_RESUME = {
    "personalInfo": {"name": "John Smith", "title": "Full Stack Developer"},
    "summary": (
        "Developer with experience building WordPress and PHP projects, "
        "responsible for e-commerce systems and team process improvements."
    ),
    "workExperience": [
        {
            "id": 1,
            "title": "Developer",
            "company": "Company",
            "description": [
                "Built systems with data integration for clients using the team tools",
                "Led projects focused on results and implementation of solutions",
            ],
        }
    ],
    "additional": {"languages": ["Portuguese", "English"]},
}


class TestDetection:
    def test_detects_brazilian_portuguese(self):
        assert detect_resume_language(PT_RESUME) == "pt"

    def test_detects_english(self):
        assert detect_resume_language(EN_RESUME) == "en"

    def test_ignores_spoken_languages(self):
        english_with_portuguese_languages = {
            **EN_RESUME,
            "additional": {"languages": ["Português", "Inglês"]},
        }
        assert detect_resume_language(english_with_portuguese_languages) == "en"

    def test_diacritics_alone_can_decide_short_text(self):
        assert detect_language_from_text("Implementação de sistemas") == "pt"

    def test_empty_text_is_english(self):
        assert detect_language_from_text("") == "en"
        assert detect_language_from_text("   ") == "en"

    @pytest.mark.parametrize("language", ["pt", "en"])
    def test_explicit_setting_wins(self, language: str):
        with patch(
            "app.services.language_detection.explicit_content_language",
            return_value=language,
        ):
            assert resolve_resume_language(PT_RESUME) == language
            assert resolve_resume_language(EN_RESUME) == language
            assert resolve_text_language("Implementação de sistemas") == language

    def test_no_setting_falls_back_to_detection(self):
        with patch(
            "app.services.language_detection.explicit_content_language",
            return_value=None,
        ):
            assert resolve_resume_language(PT_RESUME) == "pt"
            assert resolve_resume_language(EN_RESUME) == "en"


async def test_writing_check_scores_in_the_resume_language(monkeypatch):
    seen: list[str] = []

    def fake_report(data, language):  # noqa: ANN001, ARG001
        seen.append(language)
        return WritingReport()

    monkeypatch.setattr(writing, "writing_report", fake_report)
    monkeypatch.setattr(
        writing,
        "resolve_resume_language",
        lambda data: "pt",  # noqa: ARG005
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/writing/check", json={"resume_data": PT_RESUME}
        )

    assert response.status_code == 200, response.text
    assert seen == ["pt"]
