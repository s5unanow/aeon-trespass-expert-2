"""Tests for cost estimation utility."""

from __future__ import annotations

from aeon_reader_pipeline.models.config_models import ModelProfile
from aeon_reader_pipeline.models.run_models import CostEstimate
from aeon_reader_pipeline.models.translation_models import (
    GlossaryHint,
    TextNode,
    TranslationUnit,
)
from aeon_reader_pipeline.utils.cost_estimation import (
    estimate_cost,
    estimate_unit_tokens,
    format_cost_report,
)


def _make_unit(
    unit_id: str = "u1",
    text: str = "Hello world",
    glossary: list[GlossaryHint] | None = None,
    context_before: str = "",
    context_after: str = "",
) -> TranslationUnit:
    return TranslationUnit(
        unit_id=unit_id,
        doc_id="test-doc",
        page_number=1,
        block_ids=["b1"],
        text_nodes=[TextNode(inline_id="t1", source_text=text)],
        glossary_subset=glossary or [],
        context_before=context_before,
        context_after=context_after,
    )


def _make_profile(
    input_price: float = 1.25,
    output_price: float = 10.0,
) -> ModelProfile:
    return ModelProfile(
        profile_id="test",
        provider="gemini",
        model="gemini-2.5-pro",
        input_price_per_mtok=input_price,
        output_price_per_mtok=output_price,
    )


class TestEstimateUnitTokens:
    """Tests for single-unit token estimation."""

    def test_returns_positive_input_and_output(self) -> None:
        unit = _make_unit(text="Some text to translate")
        inp, out = estimate_unit_tokens(unit)
        assert inp > 0
        assert out > 0

    def test_longer_text_produces_more_tokens(self) -> None:
        short = _make_unit(text="Hi")
        long = _make_unit(
            text="This is a much longer paragraph of text that should produce more tokens."
        )

        short_inp, short_out = estimate_unit_tokens(short)
        long_inp, long_out = estimate_unit_tokens(long)

        assert long_inp > short_inp
        assert long_out > short_out

    def test_glossary_adds_to_input_tokens(self) -> None:
        without = _make_unit(text="Hello")
        with_glossary = _make_unit(
            text="Hello",
            glossary=[
                GlossaryHint(en="Titan", ru="Титан", locked=True),
                GlossaryHint(en="Argonaut", ru="Аргонавт", locked=False),
            ],
        )

        inp_without, _ = estimate_unit_tokens(without)
        inp_with, _ = estimate_unit_tokens(with_glossary)

        assert inp_with > inp_without

    def test_context_adds_to_input_tokens(self) -> None:
        without = _make_unit(text="Hello")
        with_ctx = _make_unit(
            text="Hello",
            context_before="Previous paragraph text here",
            context_after="Next paragraph text here",
        )

        inp_without, _ = estimate_unit_tokens(without)
        inp_with, _ = estimate_unit_tokens(with_ctx)

        assert inp_with > inp_without

    def test_minimum_one_token(self) -> None:
        unit = _make_unit(text="")
        inp, out = estimate_unit_tokens(unit)
        assert inp >= 1
        assert out >= 1

    def test_multiple_text_nodes(self) -> None:
        unit = TranslationUnit(
            unit_id="u1",
            doc_id="test-doc",
            page_number=1,
            block_ids=["b1", "b2"],
            text_nodes=[
                TextNode(inline_id="t1", source_text="First sentence."),
                TextNode(inline_id="t2", source_text="Second sentence."),
                TextNode(inline_id="t3", source_text="Third sentence."),
            ],
        )
        inp, out = estimate_unit_tokens(unit)
        assert inp > 0
        assert out > 0


