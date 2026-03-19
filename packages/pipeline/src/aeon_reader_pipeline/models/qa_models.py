"""Quality assurance finding, report, and rule result models."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from aeon_reader_pipeline.utils.ids import content_fingerprint


class IssueLocation(BaseModel):
    """Where an issue was found."""

    page_number: int | None = None
    block_id: str | None = None
    inline_id: str | None = None
    asset_id: str | None = None


class QAIssue(BaseModel):
    """Single quality assurance finding."""

    issue_id: str = ""
    rule_id: str
    severity: Literal["error", "warning", "info"]
    category: str
    message: str
    location: IssueLocation = Field(default_factory=IssueLocation)
    details: dict[str, Any] = Field(default_factory=dict)
    fingerprint: str = ""

    def model_post_init(self, _context: Any) -> None:
        """Auto-compute fingerprint and issue_id if not set."""
        if not self.fingerprint:
            fp_input = f"{self.rule_id}:{self.severity}:{self.message}"
            if self.location.page_number is not None:
                fp_input += f":p{self.location.page_number}"
            if self.location.block_id:
                fp_input += f":{self.location.block_id}"
            self.fingerprint = content_fingerprint(fp_input)
        if not self.issue_id:
            self.issue_id = f"qa-{self.fingerprint[:12]}"


class CategoryBreakdown(BaseModel):
    """Issue counts for a single QA category."""

    category: str
    errors: int = 0
    warnings: int = 0
    infos: int = 0


class QASummary(BaseModel):
    """Summary of QA evaluation for acceptance gating."""

    doc_id: str
    total_issues: int = 0
    errors: int = 0
    warnings: int = 0
    infos: int = 0
    accepted: bool = True
    gate_skipped: bool = False
    rejection_reasons: list[str] = Field(default_factory=list)
    by_category: list[CategoryBreakdown] = Field(default_factory=list)


class QADelta(BaseModel):
    """Comparison between current and baseline QA runs."""

    doc_id: str
    new_issues: list[str] = Field(default_factory=list)
    resolved_issues: list[str] = Field(default_factory=list)
    unchanged_issues: list[str] = Field(default_factory=list)
    regression: bool = False
