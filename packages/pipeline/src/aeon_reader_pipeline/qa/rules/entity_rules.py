"""QA rules for validating entity structures (figures, tables, callouts)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from aeon_reader_pipeline.models.ir_models import (
    CalloutBlock,
    CaptionBlock,
    FigureBlock,
    PageRecord,
    TableBlock,
)
from aeon_reader_pipeline.models.qa_models import IssueLocation, QAIssue

if TYPE_CHECKING:
    from aeon_reader_pipeline.models.enrich_models import NavigationTree


class FigureCaptionLinkageRule:
    """Validate figure-caption cross-references.

    Checks that ``FigureBlock.caption_block_id`` references an existing
    ``CaptionBlock``, and ``CaptionBlock.parent_block_id`` references an
    existing figure or table block.
    """

    rule_id = "entity.figure_caption_linkage"
    category = "entity"

    def check(
        self,
        pages: list[PageRecord],
        navigation: NavigationTree | None,
    ) -> list[QAIssue]:
        issues: list[QAIssue] = []
        for record in pages:
            if record.render_mode == "facsimile":
                continue

            block_ids = {block.block_id for block in record.blocks}

            for block in record.blocks:
                if (
                    isinstance(block, FigureBlock)
                    and block.caption_block_id
                    and block.caption_block_id not in block_ids
                ):
                    issues.append(
                        QAIssue(
                            rule_id=self.rule_id,
                            severity="error",
                            category=self.category,
                            message=(
                                f"FigureBlock '{block.block_id}' references"
                                f" missing caption '{block.caption_block_id}'"
                            ),
                            location=IssueLocation(
                                page_number=record.page_number,
                                block_id=block.block_id,
                            ),
                        )
                    )
                if (
                    isinstance(block, CaptionBlock)
                    and block.parent_block_id
                    and block.parent_block_id not in block_ids
                ):
                    issues.append(
                        QAIssue(
                            rule_id=self.rule_id,
                            severity="error",
                            category=self.category,
                            message=(
                                f"CaptionBlock '{block.block_id}' references"
                                f" missing parent '{block.parent_block_id}'"
                            ),
                            location=IssueLocation(
                                page_number=record.page_number,
                                block_id=block.block_id,
                            ),
                        )
                    )
        return issues


class TableStructureRule:
    """Validate table block structural sanity.

    Checks that tables declaring dimensions have cells, and that cell
    indices fall within declared bounds.
    """

    rule_id = "entity.table_structure"
    category = "entity"

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
                if not isinstance(block, TableBlock):
                    continue

                # Tables declaring dimensions must have cells
                if (block.rows > 0 or block.cols > 0) and not block.cells:
                    issues.append(
                        QAIssue(
                            rule_id=self.rule_id,
                            severity="error",
                            category=self.category,
                            message=(
                                f"Table '{block.block_id}' declares"
                                f" {block.rows}x{block.cols} but has no cells"
                            ),
                            location=IssueLocation(
                                page_number=record.page_number,
                                block_id=block.block_id,
                            ),
                        )
                    )

                # Cell indices within declared bounds
                for cell in block.cells:
                    if block.rows > 0 and cell.row >= block.rows:
                        issues.append(
                            QAIssue(
                                rule_id=self.rule_id,
                                severity="error",
                                category=self.category,
                                message=(
                                    f"Table '{block.block_id}' cell row {cell.row}"
                                    f" exceeds declared rows ({block.rows})"
                                ),
                                location=IssueLocation(
                                    page_number=record.page_number,
                                    block_id=block.block_id,
                                ),
                            )
                        )
                    if block.cols > 0 and cell.col >= block.cols:
                        issues.append(
                            QAIssue(
                                rule_id=self.rule_id,
                                severity="error",
                                category=self.category,
                                message=(
                                    f"Table '{block.block_id}' cell col {cell.col}"
                                    f" exceeds declared cols ({block.cols})"
                                ),
                                location=IssueLocation(
                                    page_number=record.page_number,
                                    block_id=block.block_id,
                                ),
                            )
                        )
        return issues


class CalloutStructureRule:
    """Validate callout block structure.

    Flags callout blocks with empty content as warnings — they may
    indicate extraction failures.
    """

    rule_id = "entity.callout_structure"
    category = "entity"

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
                if isinstance(block, CalloutBlock) and not block.content:
                    issues.append(
                        QAIssue(
                            rule_id=self.rule_id,
                            severity="warning",
                            category=self.category,
                            message=f"Callout '{block.block_id}' has empty content",
                            location=IssueLocation(
                                page_number=record.page_number,
                                block_id=block.block_id,
                            ),
                        )
                    )
        return issues
