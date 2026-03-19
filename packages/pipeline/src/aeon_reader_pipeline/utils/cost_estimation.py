"""Token count and API cost estimation for translation units."""

from __future__ import annotations

from aeon_reader_pipeline.models.config_models import ModelProfile
from aeon_reader_pipeline.models.run_models import CostEstimate
from aeon_reader_pipeline.models.translation_models import TranslationUnit

# Rough token-to-character ratio for mixed EN/JSON content.
# Gemini and similar models average ~4 characters per token for English text.
# JSON structural overhead adds ~30% more tokens than raw text.
_CHARS_PER_TOKEN = 4

# Fixed overhead per LLM call for system prompt + JSON framing.
# The system prompt (~1500 chars) plus JSON structure per unit (~200 chars).
_SYSTEM_PROMPT_TOKENS = 500
_JSON_OVERHEAD_TOKENS = 80

# Output tokens are typically ~1.2x source text length for EN→RU translation
# (Russian text tends to be slightly longer than English).
_OUTPUT_RATIO = 1.2


def estimate_unit_tokens(unit: TranslationUnit) -> tuple[int, int]:
    """Estimate input and output tokens for a single translation unit.

    Returns (input_tokens, output_tokens).
    """
    # Input: source text + glossary hints + context + JSON structure
    source_chars = sum(len(n.source_text) for n in unit.text_nodes)
    glossary_chars = sum(
        len(h.en) + len(h.ru) + 10  # field overhead
        for h in unit.glossary_subset
    )
    context_chars = len(unit.context_before) + len(unit.context_after)

    text_tokens = (source_chars + glossary_chars + context_chars) // _CHARS_PER_TOKEN
    input_tokens = text_tokens + _JSON_OVERHEAD_TOKENS + _SYSTEM_PROMPT_TOKENS

    # Output: translated text + JSON framing
    output_text_tokens = int(source_chars / _CHARS_PER_TOKEN * _OUTPUT_RATIO)
    output_tokens = output_text_tokens + _JSON_OVERHEAD_TOKENS

    return max(input_tokens, 1), max(output_tokens, 1)


def estimate_cost(
    units: list[TranslationUnit],
    model_profile: ModelProfile,
    doc_id: str,
) -> CostEstimate:
    """Estimate total token count and API cost for a list of translation units."""
    total_input = 0
    total_output = 0

    for unit in units:
        inp, out = estimate_unit_tokens(unit)
        total_input += inp
        total_output += out

    total_text_nodes = sum(len(u.text_nodes) for u in units)

    input_cost = total_input * model_profile.input_price_per_mtok / 1_000_000
    output_cost = total_output * model_profile.output_price_per_mtok / 1_000_000
    total_cost = input_cost + output_cost

    return CostEstimate(
        doc_id=doc_id,
        total_units=len(units),
        total_text_nodes=total_text_nodes,
        estimated_input_tokens=total_input,
        estimated_output_tokens=total_output,
        input_price_per_mtok=model_profile.input_price_per_mtok,
        output_price_per_mtok=model_profile.output_price_per_mtok,
        estimated_cost_usd=round(total_cost, 4),
        model=model_profile.model,
        provider=model_profile.provider,
    )


def format_cost_report(estimates: list[CostEstimate]) -> str:
    """Format cost estimates into a human-readable report."""
    lines: list[str] = []
    lines.append("=" * 60)
    lines.append("COST ESTIMATE")
    lines.append("=" * 60)

    grand_input = 0
    grand_output = 0
    grand_cost = 0.0
    grand_units = 0
    grand_nodes = 0

    for est in estimates:
        lines.append(f"\nDocument: {est.doc_id}")
        lines.append(f"  Model:            {est.provider}/{est.model}")
        lines.append(f"  Translation units: {est.total_units}")
        lines.append(f"  Text nodes:        {est.total_text_nodes}")
        lines.append(f"  Est. input tokens: {est.estimated_input_tokens:,}")
        lines.append(f"  Est. output tokens: {est.estimated_output_tokens:,}")
        if est.input_price_per_mtok > 0 or est.output_price_per_mtok > 0:
            lines.append(f"  Input price:       ${est.input_price_per_mtok}/MTok")
            lines.append(f"  Output price:      ${est.output_price_per_mtok}/MTok")
            lines.append(f"  Est. cost:         ${est.estimated_cost_usd:.4f}")
        else:
            lines.append(
                "  Pricing:           not configured (set *_price_per_mtok in model profile)"
            )

        grand_input += est.estimated_input_tokens
        grand_output += est.estimated_output_tokens
        grand_cost += est.estimated_cost_usd
        grand_units += est.total_units
        grand_nodes += est.total_text_nodes

    if len(estimates) > 1:
        lines.append(f"\n{'─' * 60}")
        lines.append("TOTAL")
        lines.append(f"  Documents:         {len(estimates)}")

    if len(estimates) >= 1:
        lines.append(f"  Translation units: {grand_units}")
        lines.append(f"  Text nodes:        {grand_nodes}")
        lines.append(f"  Est. input tokens: {grand_input:,}")
        lines.append(f"  Est. output tokens: {grand_output:,}")
        if grand_cost > 0:
            lines.append(f"  Est. total cost:   ${grand_cost:.4f}")

    lines.append("=" * 60)
    return "\n".join(lines)
