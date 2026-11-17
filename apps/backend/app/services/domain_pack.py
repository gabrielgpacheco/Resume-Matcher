"""Resolve the domain vocabulary pack for a tailoring run.

The pack itself lives in ``app/prompts/domain_packs.py``; this module only adds
the stored preference, so callers do not each have to read config.json.
"""

import logging

from app.config_cache import load_config
from app.prompts.domain_packs import (
    DEFAULT_DOMAIN_PACK_SETTING,
    DomainPack,
    domain_pack_prompt,
    resolve_domain_pack,
)

logger = logging.getLogger(__name__)


def configured_domain_pack_setting() -> str:
    """Return the stored domain-pack preference."""
    config = load_config()
    value = config.get("domain_pack", DEFAULT_DOMAIN_PACK_SETTING)
    return value if isinstance(value, str) else DEFAULT_DOMAIN_PACK_SETTING


def active_domain_pack(job_description: str) -> DomainPack | None:
    """Return the pack that applies to this job, honoring the setting."""
    return resolve_domain_pack(job_description, configured_domain_pack_setting())


def domain_pack_prompt_for(job_description: str) -> str:
    """Return the prompt block for this job, or an empty string.

    Kept as a single call site so preview and background tailoring always agree.
    """
    return domain_pack_prompt(job_description, configured_domain_pack_setting())
