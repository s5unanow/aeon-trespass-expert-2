"""Prompt templates and builders for LLM interactions."""

from __future__ import annotations

from pathlib import Path

import jinja2
import orjson

from aeon_reader_pipeline.models.translation_models import TranslationUnit


def render_system_prompt(
    prompts_root: Path,
    prompt_bundle: str,
    source_locale: str,
    target_locale: str,
) -> str:
    """Render the system prompt from a Jinja2 template.

    Looks for prompts_root/translate/<bundle>/system.j2
    """
    bundle_dir = prompts_root / "translate" / prompt_bundle.replace("translate-", "")
    template_path = bundle_dir / "system.j2"

    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(bundle_dir)),
        autoescape=False,  # nosec B701
        keep_trailing_newline=True,
    )
    template = env.get_template(template_path.name)
    return template.render(
        source_locale=source_locale,
        target_locale=target_locale,
    )


def render_user_prompt(unit: TranslationUnit) -> str:
    """Build the user prompt from a TranslationUnit.

    The prompt is the JSON representation of the unit, which the LLM
    uses to produce its structured response.
    """
    prompt_data = {
        "unit_id": unit.unit_id,
        "doc_id": unit.doc_id,
        "page_number": unit.page_number,
        "section_path": unit.section_path,
        "style_hint": unit.style_hint,
        "glossary_subset": [h.model_dump() for h in unit.glossary_subset],
        "text_nodes": [n.model_dump() for n in unit.text_nodes],
        "context_before": unit.context_before,
        "context_after": unit.context_after,
    }
    return orjson.dumps(prompt_data, option=orjson.OPT_INDENT_2).decode("utf-8")


def load_response_schema(prompts_root: Path, prompt_bundle: str) -> dict[str, object]:
    """Load the expected JSON response schema for validation."""
    bundle_dir = prompts_root / "translate" / prompt_bundle.replace("translate-", "")
    schema_path = bundle_dir / "response_schema.json"
    data: dict[str, object] = orjson.loads(schema_path.read_bytes())
    return data
