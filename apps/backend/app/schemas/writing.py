"""Schemas for the writing-quality critique, the rewrite loop and keyword forcing."""

from pydantic import BaseModel, Field

from app.schemas.models import ResumeData
from app.schemas.writing_report import (
    CriticNote,
    KeywordPlacement,
    WritingFinding,
    WritingReport,
    WritingRule,
)

__all__ = [
    "ApplyKeywordsRequest",
    "CriticNote",
    "ForcedKeyword",
    "GapAnswer",
    "GapAnswerResult",
    "GapAnswersRequest",
    "GapAnswersResponse",
    "GapInterviewRequest",
    "GapInterviewResponse",
    "GapQuestion",
    "KeywordPlacement",
    "WritingChange",
    "WritingCheckRequest",
    "WritingFinding",
    "WritingImproveRequest",
    "WritingImproveResponse",
    "WritingReport",
    "WritingRule",
]


class WritingCheckRequest(BaseModel):
    resume_data: ResumeData


class WritingImproveRequest(BaseModel):
    resume_data: ResumeData
    progress_id: str | None = Field(
        default=None, max_length=64, pattern=r"^[A-Za-z0-9_-]+$"
    )


class WritingChange(BaseModel):
    path: str
    before: str
    after: str


class WritingImproveResponse(BaseModel):
    improved_data: ResumeData
    writing: WritingReport
    changes: list[WritingChange] = Field(default_factory=list)


class ForcedKeyword(BaseModel):
    keyword: str = Field(min_length=1, max_length=80)
    # True when the user confirmed "I have this" for a keyword the master lacks.
    attested: bool = False


class ApplyKeywordsRequest(BaseModel):
    resume_id: str
    job_id: str
    preview_id: str
    improved_data: ResumeData
    keywords: list[ForcedKeyword] = Field(min_length=1, max_length=30)
    prompt_id: str | None = None


class GapQuestion(BaseModel):
    """One interview question about a missing job keyword."""

    keyword: str = Field(min_length=1, max_length=80)
    question: str = Field(min_length=1, max_length=400)
    context: str = Field(default="", max_length=400)


class GapInterviewRequest(BaseModel):
    """Generate interview questions for a resume's missing job keywords."""

    job_id: str


class GapInterviewResponse(BaseModel):
    questions: list[GapQuestion] = Field(default_factory=list)


class GapAnswer(BaseModel):
    """A user's answer to a gap-interview question."""

    keyword: str = Field(min_length=1, max_length=80)
    # True when the user confirmed "I have this" for a keyword the master lacks.
    have_it: bool = False
    # Optional free text: where the user used it. Not yet used to write bullets.
    detail: str | None = Field(default=None, max_length=600)


class GapAnswersRequest(BaseModel):
    job_id: str
    answers: list[GapAnswer] = Field(min_length=1, max_length=30)


class GapAnswerResult(BaseModel):
    """What the answer recorded; the UI turns "no" into a study suggestion."""

    keyword: str
    have_it: bool = False


class GapAnswersResponse(BaseModel):
    results: list[GapAnswerResult] = Field(default_factory=list)
    # Keywords the user confirmed: safe to attest when they are applied.
    attested: list[str] = Field(default_factory=list)
