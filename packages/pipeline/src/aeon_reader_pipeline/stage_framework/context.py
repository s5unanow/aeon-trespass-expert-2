"""Stage execution context — typed runtime environment for stages."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog

from aeon_reader_pipeline.io.artifact_store import ArtifactStore
from aeon_reader_pipeline.models.config_models import (
    DocumentConfig,
    GlossaryPack,
    ModelProfile,
    PatchSet,
    RuleProfile,
    SymbolPack,
)
from aeon_reader_pipeline.models.run_models import PipelineConfig


@dataclass
class StageContext:
    """Runtime context passed to every stage."""

    run_id: str
    doc_id: str
    pipeline_config: PipelineConfig
    document_config: DocumentConfig
    rule_profile: RuleProfile
    model_profile: ModelProfile
    symbol_pack: SymbolPack
    glossary_pack: GlossaryPack
    patch_set: PatchSet | None
    artifact_store: ArtifactStore
    configs_root: Path
    logger: Any = field(default_factory=lambda: structlog.get_logger())

    @property
    def stage_dir(self) -> Path:
        """Convenience: not valid until the runner sets the current stage."""
        raise NotImplementedError("Use artifact_store.stage_dir() with explicit stage name")
