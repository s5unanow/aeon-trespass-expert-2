"""QA rules for validating symbol and icon references."""

from __future__ import annotations

from typing import TYPE_CHECKING

from aeon_reader_pipeline.models.ir_models import PageRecord, SymbolRef
from aeon_reader_pipeline.models.qa_models import IssueLocation, QAIssue

if TYPE_CHECKING:
    from aeon_reader_pipeline.models.enrich_models import NavigationTree


class SymbolAnchorValidityRule:
    """Validate symbol references in page content.

    Checks that every ``SymbolRef`` in semantic blocks has a non-empty
    ``symbol_id``. Empty symbol IDs indicate unclassified symbols that
    leaked into the final IR.
    """

    rule_id = "symbol.anchor_validity"
    category = "symbol"

    def check(
        self,
        pages: list[PageRecord],
        navigation: NavigationTree | None,
    ) -> list[QAIssue]:
        issues: list[QAIssue] = []
        for record in pages:
            if record.render_mode == "facsimile":
                continue
            for block in record.blocks:
                if not hasattr(block, "content"):
                    continue
                for node in block.content:
                    if isinstance(node, SymbolRef) and not node.symbol_id:
                        issues.append(
                            QAIssue(
                                rule_id=self.rule_id,
                                severity="error",
                                category=self.category,
                                message=(
                                    f"SymbolRef with empty symbol_id in block {block.block_id}"
                                ),
                                location=IssueLocation(
                                    page_number=record.page_number,
                                    block_id=block.block_id,
                                ),
                            )
                        )
        return issues
