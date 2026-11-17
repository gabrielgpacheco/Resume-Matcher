"""POST /resumes/{resume_id}/gap-interview and /gap-answers.

Real router and a real temp database; the LLM boundary is mocked.
"""

import copy
from typing import Any
from unittest.mock import AsyncMock, patch

from httpx import ASGITransport, AsyncClient

from app.main import app
from app.routers.resumes import _hash_job_content

JOB_KEYWORDS: dict[str, Any] = {
    "required_skills": ["Python", "Kubernetes"],
    "preferred_skills": ["WordPress"],
    "keywords": [],
}
JOB_CONTENT = (
    "Platform engineer. Python, Kubernetes and WordPress. "
    "Run the container platform for every product team."
)


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _master(isolated_db: Any, sample_resume: dict[str, Any]) -> str:
    resume = await isolated_db.create_resume_atomic_master(
        content="# Jane Doe\n",
        processed_data=copy.deepcopy(sample_resume),
        processing_status="ready",
    )
    return resume["resume_id"]


async def _job_with_keywords(isolated_db: Any) -> str:
    job = await isolated_db.create_job(JOB_CONTENT)
    await isolated_db.update_job(
        job["job_id"],
        {
            "job_keywords": copy.deepcopy(JOB_KEYWORDS),
            "job_keywords_hash": _hash_job_content(JOB_CONTENT),
        },
    )
    return job["job_id"]


def _questions(*keywords: str) -> dict[str, Any]:
    return {
        "questions": [
            {
                "keyword": keyword,
                "question": f"Have you used {keyword}?",
                "context": "The posting asks for it.",
            }
            for keyword in keywords
        ]
    }


async def test_interview_asks_about_the_keywords_the_master_lacks(
    isolated_db: Any, sample_resume: dict[str, Any]
) -> None:
    resume_id = await _master(isolated_db, sample_resume)
    job_id = await _job_with_keywords(isolated_db)
    llm = AsyncMock(return_value=_questions("Kubernetes", "WordPress"))

    with patch("app.services.gap_interview.complete_json", llm):
        async with _client() as client:
            resp = await client.post(
                f"/api/v1/resumes/{resume_id}/gap-interview",
                json={"job_id": job_id},
            )

    assert resp.status_code == 200, resp.text
    assert [q["keyword"] for q in resp.json()["questions"]] == [
        "Kubernetes",
        "WordPress",
    ]
    # Python is already in the master, so it is not asked about.
    prompt = llm.await_args.kwargs["prompt"]
    assert "- Kubernetes" in prompt and "- WordPress" in prompt
    assert "- Python" not in prompt


async def test_no_gaps_returns_no_questions_without_an_llm_call(
    isolated_db: Any, sample_resume: dict[str, Any]
) -> None:
    resume_id = await _master(isolated_db, sample_resume)
    job = await isolated_db.create_job(JOB_CONTENT)
    keywords = {"required_skills": ["Python"], "preferred_skills": [], "keywords": []}
    await isolated_db.update_job(
        job["job_id"],
        {"job_keywords": keywords, "job_keywords_hash": _hash_job_content(JOB_CONTENT)},
    )
    llm = AsyncMock()

    with patch("app.services.gap_interview.complete_json", llm):
        async with _client() as client:
            resp = await client.post(
                f"/api/v1/resumes/{resume_id}/gap-interview",
                json={"job_id": job["job_id"]},
            )

    assert resp.status_code == 200, resp.text
    assert resp.json()["questions"] == []
    llm.assert_not_awaited()


