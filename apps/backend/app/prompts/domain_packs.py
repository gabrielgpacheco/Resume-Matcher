"""Domain vocabulary packs for job tailoring.

A pack gives the model the vocabulary a field uses *without* letting it claim
work the resume does not show. It is a phrasing aid, not a skill list: the
prompt section built here says, in so many words, that a term may only name
work that already exists in the resume and that a missing requirement is left
for the gap interview (``services/gap_interview.py``) instead of being invented.

The ``wordpress`` pack covers the Brazilian WordPress/PHP market: themes,
plugins, WooCommerce, blocks, headless front ends, performance and security.
"""

import re
from dataclasses import dataclass

#: Settings value that detects the pack from the job description.
AUTO_DOMAIN_PACK = "auto"
#: Settings value that never injects a pack.
NO_DOMAIN_PACK = "off"
#: Settings value used when the key is absent from config.json.
DEFAULT_DOMAIN_PACK_SETTING = AUTO_DOMAIN_PACK


@dataclass(frozen=True)
class DomainPack:
    """A vocabulary pack the tailoring prompts can include."""

    id: str
    label: str
    description: str
    #: Job-description terms that identify the field on their own.
    strong_terms: tuple[str, ...]
    #: Weaker terms: three or more distinct hits also select the pack.
    generic_terms: tuple[str, ...]
    #: (area, terms) rows shown to the model.
    vocabulary: tuple[tuple[str, tuple[str, ...]], ...]
    #: Sector guidance that follows the vocabulary list.
    guidance: str = ""

    def prompt_section(self) -> str:
        """Render the pack as a prompt block.

        The block is model-facing English (like the other prompts); the terms
        themselves are technology names, so they stay useful whatever the output
        language is.
        """
        rows = "\n".join(
            f"- {area}: {', '.join(terms)}" for area, terms in self.vocabulary
        )
        guidance = f"\n{self.guidance.strip()}" if self.guidance.strip() else ""
        return (
            f"DOMAIN VOCABULARY ({self.label}), only for naming work the resume "
            "already shows:\n"
            f"{rows}\n"
            "Use a term below only where the resume already shows that work or a "
            "clear equivalent, and prefer the job description's own term when it "
            "names the same thing.\n"
            "Never add a tool, plugin, platform, employer, metric or "
            "responsibility the resume does not show. If the job asks for "
            "something the resume lacks, leave it out: the candidate confirms "
            "gaps in a separate interview.\n"
            "This vocabulary does not change the strategy above: keep the same "
            "bullet count, entries and facts."
            f"{guidance}"
        )


WORDPRESS_PHP_PACK = DomainPack(
    id="wordpress",
    label="WordPress / PHP / WooCommerce",
    description=(
        "Vocabulary for WordPress, WooCommerce, PHP and headless front-end "
        "roles. It only helps phrase work the resume already shows."
    ),
    strong_terms=(
        "wordpress",
        "woocommerce",
        "gutenberg",
        "elementor",
        "wp-cli",
        "wp_query",
        "wp rest api",
        "advanced custom fields",
        "custom post type",
        "custom post types",
        "tema filho",
        "child theme",
        "plugin wordpress",
    ),
    generic_terms=(
        "php",
        "mysql",
        "composer",
        "hooks",
        "shortcode",
        "shortcodes",
        "acf",
        "headless",
        "core web vitals",
        "seo",
        "tema",
        "plugin",
        "bloco",
        "blocos",
        "rest api",
        "astro",
        "next.js",
    ),
    vocabulary=(
        (
            "WordPress core",
            (
                "temas e temas filhos",
                "plugins próprios",
                "hooks e filters",
                "WP_Query",
                "custom post types (CPT)",
                "taxonomias",
                "WP REST API",
                "WP-CLI",
                "shortcodes",
                "multisite",
            ),
        ),
        (
            "Gutenberg e editor",
            (
                "blocos customizados",
                "block patterns",
                "editor de blocos",
                "block.json",
                "renderização no servidor dos blocos",
            ),
        ),
        (
            "Campos e conteúdo",
            (
                "Advanced Custom Fields (ACF)",
                "campos personalizados",
                "opções globais do tema",
                "migração de conteúdo",
            ),
        ),
        (
            "WooCommerce",
            (
                "produtos e variações",
                "checkout",
                "gateways de pagamento",
                "métodos de envio",
                "assinaturas",
                "hooks do WooCommerce",
                "catálogo e filtros de produto",
            ),
        ),
        (
            "PHP e backend",
            (
                "PHP 8.x",
                "Composer",
                "PSR-4 e autoload",
                "orientação a objetos",
                "MySQL",
                "integração com APIs externas",
                "webhooks",
            ),
        ),
        (
            "Front-end e headless",
            (
                "HTML semântico",
                "CSS e SCSS",
                "JavaScript",
                "React",
                "Next.js",
                "Astro",
                "WordPress headless",
                "WP REST API e GraphQL",
            ),
        ),
        (
            "Performance, segurança e qualidade",
            (
                "Core Web Vitals",
                "cache e otimização de consultas",
                "lazy loading",
                "hardening",
                "sanitização e escape",
                "nonces e permissões",
                "acessibilidade (WCAG)",
                "SEO técnico",
                "testes e deploy",
            ),
        ),
    ),
    guidance=(
        "When the resume mentions a page builder, a theme, custom fields, a "
        "store or a PHP integration, name it with the job's terminology only at "
        "the level of detail the resume supports."
    ),
)

