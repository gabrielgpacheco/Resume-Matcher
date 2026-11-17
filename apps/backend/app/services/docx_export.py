"""Render structured resume data as an ATS-friendly Word document.

The .docx export mirrors what the print templates show, but in the shape applicant
tracking systems read best: one column, no tables, no text boxes, real paragraphs
and headings. Section order and visibility come from ``sectionMeta``; each
description line respects its ``descriptionStyles`` entry (``bullet`` or
``plain``) and inline formatting (bold/italic/underline) is kept as Word runs.
"""

import re
from html.parser import HTMLParser
from io import BytesIO
from typing import Any, Iterable

from docx import Document
from docx.document import Document as DocxDocument
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
from docx.shared import Cm, Pt, RGBColor

from app.schemas.models import (
    DEFAULT_SECTION_META,
    CustomSection,
    Education,
    Experience,
    Project,
    ResumeData,
    SectionMeta,
    SectionType,
)

#: MIME type for .docx downloads (also used by the router).
DOCX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)

BODY_FONT = "Calibri"
BODY_SIZE = Pt(10.5)
NAME_SIZE = Pt(20)
TITLE_SIZE = Pt(11)
SECTION_HEADING_SIZE = Pt(12)
META_SIZE = Pt(10)
CONTACT_SIZE = Pt(9.5)
SECTION_SPACING = Pt(10)
EARLIER_EXPERIENCE_LABEL = "Earlier experience"
SKILL_ROW_BREAK = "---"

#: Lines like "Frontend: React, Vue". Label has no comma/colon/whitespace.
_LABELED_SKILL_LINE = re.compile(r"^([^,:：\s]{1,40})(?::(?:\s+(.*))?|：\s*(.*))$")
_OPEN_BRACKETS = "([（[【"
_CLOSE_BRACKETS = ")]）]】"
_COMMA_CHARS = ",，、"
_DATE_DASHES = str.maketrans(
    {"\u2012": "-", "\u2013": "-", "\u2014": "-", "\u2015": "-"}
)
_MONTH_YEAR_PAIR = re.compile(
    r"(?<![A-Za-z])([A-Za-z]+\.?\s+\d{4})\s+([A-Za-z]+\.?\s+\d{4})"
)
_YEAR_PAIR = re.compile(r"(\d{4})\s+(\d{4})")
_MONTH_YEAR_TO_PRESENT = re.compile(
    r"(?<![a-z])([a-z]+\.?\s+\d{4})\s+(Present|Current|Now|Ongoing|Atual)",
    re.IGNORECASE,
)

#: English month names and abbreviations to Brazilian Portuguese.
_PT_MONTHS = {
    "january": "janeiro",
    "february": "fevereiro",
    "march": "março",
    "april": "abril",
    "may": "maio",
    "june": "junho",
    "july": "julho",
    "august": "agosto",
    "september": "setembro",
    "october": "outubro",
    "november": "novembro",
    "december": "dezembro",
    "jan": "jan",
    "feb": "fev",
    "mar": "mar",
    "apr": "abr",
    "jun": "jun",
    "jul": "jul",
    "aug": "ago",
    "sep": "set",
    "sept": "set",
    "oct": "out",
    "nov": "nov",
    "dec": "dez",
}
_PT_PRESENT = "Atual"


def _localize_pt_br(text: str) -> str:
    """Translate the date words to Brazilian Portuguese, keeping the layout."""

    def month(match: re.Match[str]) -> str:
        return _PT_MONTHS.get(match.group(0).lower().rstrip("."), match.group(0))

    localized = re.sub(
        r"(?<![A-Za-z])(" + "|".join(_PT_MONTHS) + r")\.?(?![A-Za-z])",
        month,
        text,
        flags=re.IGNORECASE,
    )
    return re.sub(
        r"(?<![A-Za-z])(Present|Current|Now|Ongoing|Atual)(?![A-Za-z])",
        _PT_PRESENT,
        localized,
        flags=re.IGNORECASE,
    )