async def test_answers_are_recorded_and_the_question_is_not_repeated(
    isolated_db: Any, sample_resume: dict[str, Any]
) -> None:
    resume_id = await _master(isolated_db, sample_resume)
    job_id = await _job_with_keywords(isolated_db)

    async with _client() as client:
        recorded = await client.post(
            f"/api/v1/resumes/{resume_id}/gap-answers",
            json={
                "job_id": job_id,
                "answers": [
                    {"keyword": "Kubernetes", "have_it": True, "detail": "EKS"},
                    {"keyword": "WordPress", "have_it": False},
                ],
            },
        )
    assert recorded.status_code == 200, recorded.text
    body = recorded.json()
    assert body["attested"] == ["Kubernetes"]
    assert body["results"] == [
        {"keyword": "Kubernetes", "have_it": True},
        {"keyword": "WordPress", "have_it": False},
    ]

    job = await isolated_db.get_job(job_id)
    assert job["gap_answers"][resume_id] == [
        {"keyword": "Kubernetes", "have_it": True, "detail": "EKS"},
        {"keyword": "WordPress", "have_it": False, "detail": None},
    ]

    llm = AsyncMock(return_value=_questions("WordPress"))
    with patch("app.services.gap_interview.complete_json", llm):
        async with _client() as client:
            asked = await client.post(
                f"/api/v1/resumes/{resume_id}/gap-interview", json={"job_id": job_id}
            )
    # Both keywords were answered, so there is nothing left to ask.
    assert asked.json()["questions"] == []
    llm.assert_not_awaited()


async def test_a_no_answer_leaves_the_master_resume_untouched(
    isolated_db: Any, sample_resume: dict[str, Any]
) -> None:
    resume_id = await _master(isolated_db, sample_resume)
    job_id = await _job_with_keywords(isolated_db)

    async with _client() as client:
        await client.post(
            f"/api/v1/resumes/{resume_id}/gap-answers",
            json={
                "job_id": job_id,
                "answers": [{"keyword": "Kubernetes", "have_it": False}],
            },
        )

    master = await isolated_db.get_resume(resume_id)
    assert master["processed_data"] == sample_resume


async def test_a_reopened_interview_updates_the_same_answer(
    isolated_db: Any, sample_resume: dict[str, Any]
) -> None:
    resume_id = await _master(isolated_db, sample_resume)
    job_id = await _job_with_keywords(isolated_db)
    payload = {
        "job_id": job_id,
        "answers": [{"keyword": "Kubernetes", "have_it": False}],
    }

    async with _client() as client:
        await client.post(f"/api/v1/resumes/{resume_id}/gap-answers", json=payload)
        payload["answers"][0]["have_it"] = True
        resp = await client.post(
            f"/api/v1/resumes/{resume_id}/gap-answers", json=payload
        )

    assert resp.json()["attested"] == ["Kubernetes"]
    job = await isolated_db.get_job(job_id)
    assert job["gap_answers"][resume_id] == [
        {"keyword": "Kubernetes", "have_it": True, "detail": None}
    ]


async def test_a_keyword_outside_the_job_is_refused(
    isolated_db: Any, sample_resume: dict[str, Any]
) -> None:
    resume_id = await _master(isolated_db, sample_resume)
    job_id = await _job_with_keywords(isolated_db)

    async with _client() as client:
        resp = await client.post(
            f"/api/v1/resumes/{resume_id}/gap-answers",
            json={"job_id": job_id, "answers": [{"keyword": "Rust", "have_it": True}]},
        )
    assert resp.status_code == 400


async def test_a_job_without_keywords_is_refused(
    isolated_db: Any, sample_resume: dict[str, Any]
) -> None:
    resume_id = await _master(isolated_db, sample_resume)
    job = await isolated_db.create_job(JOB_CONTENT)

    async with _client() as client:
        resp = await client.post(
            f"/api/v1/resumes/{resume_id}/gap-interview", json={"job_id": job["job_id"]}
        )
    assert resp.status_code == 409


async def test_an_unknown_resume_is_refused(
    isolated_db: Any, sample_resume: dict[str, Any]
) -> None:
    job_id = await _job_with_keywords(isolated_db)

    async with _client() as client:
        resp = await client.post(
            "/api/v1/resumes/missing/gap-interview", json={"job_id": job_id}
        )
    assert resp.status_code == 404
