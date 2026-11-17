"""Unit tests for the gap interview service (no HTTP, no real LLM)."""

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from app.services.gap_interview import (
    MAX_QUESTIONS,
    _validate_questions,
    answered_keywords,
    generate_gap_questions,
    merge_answers,
    missing_keywords,
)

JOB_KEYWORDS: dict[str, Any] = {
    "required_skills": ["Python", "Kubernetes", "WordPress"],
    "preferred_skills": ["PHP"],
    "keywords": ["WooCommerce"],
}


def test_missing_keywords_follows_posting_order(
    sample_resume: dict[str, Any],
) -> None:
    # The sample resume shows Python; the other job terms are missing.
    assert missing_keywords(JOB_KEYWORDS, sample_resume) == [
        "Kubernetes",
        "WordPress",
        "PHP",
        "WooCommerce",
    ]


@pytest.mark.parametrize(
    ("term", "expected"),
    [
        ("Java", ["Java"]),  # JavaScript in the resume must not satisfy Java
        ("JavaScript", []),  # exact skill already present
        ("python", []),  # case-insensitive
    ],
)
def test_missing_keywords_uses_whole_term_matching(
    sample_resume: dict[str, Any], term: str, expected: list[str]
) -> None:
    resume = {
        **sample_resume,
        "additional": {
            **sample_resume["additional"],
            "technicalSkills": [
                *sample_resume["additional"]["technicalSkills"],
                "JavaScript",
            ],
        },
    }
    keywords = {"required_skills": [term], "preferred_skills": [], "keywords": []}
    assert missing_keywords(keywords, resume) == expected


def test_answered_keywords_is_case_insensitive() -> None:
    job = {
        "gap_answers": {
            "resume-1": [
                {"keyword": "Kubernetes", "have_it": True},
                {"keyword": "WordPress", "have_it": False},
            ],
            "resume-2": [{"keyword": "PHP", "have_it": True}],
        }
    }
    assert answered_keywords(job, "resume-1") == {"kubernetes", "wordpress"}
    assert answered_keywords(job, "resume-2") == {"php"}
    assert answered_keywords(job, "resume-3") == set()


def test_answered_keywords_ignores_malformed_storage() -> None:
    assert answered_keywords({"gap_answers": "nope"}, "resume-1") == set()
    assert answered_keywords({"gap_answers": {"resume-1": "nope"}}, "resume-1") == set()
    assert answered_keywords({}, "resume-1") == set()


def test_merge_answers_replaces_the_same_keyword_and_keeps_other_resumes() -> None:
    job = {
        "gap_answers": {
            "resume-1": [{"keyword": "Kubernetes", "have_it": True, "detail": "k8s"}],
            "resume-2": [{"keyword": "PHP", "have_it": True, "detail": None}],
        }
    }
    updated = merge_answers(
        job,
        "resume-1",
        [
            {"keyword": "kubernetes", "have_it": False, "detail": None},
            {"keyword": "WordPress", "have_it": True, "detail": "sites"},
        ],
    )

    stored = updated["gap_answers"]
    assert stored["resume-2"] == [{"keyword": "PHP", "have_it": True, "detail": None}]
    # The later answer for Kubernetes replaces the earlier one.
    assert stored["resume-1"] == [
        {"keyword": "kubernetes", "have_it": False, "detail": None},
        {"keyword": "WordPress", "have_it": True, "detail": "sites"},
    ]


async def test_generate_gap_questions_keeps_only_asked_keywords(
    sample_resume: dict[str, Any],
) -> None:
    llm = AsyncMock(
        return_value={
            "questions": [
                {
                    "keyword": "kubernetes",
                    "question": "Have you used Kubernetes?",
                    "context": "Runs the platform",
                },
                {
                    "keyword": "kubernetes",
                    "question": "Duplicate entry",
                    "context": "",
                },
                {
                    "keyword": "Rust",
                    "question": "Not part of the posting",
                    "context": "",
                },
            ]
        }
    )
    with patch("app.services.gap_interview.complete_json", llm):
        questions = await generate_gap_questions(
            sample_resume, ["Kubernetes", "WordPress"], "en"
        )

    assert questions == [
        {
            "keyword": "Kubernetes",
            "question": "Have you used Kubernetes?",
            "context": "Runs the platform",
        }
    ]
    prompt = llm.await_args.kwargs["prompt"]
    assert "- Kubernetes" in prompt and "- WordPress" in prompt
    assert llm.await_args.kwargs["schema_type"] == "gap_interview"


async def test_generate_gap_questions_without_gaps_skips_the_llm(
    sample_resume: dict[str, Any],
) -> None:
    llm = AsyncMock()
    with patch("app.services.gap_interview.complete_json", llm):
        assert await generate_gap_questions(sample_resume, [], "en") == []
    llm.assert_not_awaited()


async def test_generate_gap_questions_caps_the_interview(
    sample_resume: dict[str, Any],
) -> None:
    gaps = [f"Skill {i}" for i in range(MAX_QUESTIONS + 4)]
    llm = AsyncMock(
        return_value={
            "questions": [
                {"keyword": gap, "question": f"Used {gap}?", "context": ""}
                for gap in gaps
            ]
        }
    )
    with patch("app.services.gap_interview.complete_json", llm):
        questions = await generate_gap_questions(sample_resume, gaps, "en")

    assert [q["keyword"] for q in questions] == gaps[:MAX_QUESTIONS]


def test_validate_questions_rejects_a_malformed_response() -> None:
    with pytest.raises(ValueError):
        _validate_questions({"questions": "nope"})
    with pytest.raises(ValueError):
        _validate_questions({"questions": [{"keyword": "PHP"}]})
    assert _validate_questions({"questions": []}) == {"questions": []}
