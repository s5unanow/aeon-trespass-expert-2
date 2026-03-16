"""Base class for pipeline stages."""

from __future__ import annotations

from abc import ABC, abstractmethod

from aeon_reader_pipeline.stage_framework.context import StageContext


class BaseStage(ABC):
    """Abstract base for all pipeline stages."""

    name: str
    version: str
    description: str = ""

    @abstractmethod
    def execute(self, ctx: StageContext) -> None:
        """Execute the stage. Must be implemented by subclasses."""
        ...

    def should_skip(self, ctx: StageContext) -> bool:
        """Check if this stage can be skipped (e.g., cached output exists)."""
        manifest = ctx.artifact_store.load_stage_manifest(
            ctx.run_id, ctx.doc_id, self.name
        )
        return manifest is not None and manifest.status == "completed"
