"""Detect the language a resume is written in.

The stored content language is a global setting, but a resume can be in another
language than the UI. Edit Mode's AI actions (enrichment, "Improve writing",
regenerate) use this heuristic to pick the output language when the user has not
made an explicit choice in Settings: an explicit ``content_language`` (or the
legacy ``language`` key) always wins.

There is no language-detection dependency, so the score is built from the text
itself: Portuguese-only characters (ã, õ, ç) and Portuguese/English stopwords.
``additional.languages`` is spoken languages, not the resume language, so it is
never part of the sample.
"""

import re
from collections.abc import Mapping
from typing import Any

from app.config_cache import explicit_content_language

#: Words that are common in Portuguese resumes but not in English ones.
_PT_WORDS = frozenset(
    {
        "não",
        "com",
        "para",
        "uma",
        "dos",
        "das",
        "pelo",
        "pela",
        "como",
        "mais",
        "também",
        "desenvolvimento",
        "experiência",
        "projetos",
        "projeto",
        "equipe",
        "usuários",
        "usuário",
        "dados",
        "sistemas",
        "sistema",
        "aplicação",
        "aplicações",
        "empresa",
        "trabalho",
        "gestão",
        "responsável",
        "atendimento",
        "melhoria",
        "implantação",
        "rotinas",
        "clientes",
        "resultados",
        "processos",
        "equipes",
        "soluções",
        "ferramentas",
        "implementação",
    }
)

#: Words that are common in English resumes but not in Portuguese ones.
_EN_WORDS = frozenset(
    {
        "the",
        "and",
        "with",
        "for",
        "was",
        "were",
        "has",
        "have",
        "this",
        "that",
        "from",
        "development",
        "experience",
        "project",
        "projects",
        "team",
        "teams",
        "system",
        "systems",
        "data",
        "application",
        "applications",
        "company",
        "work",
        "management",
        "responsible",
        "built",
        "led",
        "using",
        "clients",
        "results",
        "processes",
        "solutions",
        "tools",
        "implementation",
    }
)

_TOKEN = re.compile(r"[a-zà-ÿ]+")
_PT_STRONG_CHARS = "ãõç"
_PT_ACCENT_CHARS = "áéíóúâêôà"
#: Below this many words only a Portuguese-only character can decide.
_MIN_TOKENS = 12

#: Keys whose text is not the resume language.
_SKIPPED_KEYS = {"personalInfo", "additional", "sectionMeta", "years", "id"}


def _collect_text(value: Any, parts: list[str]) -> None:
    if isinstance(value, str):
        parts.append(value)
    elif isinstance(value, Mapping):
        for key, item in value.items():
            if key in _SKIPPED_KEYS:
                continue
            _collect_text(item, parts)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _collect_text(item, parts)


def resume_sample(data: Mapping[str, Any] | Any) -> str:
    """The resume text the detector reads: summary, bullets and custom sections."""
    parts: list[str] = []
    if hasattr(data, "model_dump"):
        data = data.model_dump()
    if isinstance(data, Mapping):
        _collect_text(data, parts)
    elif isinstance(data, str):
        parts.append(data)
    return "\n".join(parts)


def detect_language_from_text(text: str) -> str:
    """Return ``"pt"`` for Brazilian Portuguese text, otherwise ``"en"``."""
    lower = (text or "").lower()
    tokens = _TOKEN.findall(lower)
    if not tokens:
        return "en"

    pt_words = sum(1 for token in tokens if token in _PT_WORDS)
    en_words = sum(1 for token in tokens if token in _EN_WORDS)
    strong_chars = sum(lower.count(char) for char in _PT_STRONG_CHARS)
    accent_chars = sum(lower.count(char) for char in _PT_ACCENT_CHARS)

    if len(tokens) < _MIN_TOKENS:
        return "pt" if strong_chars else "en"

    pt_score = 2 * pt_words + 3 * strong_chars + accent_chars
    en_score = 2 * en_words
    return "pt" if pt_score >= 3 and pt_score > en_score else "en"


def detect_resume_language(data: Mapping[str, Any] | Any) -> str:
    """Detect the language of a whole resume's text."""
    return detect_language_from_text(resume_sample(data))


def resolve_resume_language(data: Mapping[str, Any] | Any) -> str:
    """Explicit content language first, detected resume language otherwise."""
    return explicit_content_language() or detect_resume_language(data)


def resolve_text_language(text: str) -> str:
    """Explicit content language first, detected text language otherwise."""
    return explicit_content_language() or detect_language_from_text(text)
