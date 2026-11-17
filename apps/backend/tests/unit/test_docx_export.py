"""Unit tests for the ATS-friendly DOCX export (no HTTP)."""

from io import BytesIO
from typing import Any

import pytest
from docx import Document

from app.schemas.models import DEFAULT_SECTION_META, ResumeData
from app.services.docx_export import (
    build_resume_docx,
    format_date_range,
    group_skills,
    has_renderable_content,
)


def _document(data: dict[str, Any]) -> Any:
    return Document(BytesIO(build_resume_docx(data)))


def _texts(doc: Any) -> list[str]:
    return [paragraph.text for paragraph in doc.paragraphs]


def _headings(doc: Any) -> list[str]:
    return [
        paragraph.text
        for paragraph in doc.paragraphs
        if paragraph.style.name == "Heading 1"
    ]


def _meta(**overrides: Any) -> list[dict[str, Any]]:
    meta = [dict(item) for item in DEFAULT_SECTION_META]
    for item in meta:
        item.update(overrides.get(item["key"], {}))
    return meta


def test_document_is_a_single_column_without_tables(
    sample_resume: dict[str, Any],
) -> None:
    doc = _document(sample_resume)

    assert doc.tables == []
    body = doc.element.body.xml
    assert "<w:tbl>" not in body
    assert "txbxContent" not in body


def test_sections_are_native_headings_in_section_meta_order(
    sample_resume: dict[str, Any],
) -> None:
    doc = _document(sample_resume)

    assert _headings(doc) == [
        "Summary",
        "Experience",
        "Education",
        "Projects",
        "Skills & Awards",
    ]
    # The name is the first paragraph and the loudest run in the document.
    first = doc.paragraphs[0]
    assert first.text == "Jane Doe"
    assert first.runs[0].bold is True


def test_header_carries_the_contact_line(sample_resume: dict[str, Any]) -> None:
    texts = _texts(_document(sample_resume))

    assert "Senior Backend Engineer" in texts
    contact = next(text for text in texts if "jane@example.com" in text)
    assert "+1-555-0100" in contact and "linkedin.com/in/janedoe" in contact


def test_hidden_sections_and_custom_order_are_respected(
    sample_resume: dict[str, Any],
) -> None:
    meta = _meta(summary={"isVisible": False})
    meta.append(
        {
            "id": "custom_1",
            "key": "custom_1",
            "displayName": "Volunteering",
            "sectionType": "stringList",
            "isDefault": False,
            "isVisible": True,
            "order": 0,
        }
    )
    data = {
        **sample_resume,
        "sectionMeta": meta,
        "customSections": {
            "custom_1": {
                "sectionType": "stringList",
                "strings": ["Mentored at Code Club", "Volunteer at PyCon"],
            }
        },
    }

    doc = _document(data)

    headings = _headings(doc)
    assert headings[0] == "Volunteering"
    assert "Summary" not in headings
    assert "Mentored at Code Club, Volunteer at PyCon" in _texts(doc)


def test_description_styles_decide_between_bullets_and_plain_lines(
    sample_resume: dict[str, Any],
) -> None:
    data = {
        **sample_resume,
        "workExperience": [
            {
                **sample_resume["workExperience"][0],
                "description": ["Plain intro line", "Bulleted achievement"],
                "descriptionStyles": ["plain", "bullet"],
            }
        ],
        "personalProjects": [],
    }

    doc = _document(data)

    styles = {
        paragraph.text: paragraph.style.name
        for paragraph in doc.paragraphs
        if paragraph.text in {"Plain intro line", "Bulleted achievement"}
    }
    assert styles == {
        "Plain intro line": "Normal",
        "Bulleted achievement": "List Bullet",
    }


def test_inline_formatting_is_kept_as_runs(sample_resume: dict[str, Any]) -> None:
    data = {
        **sample_resume,
        "workExperience": [
            {
                **sample_resume["workExperience"][0],
                "description": [
                    "Built <strong>APIs</strong> with <em>FastAPI</em> &amp; docs"
                ],
                "descriptionStyles": ["bullet"],
            }
        ],
        "personalProjects": [],
    }

    doc = _document(data)
    paragraph = next(
        p for p in doc.paragraphs if p.text == "Built APIs with FastAPI & docs"
    )

    assert [run.text for run in paragraph.runs if run.bold] == ["APIs"]
    assert [run.text for run in paragraph.runs if run.italic] == ["FastAPI"]


def test_condensed_old_roles_move_under_earlier_experience(
    sample_resume: dict[str, Any],
) -> None:
    work = [dict(entry) for entry in sample_resume["workExperience"]]
    work[1]["condensed"] = True
    doc = _document({**sample_resume, "workExperience": work})
    texts = _texts(doc)

    assert "Earlier experience" in texts
    assert "Software Engineer, StartupCo, Jun 2018 - Dec 2020" in texts
    # A condensed role keeps no bullets.
    assert "Developed payment processing system handling $2M monthly" not in texts


def test_skill_rows_keep_their_labels(sample_resume: dict[str, Any]) -> None:
    data = {
        **sample_resume,
        "additional": {
            **sample_resume["additional"],
            "technicalSkills": [
                "Frontend: React, Vue",
                "---",
                "Node.js",
            ],
        },
    }

    texts = _texts(_document(data))

    assert "Technical Skills: Frontend: React, Vue" in texts
    assert "Node.js" in texts


@pytest.mark.parametrize(
    ("stored", "expected"),
    [
        ("Jan 2021 \u2013 Present", "Jan 2021 - Present"),
        ("Jan 2021-Present", "Jan 2021 - Present"),
        ("2023 2025", "2023 - 2025"),
        ("Jun 2025 Aug 2025", "Jun 2025 - Aug 2025"),
        ("2014 - 2018", "2014 - 2018"),
        ("", ""),
        (None, ""),
    ],
)
def test_date_ranges_are_normalized(stored: str | None, expected: str) -> None:
    assert format_date_range(stored) == expected


def test_group_skills_matches_the_template_rules() -> None:
    assert group_skills(["Python", "Docker"]) == [
        {"label": None, "items": ["Python", "Docker"]}
    ]
    assert group_skills(["Frontend:", "React", "Vue", "---", "Node.js"]) == [
        {"label": "Frontend", "items": ["React", "Vue"]},
        {"label": None, "items": ["Node.js"]},
    ]
    # A colon inside a skill name must not turn it into a label.
    assert group_skills(["ISO 9001:2015"]) == [
        {"label": None, "items": ["ISO 9001:2015"]}
    ]


def test_empty_data_is_not_renderable() -> None:
    assert has_renderable_content(ResumeData()) is False


def test_sample_resume_is_renderable(sample_resume: dict[str, Any]) -> None:
    assert has_renderable_content(ResumeData.model_validate(sample_resume)) is True


def test_build_accepts_the_raw_stored_dict(sample_resume: dict[str, Any]) -> None:
    doc = Document(BytesIO(build_resume_docx(sample_resume)))
    assert doc.core_properties.title == "Jane Doe"
