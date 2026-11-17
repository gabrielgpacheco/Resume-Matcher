"""Domain vocabulary packs: detection, settings resolution and prompt wiring."""

from unittest.mock import AsyncMock, patch

import pytest

from app.prompts.domain_packs import (
    AUTO_DOMAIN_PACK,
    NO_DOMAIN_PACK,
    WORDPRESS_PHP_PACK,
    detect_domain_pack,
    domain_pack_options,
    domain_pack_prompt,
    pack_by_id,
    resolve_domain_pack,
)
from app.services.domain_pack import (
    configured_domain_pack_setting,
    domain_pack_prompt_for,
)
from app.services.improver import generate_resume_diffs, improve_resume

WORDPRESS_JOB = (
    "Buscamos desenvolvedor WordPress com WooCommerce para manter temas "
    "filhos, criar plugins próprios e otimizar Core Web Vitals."
)
BACKEND_JOB = (
    "Backend engineer to build Go services on Kubernetes, own Postgres "
    "schemas and ship internal APIs."
)


class TestDetection:
    def test_a_strong_term_selects_the_pack(self):
        assert detect_domain_pack(WORDPRESS_JOB) is WORDPRESS_PHP_PACK

    def test_three_generic_terms_select_the_pack(self):
        job = "Vaga para dev PHP com Composer, MySQL e integração REST API."
        assert detect_domain_pack(job) is WORDPRESS_PHP_PACK

    def test_a_generic_backend_job_does_not_borrow_the_pack(self):
        assert detect_domain_pack(BACKEND_JOB) is None

    def test_an_empty_job_description_selects_nothing(self):
        assert detect_domain_pack("") is None
        assert detect_domain_pack("   ") is None

    def test_terms_match_whole_words_only(self):
        assert detect_domain_pack("We use Kubernetes and Wonderwordpressish") is None


class TestResolution:
    @pytest.mark.parametrize("setting", [NO_DOMAIN_PACK, "none", "disabled"])
    def test_off_never_injects(self, setting: str):
        assert resolve_domain_pack(WORDPRESS_JOB, setting) is None

    @pytest.mark.parametrize("setting", [None, "", "AUTO"])
    def test_auto_detects_from_the_job(self, setting: str | None):
        assert resolve_domain_pack(WORDPRESS_JOB, setting) is WORDPRESS_PHP_PACK
        assert resolve_domain_pack(BACKEND_JOB, setting) is None

    def test_an_explicit_pack_always_applies(self):
        assert resolve_domain_pack(BACKEND_JOB, "wordpress") is WORDPRESS_PHP_PACK

    def test_an_unknown_pack_is_ignored(self):
        assert resolve_domain_pack(WORDPRESS_JOB, "drupal") is None
        assert pack_by_id("drupal") is None

    def test_missing_setting_defaults_to_auto(self):
        assert resolve_domain_pack(WORDPRESS_JOB, None) is WORDPRESS_PHP_PACK


class TestPromptSection:
    def test_prompt_names_the_vocabulary_areas(self):
        section = WORDPRESS_PHP_PACK.prompt_section()

        assert "DOMAIN VOCABULARY" in section
        assert "WooCommerce" in section
        assert "custom post types (CPT)" in section
        assert "Core Web Vitals" in section

    def test_prompt_forbids_claiming_missing_work(self):
        section = WORDPRESS_PHP_PACK.prompt_section()

        assert "only for naming work the resume already shows" in section
        assert "Never add a tool, plugin, platform" in section
        assert "separate interview" in section
        assert "does not change the strategy above" in section

    def test_an_empty_prompt_means_no_pack(self):
        assert domain_pack_prompt(BACKEND_JOB, AUTO_DOMAIN_PACK) == ""

    def test_settings_options_cover_auto_off_and_each_pack(self):
        ids = [option["id"] for option in domain_pack_options()]

        assert ids[:2] == [AUTO_DOMAIN_PACK, NO_DOMAIN_PACK]
        assert "wordpress" in ids


class TestStoredSetting:
    def test_service_reads_the_stored_preference(self):
        with patch(
            "app.services.domain_pack.load_config",
            return_value={"domain_pack": NO_DOMAIN_PACK},
        ):
            assert configured_domain_pack_setting() == NO_DOMAIN_PACK
            assert domain_pack_prompt_for(WORDPRESS_JOB) == ""

    def test_service_uses_auto_when_the_key_is_absent(self):
        with patch("app.services.domain_pack.load_config", return_value={}):
            assert configured_domain_pack_setting() == AUTO_DOMAIN_PACK
            assert "DOMAIN VOCABULARY" in domain_pack_prompt_for(WORDPRESS_JOB)


class TestPromptInjection:
    async def test_empty_section_keeps_the_diff_prompt_unchanged(self) -> None:
        with patch(
            "app.services.improver.complete_json",
            new_callable=AsyncMock,
            return_value={"changes": [], "strategy_notes": ""},
        ) as complete_json:
            await generate_resume_diffs(
                original_resume="# Ada\n\nBuilt WordPress themes",
                job_description=WORDPRESS_JOB,
                job_keywords={"skills": ["WordPress"]},
                language="en",
                original_resume_data={"personalInfo": {"name": "Ada"}},
            )

        prompt = complete_json.call_args.kwargs["prompt"]
        assert "{domain_pack_section}" not in prompt
        assert "DOMAIN VOCABULARY" not in prompt

    async def test_empty_section_keeps_the_full_prompt_unchanged(self) -> None:
        with patch(
            "app.services.improver.complete_json",
            new_callable=AsyncMock,
            return_value={"summary": "WordPress developer"},
        ) as complete_json:
            await improve_resume(
                original_resume="# Ada",
                job_description=WORDPRESS_JOB,
                job_keywords={"skills": ["WordPress"]},
                language="en",
            )

        prompt = complete_json.call_args.kwargs["prompt"]
        assert "{domain_pack_section}" not in prompt
        assert "DOMAIN VOCABULARY" not in prompt

    async def test_the_diff_prompt_carries_the_pack_when_given(self) -> None:
        section = WORDPRESS_PHP_PACK.prompt_section()
        with patch(
            "app.services.improver.complete_json",
            new_callable=AsyncMock,
            return_value={"changes": [], "strategy_notes": ""},
        ) as complete_json:
            await generate_resume_diffs(
                original_resume="# Ada\n\nBuilt WordPress themes",
                job_description=WORDPRESS_JOB,
                job_keywords={"skills": ["WordPress"]},
                language="en",
                original_resume_data={
                    "personalInfo": {"name": "Ada"},
                    "workExperience": [],
                },
                domain_pack_section=section,
            )

        prompt = complete_json.call_args.kwargs["prompt"]
        assert section in prompt
        assert "{domain_pack_section}" not in prompt

    async def test_the_full_output_prompt_carries_the_pack_when_given(self) -> None:
        section = WORDPRESS_PHP_PACK.prompt_section()
        with patch(
            "app.services.improver.complete_json",
            new_callable=AsyncMock,
            return_value={"summary": "WordPress developer"},
        ) as complete_json:
            await improve_resume(
                original_resume="# Ada",
                job_description=WORDPRESS_JOB,
                job_keywords={"skills": ["WordPress"]},
                language="en",
                domain_pack_section=section,
            )

        prompt = complete_json.call_args.kwargs["prompt"]
        assert section in prompt
