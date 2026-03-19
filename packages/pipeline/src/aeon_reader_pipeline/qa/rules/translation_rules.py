"""QA rules for checking translation completeness and consistency."""

from __future__ import annotations

from typing import TYPE_CHECKING

from aeon_reader_pipeline.models.ir_models import PageRecord, TextRun
from aeon_reader_pipeline.models.qa_models import IssueLocation, QAIssue

if TYPE_CHECKING:
    from aeon_reader_pipeline.models.enrich_models import NavigationTree


class MissingTranslationRule:
    """Flag text nodes that have source text but no translation."""

    rule_id = "translation.missing"
    category = "translation"

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
                    if isinstance(node, TextRun) and node.text.strip() and not node.ru_text:
                        issues.append(
                            QAIssue(
                                rule_id=self.rule_id,
                                severity="warning",
                                category=self.category,
                                message=f"Missing translation: {node.text[:60]}",
                                location=IssueLocation(
                                    page_number=record.page_number,
                                    block_id=block.block_id,
                                ),
                            )
                        )
        return issues


class EmptyTranslationRule:
    """Flag text nodes where translation exists but is empty."""

    rule_id = "translation.empty"
    category = "translation"

    def check(
        self,
        pages: list[PageRecord],
        navigation: NavigationTree | None,
    ) -> list[QAIssue]:
        issues: list[QAIssue] = []
        for record in pages:
            for block in record.blocks:
                if not hasattr(block, "content"):
                    continue
                for node in block.content:
                    if (
                        isinstance(node, TextRun)
                        and node.text.strip()
                        and node.ru_text is not None
                        and not node.ru_text.strip()
                    ):
                        issues.append(
                            QAIssue(
                                rule_id=self.rule_id,
                                severity="error",
                                category=self.category,
                                message=f"Empty translation for: {node.text[:60]}",
                                location=IssueLocation(
                                    page_number=record.page_number,
                                    block_id=block.block_id,
                                ),
                            )
                        )
        return issues
