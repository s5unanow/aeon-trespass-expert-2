"""Tests for table extraction, normalization, and export."""

from __future__ import annotations

import pytest

from aeon_reader_pipeline.models.extract_models import (
    BBox,
    ExtractedPage,
    RawTableCell,
    RawTableInfo,
)
from aeon_reader_pipeline.models.ir_models import TableBlock, TableCell
from aeon_reader_pipeline.models.site_bundle_models import BundleTableBlock, BundleTableCell


class TestRawTableModels:
    """Test extract-level table models."""

    def test_raw_table_cell_defaults(self) -> None:
        cell = RawTableCell(row=0, col=0, text="hello")
        assert cell.row_span == 1
        assert cell.col_span == 1

    def test_raw_table_info_with_cells(self) -> None:
        cells = [
            RawTableCell(row=0, col=0, text="Name"),
            RawTableCell(row=0, col=1, text="Value"),
            RawTableCell(row=1, col=0, text="HP"),
            RawTableCell(row=1, col=1, text="10"),
        ]
        table = RawTableInfo(
            table_index=0,
            rows=2,
            cols=2,
            bbox=BBox(x0=0, y0=0, x1=100, y1=50),
            cells=cells,
        )
        assert table.rows == 2
        assert table.cols == 2
        assert len(table.cells) == 4
        assert table.cells[0].text == "Name"

    def test_extracted_page_includes_tables(self) -> None:
        page = ExtractedPage(
            page_number=1,
            width_pt=612,
            height_pt=792,
            tables=[
                RawTableInfo(
                    table_index=0,
                    rows=1,
                    cols=1,
                    bbox=BBox(x0=0, y0=0, x1=100, y1=50),
                    cells=[RawTableCell(row=0, col=0, text="x")],
                )
            ],
        )
        assert len(page.tables) == 1

    def test_extracted_page_tables_default_empty(self) -> None:
        page = ExtractedPage(page_number=1, width_pt=612, height_pt=792)
        assert page.tables == []


class TestIRTableModels:
    """Test IR-level table models."""

    def test_table_cell_model(self) -> None:
        cell = TableCell(row=1, col=2, text="data")
        assert cell.row == 1
        assert cell.col == 2
        assert cell.text == "data"
        assert cell.row_span == 1
        assert cell.col_span == 1

    def test_table_block_with_cells(self) -> None:
        cells = [
            TableCell(row=0, col=0, text="A"),
            TableCell(row=0, col=1, text="B"),
        ]
        block = TableBlock(block_id="tbl-1", rows=1, cols=2, cells=cells)
        assert block.kind == "table"
        assert len(block.cells) == 2
        assert block.cells[0].text == "A"

    def test_table_block_empty_cells_default(self) -> None:
        block = TableBlock(block_id="tbl-1", rows=3, cols=4)
        assert block.cells == []


class TestBundleTableModels:
    """Test bundle-level table models."""

    def test_bundle_table_cell(self) -> None:
        cell = BundleTableCell(row=0, col=0, text="header")
        assert cell.row_span == 1
        assert cell.col_span == 1

    def test_bundle_table_block_with_cells(self) -> None:
        block = BundleTableBlock(
            block_id="tbl-1",
            rows=2,
            cols=2,
            cells=[
                BundleTableCell(row=0, col=0, text="A"),
                BundleTableCell(row=0, col=1, text="B"),
                BundleTableCell(row=1, col=0, text="C"),
                BundleTableCell(row=1, col=1, text="D"),
            ],
        )
        assert len(block.cells) == 4
        assert block.cells[2].text == "C"

    def test_bundle_table_block_roundtrip(self) -> None:
        block = BundleTableBlock(
            block_id="tbl-1",
            rows=1,
            cols=1,
            cells=[BundleTableCell(row=0, col=0, text="x")],
        )
        data = block.model_dump()
        restored = BundleTableBlock.model_validate(data)
        assert restored.cells[0].text == "x"


class TestTableExportConversion:
    """Test table conversion from IR to bundle in export stage."""

    def test_convert_table_block_with_cells(self) -> None:
        from aeon_reader_pipeline.stages.export_site_bundle import _convert_block

        ir_block = TableBlock(
            block_id="tbl-1",
            rows=2,
            cols=2,
            cells=[
                TableCell(row=0, col=0, text="Name"),
                TableCell(row=0, col=1, text="Value"),
                TableCell(row=1, col=0, text="HP"),
                TableCell(row=1, col=1, text="10"),
            ],
        )
        bundle = _convert_block(ir_block)
        assert isinstance(bundle, BundleTableBlock)
        assert len(bundle.cells) == 4
        assert bundle.cells[0].text == "Name"
        assert bundle.cells[3].text == "10"

    def test_convert_table_block_empty(self) -> None:
        from aeon_reader_pipeline.stages.export_site_bundle import _convert_block

        ir_block = TableBlock(block_id="tbl-2", rows=3, cols=4)
        bundle = _convert_block(ir_block)
        assert isinstance(bundle, BundleTableBlock)
        assert bundle.rows == 3
        assert bundle.cols == 4
        assert bundle.cells == []
