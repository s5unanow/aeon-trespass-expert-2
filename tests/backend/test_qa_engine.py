"""Tests for the QA engine."""

from __future__ import annotations

from aeon_reader_pipeline.models.ir_models import PageRecord
from aeon_reader_pipeline.models.qa_models import QAIssue
from aeon_reader_pipeline.qa.engine import QAEngine
from aeon_reader_pipeline.stages.enrich_content import NavigationTree


class StubRule:
    """Test rule that returns pre-defined issues."""

    def __init__(self, rule_id: str, issues: list[QAIssue]) -> None:
        self.rule_id = rule_id
        self.category = "test"
        self._issues = issues

    def check(
        self,
        pages: list[PageRecord],
        navigation: NavigationTree | None,
    ) -> list[QAIssue]:
        return self._issues


def _make_issue(severity: str = "warning", rule_id: str = "test.rule") -> QAIssue:
    return QAIssue(
        rule_id=rule_id,
        severity=severity,  # type: ignore[arg-type]
        category="test",
        message="test issue",
    )


class TestQAEngine:
    def test_register_and_evaluate(self) -> None:
        engine = QAEngine()
        issue = _make_issue()
        engine.register(StubRule("r1", [issue]))
        result = engine.evaluate([])
        assert len(result) == 1
        assert result[0].rule_id == "test.rule"

    def test_evaluate_no_rules(self) -> None:
        engine = QAEngine()
        assert engine.evaluate([]) == []

    def test_evaluate_multiple_rules(self) -> None:
        engine = QAEngine()
        engine.register(StubRule("r1", [_make_issue(rule_id="a")]))
        engine.register(StubRule("r2", [_make_issue(rule_id="b")]))
        result = engine.evaluate([])
        assert len(result) == 2
        rule_ids = {i.rule_id for i in result}
        assert rule_ids == {"a", "b"}

    def test_summarize_accepted(self) -> None:
        engine = QAEngine()
        issues = [_make_issue("warning"), _make_issue("info")]
        summary = engine.summarize("doc-1", issues, max_warnings=50)
        assert summary.accepted is True
        assert summary.total_issues == 2
        assert summary.warnings == 1
        assert summary.infos == 1
        assert summary.errors == 0

    def test_summarize_rejected_on_errors(self) -> None:
        engine = QAEngine()
        issues = [_make_issue("error")]
        summary = engine.summarize("doc-1", issues)
        assert summary.accepted is False
        assert summary.errors == 1
        assert "error" in summary.rejection_reasons[0].lower()

    def test_summarize_rejected_on_too_many_warnings(self) -> None:
        engine = QAEngine()
        issues = [_make_issue("warning") for _ in range(10)]
        summary = engine.summarize("doc-1", issues, max_warnings=5)
        assert summary.accepted is False
        assert "warning" in summary.rejection_reasons[0].lower()

    def test_summarize_no_issues(self) -> None:
        engine = QAEngine()
        summary = engine.summarize("doc-1", [])
        assert summary.accepted is True
        assert summary.total_issues == 0

    def test_summarize_doc_id(self) -> None:
        engine = QAEngine()
        summary = engine.summarize("my-doc", [])
        assert summary.doc_id == "my-doc"
