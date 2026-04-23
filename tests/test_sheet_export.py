"""
Unit tests for sheet layout, number formatting, and horizontal merge.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from n2_param.core.parsing.asap_report_parser import AsapReportParser
from n2_param.export.sheet_export import (
    SHEET_COLS,
    bjh_data_cells,
    build_sheet_rows,
    export_parsed_to_file,
    merge_sheet_blocks,
    _format_eu_float,
    _padded_row,
)
from n2_param.gui.chart_series import bjh_dVdD_cc_g_nm


def tr_echo(key: str) -> str:
    """i18n stub: return the key to avoid a dependency on the CSV bundle in tests."""
    if not key:
        raise ValueError("key must be non-empty")
    return key


def test_format_eu_comma_and_scientific() -> None:
    assert _format_eu_float(0.0047) == "0,0047"
    assert _format_eu_float(0.0) == "0"
    s = _format_eu_float(1e-5)
    assert "E" in s
    s2 = _format_eu_float(1.23e-5)
    assert "E" in s2
    assert "," in s2.split("E", maxsplit=1)[0]


def test_padded_row_width() -> None:
    assert _padded_row(["a", "b"], 5) == ["a", "b", "", "", ""]


def test_merge_two_blocks_with_gap() -> None:
    block_a: list[list[str]] = [["a1", "a2"], ["b1", "b2"]]
    block_b: list[list[str]] = [["X", "Y", "Z"], ["U", "V", "W"]]
    merged = merge_sheet_blocks([block_a, block_b], gap_columns=2)
    assert len(merged) == 2
    assert len(merged[0]) == 2 + 2 + 3
    assert merged[0][:2] == ["a1", "a2"]
    assert merged[0][2:4] == ["", ""]
    assert merged[0][4:7] == ["X", "Y", "Z"]


def test_merge_different_row_heights() -> None:
    short: list[list[str]] = [["x", "y"]]
    long_block: list[list[str]] = [["1"], ["2"], ["3"]]
    merged = merge_sheet_blocks([short, long_block], gap_columns=2)
    assert len(merged) == 3
    assert merged[1][0:2] == ["", ""]  # first block padded down
    assert merged[1][-1] == "2"


def test_build_sheet_row_shape() -> None:
    path = Path(__file__).resolve().parents[1] / "samples" / "C-Zn-AHC.394"
    text = path.read_text(encoding="utf-8", errors="replace")
    report = AsapReportParser().parse(text)
    name = "TestSample"
    rows = build_sheet_rows(name, report, tr_echo)
    assert all(len(r) == SHEET_COLS for r in rows)
    assert name in (rows[0][1] or "")


def test_bjh_dvd_matches_series_fn() -> None:
    path = Path(__file__).resolve().parents[1] / "samples" / "C-Zn-AHC.394"
    text = path.read_text(encoding="utf-8", errors="replace")
    report = AsapReportParser().parse(text)
    r0 = report.bjh_desorption_rows[0]
    c = bjh_data_cells(r0)
    d_ref = bjh_dVdD_cc_g_nm(r0)
    if math.isfinite(d_ref):
        assert c[-1] == _format_eu_float(d_ref)


def test_export_parsed_rejects_wrong_ext(tmp_path: Path) -> None:
    path = Path(__file__).resolve().parents[1] / "samples" / "C-Zn-AHC.394"
    text = path.read_text(encoding="utf-8", errors="replace")
    report = AsapReportParser().parse(text)
    bad = tmp_path / "out.txt"
    with pytest.raises(ValueError, match="unsupported file extension"):
        export_parsed_to_file(bad, report, "S", tr_echo)
    out = tmp_path / "a.csv"
    export_parsed_to_file(out, report, "N", tr_echo)
    assert out.is_file() and ";" in out.read_text(encoding="utf-8-sig")
