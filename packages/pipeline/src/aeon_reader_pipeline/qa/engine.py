"""QA engine that orchestrates rule evaluation across pipeline artifacts."""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, Protocol

from aeon_reader_pipeline.models.config_models import QAGateConfig
from aeon_reader_pipeline.models.ir_models import PageRecord
from aeon_reader_pipeline.models.qa_models import CategoryBreakdown, QAIssue, QASummary

if TYPE_CHECKING:
    from aeon_reader_pipeline.models.enrich_models import NavigationTree


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


def _build_category_breakdown(issues: list[QAIssue]) -> list[CategoryBreakdown]:
    """Aggregate issue counts by category."""
    counts: dict[str, dict[str, int]] = defaultdict(
        lambda: {"errors": 0, "warnings": 0, "infos": 0}
    )
    for issue in issues:
        bucket = counts[issue.category]
        if issue.severity == "error":
            bucket["errors"] += 1
        elif issue.severity == "warning":
            bucket["warnings"] += 1
        else:
            bucket["infos"] += 1
    return [CategoryBreakdown(category=cat, **vals) for cat, vals in sorted(counts.items())]


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
        *,
        gate_config: QAGateConfig | None = None,
    ) -> QASummary:
        """Build acceptance summary from issues.

        When *gate_config* is provided its thresholds are used instead of
        the legacy *max_warnings* parameter.
        """
        errors = sum(1 for i in issues if i.severity == "error")
        warnings = sum(1 for i in issues if i.severity == "warning")
        infos = sum(1 for i in issues if i.severity == "info")

        effective_max_errors = gate_config.max_errors if gate_config else 0
        effective_max_warnings = gate_config.max_warnings if gate_config else max_warnings

        rejection_reasons: list[str] = []
        if errors > effective_max_errors:
            rejection_reasons.append(f"{errors} error(s) exceed threshold ({effective_max_errors})")
        if warnings > effective_max_warnings:
            rejection_reasons.append(
                f"{warnings} warnings exceed threshold ({effective_max_warnings})"
            )

        by_category = _build_category_breakdown(issues)

        return QASummary(
            doc_id=doc_id,
            total_issues=len(issues),
            errors=errors,
            warnings=warnings,
            infos=infos,
            accepted=len(rejection_reasons) == 0,
            rejection_reasons=rejection_reasons,
            by_category=by_category,
        )
