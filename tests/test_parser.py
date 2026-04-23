"""
Regression tests for ASAP parsing across bundled sample exports.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from n2_param.core.parsing.asap_report_parser import (
    AsapReportParser,
    _ANALYSIS_LOG_LINE,
    _DATA_ROW_RE,
)
from n2_param.gui.chart_series import bjh_dVdD_cc_g_nm

_SAMPLES_DIR = Path(__file__).resolve().parents[1] / "samples"


def _legacy_first_segment_analysis_log_row_count(text: str) -> int:
    """Count ANALYSIS LOG rows using only the text before the second section header."""
    matches = list(_ANALYSIS_LOG_LINE.finditer(text))
    if not matches:
        return 0
    block_end = matches[1].start() if len(matches) > 1 else len(text)
    block = text[matches[0].end() : block_end]
    header_match = re.search(
        r"RELATIVE\s+PRESSURE.*?VOL ADSORBED",
        block,
        flags=re.DOTALL,
    )
    if header_match is None:
        return 0
    count = 0
    for raw_line in block[header_match.end() :].splitlines():
        if _DATA_ROW_RE.match(raw_line.rstrip("\n")):
            count += 1
    return count


@pytest.mark.parametrize(
    "filename",
    [
        "Cs-Zn-NaOH.003",
        "C-Zn-AHC.394",
        "Cs-Zn-AHC.004",
        "Cs-Zn-AHC-Am.002",
        "C-Zn-NaOH.393",
        "C-Zn-Com.391",
        "C-Zn-AHC-Am.392",
    ],
)
def test_parse_samples_parse_without_fatal_errors(filename: str) -> None:
    """Each sample should parse and expose core tables."""
    path = _SAMPLES_DIR / filename
    text = path.read_text(encoding="utf-8", errors="replace")
    report = AsapReportParser().parse(text)
    assert report.sample_id is not None
    assert len(report.analysis_log) > 0
    assert len(report.bjh_desorption_rows) > 0
    assert report.summary.bjh_cumulative_desorption_surface_area_sq_m_g is not None
    assert report.summary.bjh_cumulative_desorption_pore_volume_cc_g is not None
    assert report.summary.bjh_desorption_average_pore_diameter_a is not None


def test_c_zn_ahc_394_merges_analysis_log_across_pages() -> None:
    """Multi-page ANALYSIS LOG continuations must append after the page break."""
    path = _SAMPLES_DIR / "C-Zn-AHC.394"
    text = path.read_text(encoding="utf-8", errors="replace")
    report = AsapReportParser().parse(text)
    legacy_first_only = _legacy_first_segment_analysis_log_row_count(text)
    assert legacy_first_only > 0
    assert len(report.analysis_log) > legacy_first_only
    assert len(report.analysis_log) == 47


def test_bjh_dVdD_formulasample_row() -> None:
    """dV/dD = (A * 10) / (B - C) with A incremental volume, C_min–B_max from range (Å)."""
    path = _SAMPLES_DIR / "C-Zn-AHC-Am.392"
    text = path.read_text(encoding="utf-8", errors="replace")
    report = AsapReportParser().parse(text)
    assert len(report.bjh_desorption_rows) >= 2
    row1 = report.bjh_desorption_rows[1]
    a = 0.009009
    b_minus_c = 441.8 - 394.6
    expect = a * 10.0 / b_minus_c
    assert bjh_dVdD_cc_g_nm(row1) == pytest.approx(expect, rel=1e-5)


def test_cs_zn_naoh_numeric_snapshot() -> None:
    """Spot-check known values from Cs-Zn-NaOH.003."""
    path = _SAMPLES_DIR / "Cs-Zn-NaOH.003"
    text = path.read_text(encoding="utf-8", errors="replace")
    report = AsapReportParser().parse(text)
    assert report.sample_id == "Sc-66-2, Vaschenkov"
    assert report.summary.bjh_cumulative_desorption_surface_area_sq_m_g == pytest.approx(23.3907)
    assert report.summary.bjh_cumulative_desorption_pore_volume_cc_g == pytest.approx(0.091648)
    assert report.summary.bjh_desorption_average_pore_diameter_a == pytest.approx(156.7253)
