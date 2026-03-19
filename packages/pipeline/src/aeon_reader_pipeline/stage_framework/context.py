"""Stage execution context — typed runtime environment for stages."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

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
from aeon_reader_pipeline.models.run_models import PipelineConfig, StageErrorRecord

if TYPE_CHECKING:
    from aeon_reader_pipeline.llm.base import LlmGateway


class ErrorCollector:
    """Thread-safe collector for stage errors."""

    def __init__(self) -> None:
        self._errors: list[StageErrorRecord] = []
        self._lock = threading.Lock()

    def record(
        self,
        error_type: str,
        message: str,
        **context: Any,
    ) -> None:
        """Record a non-fatal error."""
        with self._lock:
            self._errors.append(
                StageErrorRecord(error_type=error_type, message=message, context=context)
            )

    def collect(self) -> list[StageErrorRecord]:
        """Return all collected errors and reset."""
        with self._lock:
            errors = list(self._errors)
            self._errors.clear()
            return errors

    @property
    def count(self) -> int:
        with self._lock:
            return len(self._errors)


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
    llm_gateway: LlmGateway | None = None
    logger: Any = field(default_factory=lambda: structlog.get_logger())
    errors: ErrorCollector = field(default_factory=ErrorCollector)

    @property
    def stage_dir(self) -> Path:
        """Convenience: not valid until the runner sets the current stage."""
        raise NotImplementedError("Use artifact_store.stage_dir() with explicit stage name")
