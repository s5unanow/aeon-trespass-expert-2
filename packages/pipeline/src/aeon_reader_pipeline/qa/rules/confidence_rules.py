"""QA rules for page confidence and fallback-routing decisions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from aeon_reader_pipeline.models.ir_models import PageRecord
from aeon_reader_pipeline.models.qa_models import IssueLocation, QAIssue

if TYPE_CHECKING:
    from aeon_reader_pipeline.models.enrich_models import NavigationTree


class LowConfidencePageRule:
    """Flag pages that were routed away from semantic rendering.

    Reports hybrid pages as warnings and facsimile pages as info
    so operators can investigate extraction quality.
    """

    rule_id = "confidence.low_page"
    category = "confidence"

    def check(
        self,
        pages: list[PageRecord],
        navigation: NavigationTree | None,
    ) -> list[QAIssue]:
        issues: list[QAIssue] = []
        for record in pages:
            if record.render_mode == "hybrid":
                issues.append(
                    QAIssue(
                        rule_id=self.rule_id,
                        severity="warning",
                        category=self.category,
                        message=(f"Page {record.page_number} routed to hybrid rendering"),
                        location=IssueLocation(page_number=record.page_number),
                    )
                )
            elif record.render_mode == "facsimile":
                issues.append(
                    QAIssue(
                        rule_id=self.rule_id,
                        severity="info",
                        category=self.category,
                        message=(f"Page {record.page_number} routed to facsimile rendering"),
                        location=IssueLocation(page_number=record.page_number),
                    )
                )
        return issues
