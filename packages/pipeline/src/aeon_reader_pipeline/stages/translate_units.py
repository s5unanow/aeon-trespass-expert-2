"""Stage 6 — translate individual translation units via LLM."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from aeon_reader_pipeline.llm.base import LlmGateway
from aeon_reader_pipeline.llm.placeholders import (
    inject_placeholders,
    restore_placeholders,
    validate_placeholders,
)
from aeon_reader_pipeline.llm.prompts import render_system_prompt, render_user_prompt
from aeon_reader_pipeline.llm.translation_memory import TranslationMemory
from aeon_reader_pipeline.llm.validation import (
    ValidationError,
    parse_translation_response,
    validate_glossary_compliance,
)
from aeon_reader_pipeline.models.translation_models import (
    TranslationCallMetadata,
    TranslationFailure,
    TranslationPlan,
    TranslationResult,
    TranslationStageSummary,
    TranslationUnit,
)
from aeon_reader_pipeline.stage_framework.base import BaseStage
from aeon_reader_pipeline.stage_framework.context import StageContext
from aeon_reader_pipeline.stage_framework.registry import register_stage

STAGE_NAME = "translate_units"
STAGE_VERSION = "1.0.0"

MAX_RETRIES = 3


def _translate_single_unit(
    unit: TranslationUnit,
    gateway: LlmGateway,
    system_prompt: str,
    ctx: StageContext,
    tm: TranslationMemory,
) -> tuple[TranslationResult | None, TranslationFailure | None, TranslationCallMetadata | None]:
    """Translate a single unit with retry logic."""
    # Check translation memory first
    cached = tm.lookup(unit)
    if cached is not None:
        ctx.logger.debug("tm_cache_hit", unit_id=unit.unit_id)
        meta = TranslationCallMetadata(
            unit_id=unit.unit_id,
            provider="cache",
            model="cache",
            prompt_bundle="",
            cache_hit=True,
        )
        return cached, None, meta

    # Inject placeholders for locked terms
    processed_nodes, ph_map = inject_placeholders(unit.text_nodes, unit.glossary_subset)
    processed_unit = unit.model_copy(update={"text_nodes": processed_nodes})

    profile = ctx.model_profile
    prompt_bundle = profile.prompt_bundle

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            user_prompt = render_user_prompt(processed_unit)
            response = gateway.translate(system_prompt, user_prompt, profile)

            # Parse and validate
            result = parse_translation_response(
                response.text,
                processed_unit,
                provider=response.provider,
                model=response.model,
                prompt_bundle=prompt_bundle,
            )

            # Validate placeholders (warnings only — don't fail the unit)
            ph_errors = validate_placeholders(result.translations, ph_map)
            for ph_err in ph_errors:
                ctx.logger.warning("placeholder_warning", unit_id=unit.unit_id, detail=ph_err)

            # Restore placeholders
            restored = restore_placeholders(result.translations, ph_map)
            result = result.model_copy(update={"translations": restored, "attempt": attempt})

            # Glossary compliance (warnings only)
            warnings = validate_glossary_compliance(result, unit)
            for w in warnings:
                ctx.logger.warning("glossary_warning", unit_id=unit.unit_id, warning=w)

            # Store in translation memory
            tm.store(unit, result)

            meta = TranslationCallMetadata(
                unit_id=unit.unit_id,
                provider=response.provider,
                model=response.model,
                prompt_bundle=prompt_bundle,
                temperature=profile.temperature,
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                latency_ms=response.latency_ms,
            )

            return result, None, meta

        except ValidationError as e:
            ctx.logger.warning(
                "translation_validation_failed",
                unit_id=unit.unit_id,
                attempt=attempt,
                errors=e.errors,
            )
            if attempt == MAX_RETRIES:
                ctx.errors.record(
                    error_type="validation_error",
                    message=str(e),
                    unit_id=unit.unit_id,
                    attempt=attempt,
                )
                failure = TranslationFailure(
                    unit_id=unit.unit_id,
                    error_type="validation_error",
                    error_message=str(e),
                    provider=gateway.provider_name(),
                    model=profile.model,
                    attempt=attempt,
                )
                return None, failure, None

        except Exception as e:
            ctx.logger.warning(
                "translation_call_failed",
                unit_id=unit.unit_id,
                attempt=attempt,
                error=str(e),
            )
            if attempt == MAX_RETRIES:
                ctx.errors.record(
                    error_type=type(e).__name__,
                    message=str(e),
                    unit_id=unit.unit_id,
                    attempt=attempt,
                )
                failure = TranslationFailure(
                    unit_id=unit.unit_id,
                    error_type=type(e).__name__,
                    error_message=str(e),
                    provider=gateway.provider_name(),
                    model=profile.model,
                    attempt=attempt,
                )
                return None, failure, None

    return None, None, None  # pragma: no cover


def _get_prompts_root(ctx: StageContext) -> Path:
    """Find the prompts directory relative to configs_root."""
    # prompts/ lives at repo root, configs_root is configs/
    return ctx.configs_root.parent / "prompts"


@register_stage
class TranslateUnitsStage(BaseStage):
    """Translate planned units via LLM gateway."""

    name = STAGE_NAME
    version = STAGE_VERSION
    description = "Execute LLM translation of planned units with retry and caching"

    def execute(self, ctx: StageContext) -> None:  # noqa: C901, PLR0915
        plan = ctx.artifact_store.read_artifact(
            ctx.run_id,
            ctx.doc_id,
            "plan_translation",
            "translation_plan.json",
            TranslationPlan,
        )

        ctx.logger.info("translating_units", total_units=plan.total_units)

        if not plan.units:
            self._write_empty_summary(ctx, plan)
            return

        # Get gateway from context, fall back to default provider
        gateway = ctx.llm_gateway
        if gateway is None:
            from aeon_reader_pipeline.llm.gemini import GeminiProvider

            gateway = GeminiProvider()

        # Set up translation memory
        cache_dir = ctx.artifact_store.cache_dir_for(STAGE_NAME, ctx.doc_id)
        tm = TranslationMemory(cache_dir)

        # Render system prompt once
        prompts_root = _get_prompts_root(ctx)
        system_prompt = render_system_prompt(
            prompts_root,
            ctx.model_profile.prompt_bundle,
            ctx.document_config.source_locale,
            ctx.document_config.target_locale,
        )

        results: list[TranslationResult] = []
        failures: list[TranslationFailure] = []
        calls: list[TranslationCallMetadata] = []
        cached_count = 0
        lock = threading.Lock()
        completed_count = 0

        concurrency = ctx.pipeline_config.llm_concurrency

        _UnitOutcome = tuple[
            TranslationResult | None,
            TranslationFailure | None,
            TranslationCallMetadata | None,
        ]

        def _process_unit(unit: TranslationUnit) -> _UnitOutcome:
            return _translate_single_unit(unit, gateway, system_prompt, ctx, tm)

        def _collect(
            unit: TranslationUnit,
            result: TranslationResult | None,
            failure: TranslationFailure | None,
            meta: TranslationCallMetadata | None,
        ) -> None:
            nonlocal cached_count, completed_count
            with lock:
                if result is not None:
                    results.append(result)
                    ctx.artifact_store.write_artifact(
                        ctx.run_id,
                        ctx.doc_id,
                        STAGE_NAME,
                        f"results/{unit.unit_id}.json",
                        result,
                    )
                    if result.cached:
                        cached_count += 1

                if failure is not None:
                    failures.append(failure)
                    ctx.artifact_store.write_artifact(
                        ctx.run_id,
                        ctx.doc_id,
                        STAGE_NAME,
                        f"failures/{unit.unit_id}.json",
                        failure,
                    )

                if meta is not None:
                    calls.append(meta)

                completed_count += 1
                if completed_count % 50 == 0:
                    ctx.logger.info(
                        "translation_progress",
                        completed=completed_count,
                        total=plan.total_units,
                        succeeded=len(results),
                        failed=len(failures),
                    )

                ctx.logger.debug(
                    "unit_translated",
                    unit_id=unit.unit_id,
                    success=result is not None,
                    cached=result.cached if result else False,
                )

        if concurrency > 1:
            ctx.logger.info("parallel_translation", workers=concurrency)
            with ThreadPoolExecutor(max_workers=concurrency) as executor:
                futures = {executor.submit(_process_unit, unit): unit for unit in plan.units}
                for future in as_completed(futures):
                    unit = futures[future]
                    result, failure, meta = future.result()
                    _collect(unit, result, failure, meta)
        else:
            for unit in plan.units:
                result, failure, meta = _process_unit(unit)
                _collect(unit, result, failure, meta)

        # Write call metadata
        if calls:
            ctx.artifact_store.write_artifact_list(
                ctx.run_id,
                ctx.doc_id,
                STAGE_NAME,
                "calls.jsonl",
                list(calls),
            )

        # Write summary
        status: str = "completed"
        if failures and not results:
            status = "failed"
        elif failures:
            status = "partial"

        summary = TranslationStageSummary(
            doc_id=ctx.doc_id,
            total_units=plan.total_units,
            completed=len(results),
            failed=len(failures),
            cached=cached_count,
            status=status,  # type: ignore[arg-type]
            errors=[{"unit_id": f.unit_id, "error": f.error_message} for f in failures],
        )
        ctx.artifact_store.write_artifact(
            ctx.run_id,
            ctx.doc_id,
            STAGE_NAME,
            "summary.json",
            summary,
        )

        ctx.logger.info(
            "translation_complete",
            completed=len(results),
            failed=len(failures),
            cached=cached_count,
        )

    def _write_empty_summary(self, ctx: StageContext, plan: TranslationPlan) -> None:
        summary = TranslationStageSummary(
            doc_id=ctx.doc_id,
            total_units=0,
            completed=0,
            status="completed",
        )
        ctx.artifact_store.write_artifact(
            ctx.run_id,
            ctx.doc_id,
            STAGE_NAME,
            "summary.json",
            summary,
        )
        ctx.logger.info("no_units_to_translate")
