"""QA engine that orchestrates rule evaluation across pipeline artifacts."""

from __future__ import annotations

from typing import Protocol

from aeon_reader_pipeline.models.ir_models import PageRecord
from aeon_reader_pipeline.models.qa_models import QAIssue, QASummary
from aeon_reader_pipeline.stages.enrich_content import NavigationTree


class QARule(Protocol):
    """Protocol for a QA rule function.

    Rules must be pure functions — no side effects, no I/O.
    """

    rule_id: str
    category: str

    def check(
        self,
        pages: list[PageRecord],
        navigation: NavigationTree | None,
    ) -> list[QAIssue]: ...


class QAEngine:
    """Runs registered QA rules and produces a summary."""

    def __init__(self) -> None:
        self._rules: list[QARule] = []

    def register(self, rule: QARule) -> None:
        """Register a rule for evaluation."""
        self._rules.append(rule)

    def evaluate(
        self,
        pages: list[PageRecord],
        navigation: NavigationTree | None = None,
    ) -> list[QAIssue]:
        """Run all registered rules and collect issues."""
        issues: list[QAIssue] = []
        for rule in self._rules:
            rule_issues = rule.check(pages, navigation)
            issues.extend(rule_issues)
        return issues

    def summarize(
        self,
        doc_id: str,
        issues: list[QAIssue],
        max_warnings: int = 50,
    ) -> QASummary:
        """Build acceptance summary from issues."""
        errors = sum(1 for i in issues if i.severity == "error")
        warnings = sum(1 for i in issues if i.severity == "warning")
        infos = sum(1 for i in issues if i.severity == "info")

        rejection_reasons: list[str] = []
        if errors > 0:
            rejection_reasons.append(f"{errors} error(s) found")
        if warnings > max_warnings:
            rejection_reasons.append(f"{warnings} warnings exceed threshold ({max_warnings})")

        return QASummary(
            doc_id=doc_id,
            total_issues=len(issues),
            errors=errors,
            warnings=warnings,
            infos=infos,
            accepted=len(rejection_reasons) == 0,
            rejection_reasons=rejection_reasons,
        )