def format_date_range(value: str | None, language: str = "en") -> str:
    """Normalize a stored date range the way the print templates do.

    Any dash becomes ``-``, spacing is normalized, and two dates written without
    a separator ("2024 2025", "Jun 2025 Present") get one. ATS parsers expect a
    consistent range. ``language="pt"`` also translates the month names and
    "Present" to Brazilian Portuguese ("jan 2021 - Atual").
    """
    if not value:
        return ""

    text = value.translate(_DATE_DASHES)
    segments = text.split("-")
    normalized: list[str] = []
    for index, segment in enumerate(segments):
        start = segment.lstrip() if index > 0 else segment
        normalized.append(start.rstrip() if index < len(segments) - 1 else start)
    text = " - ".join(normalized)

    text = _MONTH_YEAR_PAIR.sub(r"\1 - \2", text)
    text = _YEAR_PAIR.sub(r"\1 - \2", text)
    text = _MONTH_YEAR_TO_PRESENT.sub(r"\1 - \2", text)
    text = text.strip()
    return _localize_pt_br(text) if language.lower().startswith("pt") else text


class _InlineHtmlParser(HTMLParser):
    """Collect text spans with the inline formatting the builder can produce."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.spans: list[tuple[str, bool, bool, bool]] = []
        self._bold = 0
        self._italic = 0
        self._underline = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in {"strong", "b"}:
            self._bold += 1
        elif tag in {"em", "i"}:
            self._italic += 1
        elif tag == "u":
            self._underline += 1
        elif tag == "br":
            self._emit("\n")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "br":
            self._emit("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"strong", "b"}:
            self._bold = max(0, self._bold - 1)
        elif tag in {"em", "i"}:
            self._italic = max(0, self._italic - 1)
        elif tag == "u":
            self._underline = max(0, self._underline - 1)

    def handle_data(self, data: str) -> None:
        self._emit(data)

    def _emit(self, text: str) -> None:
        normalized = text.replace("\xa0", " ")
        if normalized:
            self.spans.append(
                (normalized, self._bold > 0, self._italic > 0, self._underline > 0)
            )


def _add_rich_text(paragraph: Any, text: str) -> None:
    """Add ``text`` to a paragraph, turning inline HTML into formatted runs."""
    if not text:
        return
    if "<" not in text and "&" not in text:
        paragraph.add_run(text.replace("\xa0", " "))
        return

    parser = _InlineHtmlParser()
    parser.feed(text)
    parser.close()
    for chunk, bold, italic, underline in parser.spans:
        run = paragraph.add_run(chunk)
        run.bold = bold
        run.italic = italic
        run.underline = underline


def _flatten_files(items: Iterable[Any]) -> list[str]:
    return [text for item in items if (text := str(item).strip())]


# --- Skill rows (port of lib/utils/skill-groups.ts) -------------------------


def _split_skills(text: str) -> list[str]:
    items: list[str] = []
    depth = 0
    start = 0
    for index, char in enumerate(text):
        if char in _OPEN_BRACKETS:
            depth += 1
        elif char in _CLOSE_BRACKETS and depth > 0:
            depth -= 1
        elif char in _COMMA_CHARS and depth == 0:
            items.append(text[start:index])
            start = index + 1
    items.append(text[start:])
    return [item.strip() for item in items if item.strip()]


def group_skills(lines: Iterable[str]) -> list[dict[str, Any]]:
    """Group ``technicalSkills`` lines into labeled rows.

    "Label: a, b" starts a row, "---" closes the current one, and any other line
    is one skill in the open (unlabeled) row. Mirrors the print templates so the
    .docx and the PDF show the same grouping.
    """
    rows: list[dict[str, Any]] = []
    open_row: dict[str, Any] | None = None
    for raw in lines:
        line = str(raw).strip() if isinstance(raw, str) else ""
        if not line:
            continue
        if line == SKILL_ROW_BREAK:
            open_row = None
            continue
        match = _LABELED_SKILL_LINE.match(line)
        if match and match.group(1).strip():
            row = {
                "label": match.group(1).strip(),
                "items": _split_skills(match.group(2) or match.group(3) or ""),
            }
            rows.append(row)
            open_row = row if not row["items"] else None
            continue
        if open_row is None:
            open_row = {"label": None, "items": []}
            rows.append(open_row)
        open_row["items"].append(line)
    return [row for row in rows if row["items"]]


# --- Document setup ---------------------------------------------------------


def _setup_document() -> DocxDocument:
    doc = Document()
    section = doc.sections[0]
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(1.8)
    section.bottom_margin = Cm(1.8)
    section.left_margin = Cm(1.8)
    section.right_margin = Cm(1.8)

    normal = doc.styles["Normal"]
    normal.font.name = BODY_FONT
    normal.font.size = BODY_SIZE
    normal.font.color.rgb = RGBColor(0, 0, 0)
    normal.paragraph_format.space_before = Pt(0)
    normal.paragraph_format.space_after = Pt(2)
    normal.paragraph_format.line_spacing = 1.05

    heading = doc.styles["Heading 1"]
    heading.font.name = BODY_FONT
    heading.font.size = SECTION_HEADING_SIZE
    heading.font.bold = True
    heading.font.color.rgb = RGBColor(0, 0, 0)
    heading.paragraph_format.space_before = SECTION_SPACING
    heading.paragraph_format.space_after = Pt(3)
    heading.paragraph_format.keep_with_next = True
    return doc


def _content_width(doc: DocxDocument) -> Any:
    section = doc.sections[0]
    return section.page_width - section.left_margin - section.right_margin


def _add_section_heading(doc: DocxDocument, title: str) -> None:
    if not title.strip():
        return
    paragraph = doc.add_paragraph(title.strip(), style="Heading 1")
    paragraph.paragraph_format.keep_with_next = True


def _add_two_column_line(
    doc: DocxDocument, left: str, right: str, *, bold: bool = False
) -> None:
    if not left and not right:
        return
    paragraph = doc.add_paragraph()
    paragraph.paragraph_format.space_after = Pt(0)
    if left:
        run = paragraph.add_run(left)
        run.bold = bold
    if left and right:
        paragraph.paragraph_format.tab_stops.add_tab_stop(
            _content_width(doc), WD_TAB_ALIGNMENT.RIGHT
        )
        paragraph.add_run("\t")
        paragraph.add_run(right)
    elif right:
        paragraph.add_run(right)


def _add_entry_header(
    doc: DocxDocument, title: str, meta: str, *, bold: bool = True
) -> None:
    if not title and not meta:
        return
    paragraph = doc.add_paragraph()
    paragraph.paragraph_format.space_before = Pt(5)
    paragraph.paragraph_format.space_after = Pt(0)
    paragraph.paragraph_format.keep_with_next = True
    if title:
        run = paragraph.add_run(title)
        run.bold = bold
    if meta:
        if title:
            paragraph.paragraph_format.tab_stops.add_tab_stop(
                _content_width(doc), WD_TAB_ALIGNMENT.RIGHT
            )
            paragraph.add_run("\t")
        paragraph.add_run(meta)


def _add_description(
    doc: DocxDocument, items: Iterable[str], styles: Iterable[str] | None
) -> None:
    style_list = list(styles or [])
    for index, item in enumerate(items):
        text = str(item).strip()
        if not text:
            continue
        is_bullet = index >= len(style_list) or style_list[index] != "plain"
        paragraph = doc.add_paragraph(style="List Bullet" if is_bullet else None)
        paragraph.paragraph_format.space_before = Pt(0)
        paragraph.paragraph_format.space_after = Pt(0)
        _add_rich_text(paragraph, text)


# --- Sections ---------------------------------------------------------------


def _render_summary(doc: DocxDocument, resume: ResumeData, heading: str) -> None:
    if not resume.summary.strip():
        return
    _add_section_heading(doc, heading)
    paragraph = doc.add_paragraph()
    _add_rich_text(paragraph, resume.summary.strip())


def _render_experience(
    doc: DocxDocument, resume: ResumeData, heading: str, language: str = "en"
) -> None:
    full = [entry for entry in resume.workExperience if not entry.condensed]
    condensed = [entry for entry in resume.workExperience if entry.condensed]
    if not full and not condensed:
        return

    _add_section_heading(doc, heading)
    for entry in full:
        _render_experience_entry(doc, entry, language)
    if condensed:
        subheading = doc.add_paragraph()
        subheading.paragraph_format.space_before = Pt(5)
        subheading.paragraph_format.space_after = Pt(0)
        subheading.paragraph_format.keep_with_next = True
        run = subheading.add_run(EARLIER_EXPERIENCE_LABEL)
        run.bold = True
        for entry in condensed:
            line = ", ".join(
                part
                for part in (
                    entry.title.strip(),
                    entry.company.strip(),
                    format_date_range(entry.years, language),
                )
                if part
            )
            if line:
                paragraph = doc.add_paragraph()
                paragraph.paragraph_format.space_after = Pt(0)
                paragraph.add_run(line)


def _render_experience_entry(
    doc: DocxDocument, entry: Experience, language: str = "en"
) -> None:
    _add_entry_header(
        doc, entry.title.strip(), format_date_range(entry.years, language)
    )
    if entry.company.strip() or entry.location:
        _add_two_column_line(doc, entry.company.strip(), (entry.location or "").strip())
    _add_description(doc, entry.description, entry.descriptionStyles)


def _render_education(
    doc: DocxDocument, resume: ResumeData, heading: str, language: str = "en"
) -> None:
    if not resume.education:
        return
    _add_section_heading(doc, heading)
    for entry in resume.education:
        _render_education_entry(doc, entry, language)


def _render_education_entry(
    doc: DocxDocument, entry: Education, language: str = "en"
) -> None:
    _add_entry_header(
        doc,
        entry.institution.strip(),
        format_date_range(entry.years, language),
    )
    if entry.degree.strip():
        paragraph = doc.add_paragraph()
        paragraph.paragraph_format.space_after = Pt(0)
        paragraph.add_run(entry.degree.strip())
    if entry.description:
        paragraph = doc.add_paragraph()
        _add_rich_text(paragraph, entry.description.strip())


def _link_label(url: str) -> str:
    label = re.sub(r"^https?://", "", url.strip())
    label = re.sub(r"^www\.", "", label)
    return label.rstrip("/")


def _render_projects(
    doc: DocxDocument, resume: ResumeData, heading: str, language: str = "en"
) -> None:
    if not resume.personalProjects:
        return
    _add_section_heading(doc, heading)
    for project in resume.personalProjects:
        _render_project_entry(doc, project, language)


def _render_project_entry(
    doc: DocxDocument, project: Project, language: str = "en"
) -> None:
    links = [_link_label(link) for link in (project.github, project.website) if link]
    links = [link for link in links if link]

    paragraph = doc.add_paragraph()
    paragraph.paragraph_format.space_before = Pt(5)
    paragraph.paragraph_format.space_after = Pt(0)
    paragraph.paragraph_format.keep_with_next = True
    if project.name.strip():
        paragraph.add_run(project.name.strip()).bold = True
    if links:
        paragraph.add_run("  " + " | ".join(links))
    years = format_date_range(project.years, language)
    if years:
        paragraph.paragraph_format.tab_stops.add_tab_stop(
            _content_width(doc), WD_TAB_ALIGNMENT.RIGHT
        )
        paragraph.add_run("\t")
        paragraph.add_run(years)
    if project.role.strip():
        role_line = doc.add_paragraph()
        role_line.paragraph_format.space_after = Pt(0)
        role_line.add_run(project.role.strip())
    _add_description(doc, project.description, project.descriptionStyles)


def _render_additional(doc: DocxDocument, resume: ResumeData, heading: str) -> None:
    additional = resume.additional
    skill_rows = group_skills(additional.technicalSkills)
    languages = _flatten_files(additional.languages)
    certifications = _flatten_files(additional.certificationsTraining)
    awards = _flatten_files(additional.awards)
    if not (skill_rows or languages or certifications or awards):
        return

    _add_section_heading(doc, heading)
    for index, row in enumerate(skill_rows):
        paragraph = doc.add_paragraph()
        paragraph.paragraph_format.space_after = Pt(0)
        if index == 0:
            paragraph.add_run("Technical Skills: ").bold = True
        if row["label"]:
            paragraph.add_run(f"{row['label']}: ").bold = True
        paragraph.add_run(", ".join(row["items"]))

    for label, values in (
        ("Languages", languages),
        ("Certifications", certifications),
        ("Awards", awards),
    ):
        if not values:
            continue
        paragraph = doc.add_paragraph()
        paragraph.paragraph_format.space_after = Pt(0)
        paragraph.add_run(f"{label}: ").bold = True
        paragraph.add_run(", ".join(values))


def _custom_has_content(section_type: SectionType, data: CustomSection) -> bool:
    if section_type is SectionType.TEXT:
        return bool((data.text or "").strip())
    if section_type is SectionType.ITEM_LIST:
        return bool(data.items)
    if section_type is SectionType.STRING_LIST:
        return bool(_flatten_files(data.strings or []))
    return False


def _render_custom_section(
    doc: DocxDocument,
    section: SectionMeta,
    data: CustomSection,
    heading: str,
    language: str = "en",
) -> None:
    if not _custom_has_content(section.sectionType, data):
        return
    _add_section_heading(doc, heading)
    if section.sectionType is SectionType.TEXT:
        paragraph = doc.add_paragraph()
        _add_rich_text(paragraph, (data.text or "").strip())
        return
    if section.sectionType is SectionType.STRING_LIST:
        paragraph = doc.add_paragraph()
        paragraph.add_run(", ".join(_flatten_files(data.strings or [])))
        return
    for item in data.items or []:
        _add_entry_header(
            doc,
            (item.title or "").strip(),
            format_date_range(item.years, language),
        )
        if (item.subtitle or "").strip() or (item.location or "").strip():
            _add_two_column_line(
                doc,
                (item.subtitle or "").strip(),
                (item.location or "").strip(),
            )
        _add_description(doc, item.description, item.descriptionStyles)


def _section_meta(resume: ResumeData) -> list[SectionMeta]:
    sections = resume.sectionMeta
    if not sections:
        sections = [SectionMeta.model_validate(item) for item in DEFAULT_SECTION_META]
    return sorted(
        (section for section in sections if section.isVisible),
        key=lambda section: section.order,
    )


def _default_display_name(key: str) -> str:
    for item in DEFAULT_SECTION_META:
        if item["key"] == key:
            return str(item["displayName"])
    return key


def _render_section(
    doc: DocxDocument,
    resume: ResumeData,
    section: SectionMeta,
    language: str = "en",
) -> None:
    title = section.displayName.strip() or _default_display_name(section.key)
    if section.key == "summary":
        _render_summary(doc, resume, title)
    elif section.key == "workExperience":
        _render_experience(doc, resume, title, language)
    elif section.key == "education":
        _render_education(doc, resume, title, language)
    elif section.key == "personalProjects":
        _render_projects(doc, resume, title, language)
    elif section.key == "additional":
        _render_additional(doc, resume, title)
    elif not section.isDefault:
        custom = resume.customSections.get(section.key)
        if custom is not None:
            _render_custom_section(doc, section, custom, title, language)


def _render_header(doc: DocxDocument, resume: ResumeData) -> None:
    personal = resume.personalInfo
    if personal.name.strip():
        paragraph = doc.add_paragraph()
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        paragraph.paragraph_format.space_after = Pt(0)
        run = paragraph.add_run(personal.name.strip())
        run.bold = True
        run.font.size = NAME_SIZE
    if personal.title.strip():
        paragraph = doc.add_paragraph()
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        paragraph.paragraph_format.space_after = Pt(0)
        run = paragraph.add_run(personal.title.strip())
        run.font.size = TITLE_SIZE

    contact = [
        value.strip()
        for value in (
            personal.email,
            personal.phone,
            personal.location,
            personal.website,
            personal.linkedin,
            personal.github,
        )
        if value and value.strip()
    ]
    if contact:
        paragraph = doc.add_paragraph()
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        paragraph.paragraph_format.space_after = Pt(2)
        run = paragraph.add_run(" | ".join(contact))
        run.font.size = CONTACT_SIZE


def has_renderable_content(resume: ResumeData) -> bool:
    """Whether the resume has anything to put in a document."""
    personal = resume.personalInfo
    if any(
        (value or "").strip()
        for value in (
            personal.name,
            personal.title,
            personal.email,
            personal.phone,
            personal.location,
            personal.website,
            personal.linkedin,
            personal.github,
        )
    ):
        return True
    if resume.summary.strip():
        return True
    if resume.workExperience or resume.education or resume.personalProjects:
        return True

    additional = resume.additional
    if (
        _flatten_files(additional.technicalSkills)
        or _flatten_files(additional.languages)
        or _flatten_files(additional.certificationsTraining)
        or _flatten_files(additional.awards)
    ):
        return True

    return any(
        _custom_has_content(section.sectionType, data)
        for section in resume.sectionMeta
        if section.isVisible
        for data in [resume.customSections.get(section.key)]
        if data is not None
    )


def build_resume_docx(data: ResumeData | dict[str, Any], language: str = "en") -> bytes:
    """Build the .docx bytes for a resume.

    Args:
        data: Validated ``ResumeData`` or the raw dict stored on the resume.
        language: Content language; ``pt`` formats dates in Brazilian Portuguese.

    Returns:
        The complete .docx file as bytes.
    """
    resume = data if isinstance(data, ResumeData) else ResumeData.model_validate(data)

    doc = _setup_document()
    name = resume.personalInfo.name.strip()
    doc.core_properties.title = name or "Resume"
    doc.core_properties.author = name
    doc.core_properties.comments = "Generated by Resume Matcher"

    _render_header(doc, resume)
    for section in _section_meta(resume):
        if section.key == "personalInfo":
            continue
        _render_section(doc, resume, section, language)

    buffer = BytesIO()
    doc.save(buffer)
    return buffer.getvalue()
