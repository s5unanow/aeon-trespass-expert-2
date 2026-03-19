"""Quality assurance subpackage."""

from __future__ import annotations

from aeon_reader_pipeline.models.qa_models import QASummary


class QualityGateError(Exception):
    """Raised when QA quality gate rejects the document."""

    def __init__(self, summary: QASummary) -> None:
        self.summary = summary
        reasons = "; ".join(summary.rejection_reasons)
        super().__init__(f"QA quality gate failed for '{summary.doc_id}': {reasons}")
