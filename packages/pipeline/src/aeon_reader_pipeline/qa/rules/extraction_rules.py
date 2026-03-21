"""QA rules for validating Architecture 3 extraction artifacts.

These rules validate structural invariants on region graphs and reading
order produced by ``collect_evidence``. They receive evidence via
constructor injection so the ``QARule`` protocol is preserved.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from aeon_reader_pipeline.models.evidence_models import CanonicalPageEvidence
from aeon_reader_pipeline.models.ir_models import PageRecord
from aeon_reader_pipeline.models.qa_models import IssueLocation, QAIssue

if TYPE_CHECKING:
    from aeon_reader_pipeline.models.enrich_models import NavigationTree


class RegionGraphValidityRule:
    """Validate region graph structural invariants.

    Checks for: duplicate region IDs, invalid edge references,
    and self-referential edges.
    """

    rule_id = "extraction.region_graph"
    category = "extraction"

    def __init__(self, evidence: dict[int, CanonicalPageEvidence]) -> None:
        self._evidence = evidence

    def check(
        self,
        pages: list[PageRecord],
        navigation: NavigationTree | None,
    ) -> list[QAIssue]:
        issues: list[QAIssue] = []
        for record in pages:
            ev = self._evidence.get(record.page_number)
            if ev is None or ev.region_graph is None:
                continue
            graph = ev.region_graph
            region_ids: set[str] = set()

            # Duplicate region IDs
            for region in graph.regions:
                if region.region_id in region_ids:
                    issues.append(
                        QAIssue(
                            rule_id=self.rule_id,
                            severity="error",
                            category=self.category,
                            message=f"Duplicate region ID: {region.region_id}",
                            location=IssueLocation(page_number=record.page_number),
                        )
                    )
                region_ids.add(region.region_id)

            # Edge validity
            for edge in graph.edges:
                if edge.src_region_id not in region_ids:
                    issues.append(
                        QAIssue(
                            rule_id=self.rule_id,
                            severity="error",
                            category=self.category,
                            message=(f"Edge source '{edge.src_region_id}' not in region graph"),
                            location=IssueLocation(page_number=record.page_number),
                        )
                    )
                if edge.dst_region_id not in region_ids:
                    issues.append(
                        QAIssue(
                            rule_id=self.rule_id,
                            severity="error",
                            category=self.category,
                            message=(
                                f"Edge destination '{edge.dst_region_id}' not in region graph"
                            ),
                            location=IssueLocation(page_number=record.page_number),
                        )
                    )
                if edge.src_region_id == edge.dst_region_id:
                    issues.append(
                        QAIssue(
                            rule_id=self.rule_id,
                            severity="error",
                            category=self.category,
                            message=(f"Self-referential edge on region '{edge.src_region_id}'"),
                            location=IssueLocation(page_number=record.page_number),
                        )
                    )
        return issues


class ReadingOrderValidityRule:
    """Validate reading order structural invariants.

    Checks for: contiguous sequence indices, references to valid
    region IDs, and unassigned regions.
    """

    rule_id = "extraction.reading_order"
    category = "extraction"

    def __init__(self, evidence: dict[int, CanonicalPageEvidence]) -> None:
        self._evidence = evidence

    def check(
        self,
        pages: list[PageRecord],
        navigation: NavigationTree | None,
    ) -> list[QAIssue]:
        issues: list[QAIssue] = []
        for record in pages:
            ev = self._evidence.get(record.page_number)
            if ev is None or ev.reading_order is None:
                continue
            order = ev.reading_order

            # Contiguous sequence indices (0..n-1)
            indices = sorted(e.sequence_index for e in order.entries)
            expected = list(range(len(order.entries)))
            if indices != expected:
                issues.append(
                    QAIssue(
                        rule_id=self.rule_id,
                        severity="error",
                        category=self.category,
                        message=(f"Non-contiguous sequence indices on page {record.page_number}"),
                        location=IssueLocation(page_number=record.page_number),
                        details={"indices": indices, "expected": expected},
                    )
                )

            # Region references must exist in the region graph
            if ev.region_graph is not None:
                graph_ids = {r.region_id for r in ev.region_graph.regions}
                for entry in order.entries:
                    if entry.region_id not in graph_ids:
                        issues.append(
                            QAIssue(
                                rule_id=self.rule_id,
                                severity="error",
                                category=self.category,
                                message=(
                                    f"Reading order references unknown region: '{entry.region_id}'"
                                ),
                                location=IssueLocation(page_number=record.page_number),
                            )
                        )

            # Unassigned regions (warning — may be intentional for furniture)
            if order.unassigned_region_ids:
                issues.append(
                    QAIssue(
                        rule_id=self.rule_id,
                        severity="warning",
                        category=self.category,
                        message=(
                            f"{len(order.unassigned_region_ids)} unassigned region(s)"
                            f" on page {record.page_number}"
                        ),
                        location=IssueLocation(page_number=record.page_number),
                        details={"unassigned_ids": order.unassigned_region_ids},
                    )
                )
        return issues
