"""Stage 0 — resolve run plan from configs and profiles."""

from __future__ import annotations

import hashlib
from pathlib import Path

from aeon_reader_pipeline.config.hashing import hash_model
from aeon_reader_pipeline.models.run_models import ResolvedDocPlan, ResolvedRunPlan
from aeon_reader_pipeline.stage_framework.base import BaseStage
from aeon_reader_pipeline.stage_framework.context import StageContext
from aeon_reader_pipeline.stage_framework.registry import filter_stages, register_stage

STAGE_NAME = "resolve_run"
STAGE_VERSION = "1.0.0"


def _hash_prompt_bundle(configs_root: Path, bundle_id: str) -> str | None:
    """Hash prompt bundle directory contents for a cache key.

    Bundle ID like ``translate-v1`` maps to ``prompts/translate/v1/``.
    Returns None if the directory does not exist.
    """
    suffix = bundle_id.replace("translate-", "")
    prompts_dir = configs_root.parent / "prompts" / "translate" / suffix
    if not prompts_dir.is_dir():
        return None
    h = hashlib.sha256()
    for f in sorted(prompts_dir.rglob("*")):
        if f.is_file():
            h.update(f.name.encode())
            h.update(f.read_bytes())
    return h.hexdigest()


def _resolve_doc(ctx: StageContext) -> ResolvedDocPlan:
    """Build a resolved plan for a single document."""
    source_pdf = Path(ctx.document_config.source_pdf)
    if not source_pdf.exists():
        raise FileNotFoundError(f"Source PDF not found: {source_pdf}")

    return ResolvedDocPlan(
        doc_id=ctx.doc_id,
        source_pdf_path=str(source_pdf),
        config_hash=hash_model(ctx.document_config),
        rule_profile_hash=hash_model(ctx.rule_profile),
        model_profile_hash=hash_model(ctx.model_profile),
        symbol_pack_hash=hash_model(ctx.symbol_pack),
        glossary_pack_hash=hash_model(ctx.glossary_pack),
        patch_set_hash=hash_model(ctx.patch_set) if ctx.patch_set else None,
        prompt_bundle_hash=_hash_prompt_bundle(ctx.configs_root, ctx.model_profile.prompt_bundle),
    )


@register_stage
class ResolveRunStage(BaseStage):
    """Validate configs and produce a deterministic run plan."""

    name = STAGE_NAME
    version = STAGE_VERSION
    description = "Resolve and validate configs, compute deterministic cache keys"

    def execute(self, ctx: StageContext) -> None:
        ctx.logger.info("resolving_run", doc_id=ctx.doc_id)

        doc_plan = _resolve_doc(ctx)

        stage_plan = filter_stages(
            from_stage=ctx.pipeline_config.stages.from_stage,
            to_stage=ctx.pipeline_config.stages.to_stage,
            only=ctx.pipeline_config.stages.only,
        )

        plan = ResolvedRunPlan(
            run_id=ctx.run_id,
            docs=[doc_plan],
            stage_plan=stage_plan,
            config_snapshot={
                "pipeline": ctx.pipeline_config.model_dump(mode="json"),
                "document": ctx.document_config.model_dump(mode="json"),
            },
        )

        ctx.artifact_store.write_artifact(
            ctx.run_id,
            ctx.doc_id,
            STAGE_NAME,
            "resolved_plan.json",
            plan,
        )

        ctx.logger.info(
            "run_resolved",
            config_hash=doc_plan.config_hash[:12],
            rule_hash=doc_plan.rule_profile_hash[:12],
            model_hash=doc_plan.model_profile_hash[:12],
            glossary_hash=doc_plan.glossary_pack_hash[:12],
            stages=len(stage_plan),
        )