DOMAIN_PACKS: dict[str, DomainPack] = {WORDPRESS_PHP_PACK.id: WORDPRESS_PHP_PACK}


def pack_by_id(pack_id: str | None) -> DomainPack | None:
    """Return the pack registered under ``pack_id`` (case-insensitive)."""
    if not pack_id:
        return None
    return DOMAIN_PACKS.get(pack_id.strip().lower())


def _term_pattern(term: str) -> re.Pattern[str]:
    # Whole words only: "acf" must not match "facf", and "plugin" must not
    # match "plugins" only if the term itself is singular.
    return re.compile(rf"(?<!\w){re.escape(term)}(?!\w)", re.IGNORECASE)


def _matches(terms: tuple[str, ...], text: str) -> set[str]:
    return {term for term in terms if _term_pattern(term).search(text)}


def detect_domain_pack(job_description: str) -> DomainPack | None:
    """Pick the pack a job description is about, if any.

    One strong term (``wordpress``, ``woocommerce``, ...) selects the pack.
    Otherwise three distinct generic hits (``php``, ``composer``, ``mysql``,
    ...) are needed, so a generic backend job does not borrow WordPress words.
    """
    text = (job_description or "").lower()
    if not text.strip():
        return None
    for pack in DOMAIN_PACKS.values():
        if _matches(pack.strong_terms, text):
            return pack
        if len(_matches(pack.generic_terms, text)) >= 3:
            return pack
    return None


def resolve_domain_pack(
    job_description: str, setting: str | None = None
) -> DomainPack | None:
    """Resolve the effective pack for one tailoring run.

    ``setting`` is the stored preference: ``auto`` (detect from the job),
    ``off`` (never), or a pack id (always use that pack).
    """
    value = (setting or DEFAULT_DOMAIN_PACK_SETTING).strip().lower()
    if value in {"", NO_DOMAIN_PACK, "none", "disabled"}:
        return None
    if value == AUTO_DOMAIN_PACK:
        return detect_domain_pack(job_description)
    return pack_by_id(value)


def domain_pack_prompt(job_description: str, setting: str | None = None) -> str:
    """Prompt block for the effective pack, or an empty string."""
    pack = resolve_domain_pack(job_description, setting)
    return pack.prompt_section() if pack else ""


def domain_pack_options() -> list[dict[str, str]]:
    """Settings options: automatic detection, disabled, then each pack."""
    options = [
        {
            "id": AUTO_DOMAIN_PACK,
            "label": "Automatic",
            "description": (
                "Use a domain pack when the job description clearly belongs to it."
            ),
        },
        {
            "id": NO_DOMAIN_PACK,
            "label": "Off",
            "description": "Never add domain vocabulary to tailoring.",
        },
    ]
    options.extend(
        {
            "id": pack.id,
            "label": pack.label,
            "description": pack.description,
        }
        for pack in DOMAIN_PACKS.values()
    )
    return options
