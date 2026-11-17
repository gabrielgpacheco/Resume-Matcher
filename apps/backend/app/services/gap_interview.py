"""Gap interview: ask about job keywords the master resume does not show.

The deterministic keyword picker already lets the user attest a skill they have;
the gap interview turns that into a short text interview. The AI writes one
neutral question per missing keyword. Answers are only recorded: a "yes" marks
the keyword as attested so the normal keyword flow can place it, and a "no"
never touches the resume.
"""

import json
import logging
from typing import Any

from app.llm import complete_json, get_llm_config, get_model_name, get_safe_max_tokens
from app.prompts.gap_interview import GAP_INTERVIEW_PROMPT
from app.prompts.templates import get_language_name
from app.services.refiner import _extract_all_text, job_keyword_terms
from app.services.text_match import keyword_in_text

logger = logging.getLogger(__name__)

#: At most this many questions in one interview.
MAX_QUESTIONS = 8

#: Persisted on the job document: {resume_id: [answer, ...]}.
ANSWERS_KEY = "gap_answers"


def missing_keywords(
    job_keywords: dict[str, Any], master_data: dict[str, Any]
) -> list[str]:
    """Job terms the master resume does not show, in posting order."""
    text = _extract_all_text(master_data).lower()
    return [
        term
        for term in job_keyword_terms(job_keywords)
        if term.strip() and not keyword_in_text(term, text)
    ]


def answered_keywords(job: dict[str, Any], resume_id: str) -> set[str]:
    """Casefolded keywords already answered for this resume and job."""
    answered: set[str] = set()
    for answer in _stored_answers(job, resume_id):
        keyword = answer.get("keyword")
        if isinstance(keyword, str) and keyword.strip():
            answered.add(keyword.strip().casefold())
    return answered


def merge_answers(
    job: dict[str, Any], resume_id: str, answers: list[dict[str, Any]]
) -> dict[str, dict[str, list[dict[str, Any]]]]:
    """Return a new ``gap_answers`` map with ``answers`` recorded for the resume.

    A later answer for the same keyword replaces the earlier one, which keeps
    the pipeline idempotent when the user reopens the interview.
    """
    stored = job.get(ANSWERS_KEY)
    merged: dict[str, list[dict[str, Any]]] = {
        key: list(value)
        for key, value in (stored.items() if isinstance(stored, dict) else [])
        if isinstance(key, str) and isinstance(value, list)
    }
    by_keyword = {
        str(answer.get("keyword", "")).strip().casefold(): answer
        for answer in merged.get(resume_id, [])
        if answer.get("keyword")
    }
    for answer in answers:
        keyword = str(answer.get("keyword", "")).strip()
        if keyword:
            by_keyword[keyword.casefold()] = answer
    merged[resume_id] = list(by_keyword.values())
    return {ANSWERS_KEY: merged}


def _stored_answers(job: dict[str, Any], resume_id: str) -> list[dict[str, Any]]:
    stored = job.get(ANSWERS_KEY)
    if not isinstance(stored, dict):
        return []
    entries = stored.get(resume_id)
    if not isinstance(entries, list):
        return []
    return [entry for entry in entries if isinstance(entry, dict)]


def _validate_questions(result: dict[str, Any]) -> dict[str, Any]:
    questions = result.get("questions")
    if not isinstance(questions, list):
        raise ValueError("Gap interview response is missing a 'questions' list")
    for question in questions:
        if not isinstance(question, dict):
            raise ValueError("Each question must be an object")
        if not question.get("keyword") or not question.get("question"):
            raise ValueError("Each question needs 'keyword' and 'question'")
    return result


async def generate_gap_questions(
    master_data: dict[str, Any],
    gaps: list[str],
    language: str,
) -> list[dict[str, str]]:
    """One neutral question per gap keyword, in the content language."""
    if not gaps:
        return []

    prompt = GAP_INTERVIEW_PROMPT.format(
        keywords="\n".join(f"- {keyword}" for keyword in gaps[:MAX_QUESTIONS]),
        resume=json.dumps(
            {"summary": master_data.get("summary", "")}, ensure_ascii=False
        )[:2000],
        output_language=get_language_name(language),
    )
    config = get_llm_config()
    result = await complete_json(
        prompt=prompt,
        system_prompt="You are a careful career coach. Output only valid JSON.",
        max_tokens=get_safe_max_tokens(get_model_name(config), config=config),
        schema_type="gap_interview",
        response_validator=_validate_questions,
    )

    # Keep only questions about keywords we asked about, one per keyword.
    asked = {keyword.casefold(): keyword for keyword in gaps}
    questions: list[dict[str, str]] = []
    seen: set[str] = set()
    for question in result["questions"]:
        keyword = str(question.get("keyword", "")).strip()
        key = keyword.casefold()
        if key not in asked or key in seen:
            continue
        seen.add(key)
        questions.append(
            {
                "keyword": asked[key],
                "question": str(question.get("question", "")).strip(),
                "context": str(question.get("context") or "").strip(),
            }
        )
        if len(questions) >= MAX_QUESTIONS:
            break
    return questions