class TestEstimateCost:
    """Tests for full cost estimation."""

    def test_empty_units(self) -> None:
        profile = _make_profile()
        result = estimate_cost([], profile, "test-doc")

        assert result.total_units == 0
        assert result.estimated_input_tokens == 0
        assert result.estimated_output_tokens == 0
        assert result.estimated_cost_usd == 0.0

    def test_single_unit_cost(self) -> None:
        units = [_make_unit(text="Hello world")]
        profile = _make_profile(input_price=1.25, output_price=10.0)
        result = estimate_cost(units, profile, "test-doc")

        assert result.total_units == 1
        assert result.total_text_nodes == 1
        assert result.estimated_input_tokens > 0
        assert result.estimated_output_tokens > 0
        assert result.estimated_cost_usd > 0.0
        assert result.doc_id == "test-doc"
        assert result.model == "gemini-2.5-pro"
        assert result.provider == "gemini"

    def test_multiple_units_cost_is_additive(self) -> None:
        units = [
            _make_unit(unit_id="u1", text="First unit"),
            _make_unit(unit_id="u2", text="Second unit"),
        ]
        profile = _make_profile()

        result = estimate_cost(units, profile, "test-doc")
        single1 = estimate_cost([units[0]], profile, "test-doc")
        single2 = estimate_cost([units[1]], profile, "test-doc")

        assert result.estimated_input_tokens == (
            single1.estimated_input_tokens + single2.estimated_input_tokens
        )
        assert result.estimated_output_tokens == (
            single1.estimated_output_tokens + single2.estimated_output_tokens
        )

    def test_zero_pricing_gives_zero_cost(self) -> None:
        units = [_make_unit(text="Hello world")]
        profile = _make_profile(input_price=0.0, output_price=0.0)
        result = estimate_cost(units, profile, "test-doc")

        assert result.estimated_input_tokens > 0
        assert result.estimated_cost_usd == 0.0

    def test_pricing_fields_are_preserved(self) -> None:
        profile = _make_profile(input_price=2.5, output_price=7.5)
        result = estimate_cost([_make_unit()], profile, "test-doc")

        assert result.input_price_per_mtok == 2.5
        assert result.output_price_per_mtok == 7.5

    def test_cost_calculation_is_correct(self) -> None:
        """Verify cost = (input_tokens * input_price + output_tokens * output_price) / 1M."""
        units = [_make_unit(text="x" * 400)]  # 400 chars -> ~100 text tokens
        profile = _make_profile(input_price=1.0, output_price=1.0)
        result = estimate_cost(units, profile, "test-doc")

        expected = (
            result.estimated_input_tokens * 1.0 / 1_000_000
            + result.estimated_output_tokens * 1.0 / 1_000_000
        )
        assert abs(result.estimated_cost_usd - round(expected, 4)) < 0.0001


class TestFormatCostReport:
    """Tests for the human-readable cost report."""

    def test_single_doc_report(self) -> None:
        estimate = CostEstimate(
            doc_id="rulebook-v1",
            total_units=50,
            total_text_nodes=120,
            estimated_input_tokens=50000,
            estimated_output_tokens=30000,
            input_price_per_mtok=1.25,
            output_price_per_mtok=10.0,
            estimated_cost_usd=0.3625,
            model="gemini-2.5-pro",
            provider="gemini",
        )
        report = format_cost_report([estimate])

        assert "COST ESTIMATE" in report
        assert "rulebook-v1" in report
        assert "gemini/gemini-2.5-pro" in report
        assert "50" in report  # units
        assert "120" in report  # nodes
        assert "50,000" in report  # input tokens
        assert "30,000" in report  # output tokens
        assert "$0.3625" in report

    def test_no_pricing_shows_message(self) -> None:
        estimate = CostEstimate(
            doc_id="test-doc",
            total_units=10,
            total_text_nodes=20,
            estimated_input_tokens=5000,
            estimated_output_tokens=3000,
            input_price_per_mtok=0.0,
            output_price_per_mtok=0.0,
            estimated_cost_usd=0.0,
            model="test-model",
            provider="test",
        )
        report = format_cost_report([estimate])

        assert "not configured" in report

    def test_multi_doc_report_has_total(self) -> None:
        e1 = CostEstimate(
            doc_id="doc-1",
            total_units=30,
            total_text_nodes=60,
            estimated_input_tokens=20000,
            estimated_output_tokens=10000,
            input_price_per_mtok=1.25,
            output_price_per_mtok=10.0,
            estimated_cost_usd=0.125,
            model="gemini-2.5-pro",
            provider="gemini",
        )
        e2 = CostEstimate(
            doc_id="doc-2",
            total_units=20,
            total_text_nodes=40,
            estimated_input_tokens=15000,
            estimated_output_tokens=8000,
            input_price_per_mtok=1.25,
            output_price_per_mtok=10.0,
            estimated_cost_usd=0.0988,
            model="gemini-2.5-pro",
            provider="gemini",
        )
        report = format_cost_report([e1, e2])

        assert "TOTAL" in report
        assert "doc-1" in report
        assert "doc-2" in report
        # Grand total should include both
        assert "Documents:         2" in report

    def test_empty_estimates(self) -> None:
        report = format_cost_report([])
        assert "COST ESTIMATE" in report
