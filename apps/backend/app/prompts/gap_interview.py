"""Prompt for the gap interview: turn missing job keywords into questions."""

GAP_INTERVIEW_PROMPT = """You are a career coach helping a candidate work out whether skills a job posting asks for are part of their real experience.

The candidate's master resume does NOT mention these job keywords:
{keywords}

Candidate's resume summary (context only, so questions stay grounded):
{resume}

For each keyword, write ONE short, neutral question in {output_language} that asks whether the candidate has used it, plus a one-line note on why the keyword matters for this role. Never suggest the answer, never assume the candidate has the skill, and never invent experience.

Output ONLY a JSON object with a "questions" array:
{{"questions": [{{"keyword": "<exact keyword from the list>", "question": "<short question>", "context": "<one-line why-it-matters note>"}}]}}

Rules:
- One entry per keyword, using the keyword exactly as listed.
- Question must be answerable with a simple yes/no.
- Keep every string in {output_language}.
"""
