"""Tests for ErrorCollector and stage error aggregation."""

from __future__ import annotations

import threading

from aeon_reader_pipeline.stage_framework.context import ErrorCollector


class TestErrorCollector:
    def test_record_and_collect(self) -> None:
        ec = ErrorCollector()
        ec.record("ValueError", "bad input", page=1)
        ec.record("IOError", "disk full", path="/tmp")

        errors = ec.collect()
        assert len(errors) == 2
        assert errors[0].error_type == "ValueError"
        assert errors[0].message == "bad input"
        assert errors[0].context == {"page": 1}
        assert errors[1].error_type == "IOError"
        assert errors[1].context == {"path": "/tmp"}

    def test_collect_clears_errors(self) -> None:
        ec = ErrorCollector()
        ec.record("Error", "test")
        assert ec.count == 1
        ec.collect()
        assert ec.count == 0

    def test_count_property(self) -> None:
        ec = ErrorCollector()
        assert ec.count == 0
        ec.record("E", "m")
        assert ec.count == 1

    def test_thread_safety(self) -> None:
        ec = ErrorCollector()
        barrier = threading.Barrier(4)

        def writer(tid: int) -> None:
            barrier.wait()
            for i in range(50):
                ec.record("Error", f"t{tid}-{i}")

        threads = [threading.Thread(target=writer, args=(t,)) for t in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        errors = ec.collect()
        assert len(errors) == 200
