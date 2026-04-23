"""
ASAP table export: build spreadsheet-like matrices from ``ParsedReport`` and write XLSX/CSV.

Responsibilities: EU-style number formatting (comma decimal), two sections (ANALYSIS LOG, BJH),
and horizontal layout for multiple samples in a single file.
"""

from __future__ import annotations

import csv
import logging
import math
from collections.abc import Callable, Sequence
from pathlib import Path

from openpyxl import Workbook

from n2_param.core.models import BJHDesorptionRow, ParsedReport
from n2_param.gui.chart_series import bjh_dVdD_cc_g_nm

logger = logging.getLogger(__name__)

LabelGet = Callable[[str], str]

# Common column count for a single sample (matches template: ANALYSIS block up to 8 + BJH 9 → use 9).
SHEET_COLS: int = 9


def _format_eu_scientific(x: float) -> str:
    """
    Format a non-zero float in scientific notation: mantissa with comma, ``E``, and signed exponent.

    Parameters:
        x: A finite, non-zero value in the range handled by the scientific branch.

    Returns:
        A string in the same style as typical ASAP CSV exports.
    """
    s = f"{x:.5E}"
    m, e = s.split("E", maxsplit=1)
    m = m.rstrip("0").rstrip(".")
    m = m.replace(".", ",")
    exp = int(e)
    if exp < 0:
        return f"{m}E-{abs(exp):02d}"
    return f"{m}E+{exp:02d}"


def _format_eu_float(x: float) -> str:
    """
    Render a float with comma as decimal separator; use scientific form for very small or large values.

    Parameters:
        x: A finite or non-finite value.

    Returns:
        A string, or the empty string for non-finite values.
    """
    if not math.isfinite(x):
        return ""
    if x == 0.0:
        return "0"
    ax = abs(x)
    if (ax < 1e-4) or (ax >= 1e6):
        return _format_eu_scientific(x)
    s = f"{x:.12f}"
    s = s.rstrip("0").rstrip(".")
    if s in ("-0", ""):
        s = "0"
    return s.replace(".", ",")


def _padded_row(cells: list[str], width: int) -> list[str]:
    """
    Return a list of length ``width``; pad on the right with empty strings, truncate on overflow.
    """
    if not isinstance(width, int) or width < 0:
        raise ValueError("width must be a non-negative int")
    out = list(cells) + [""] * (width - len(cells))
    return out[:width]


def bjh_data_cells(row: BJHDesorptionRow) -> list[str]:
    """
    One BJH data line as nine string cells: diameter range, volumes/areas, average nm, dV/dD.

    Parameters:
        row: A parsed BJH desorption row.

    Returns:
        Nine string cells, aligned with the export table headers.
    """
    lo, hi = row.pore_diameter_low_a, row.pore_diameter_high_a
    d_max, d_min = (max(lo, hi), min(lo, hi))
    avg_nm = row.average_diameter_a / 10.0
    dvd = bjh_dVdD_cc_g_nm(row)
    dvd_s = _format_eu_float(dvd) if math.isfinite(dvd) else ""
    return [
        _format_eu_float(d_max),
        _format_eu_float(d_min),
        _format_eu_float(row.average_diameter_a),
        _format_eu_float(row.incremental_pore_volume_cc_g),
        _format_eu_float(row.cumulative_pore_volume_cc_g),
        _format_eu_float(row.incremental_pore_area_sq_m_g),
        _format_eu_float(row.cumulative_pore_area_sq_m_g),
        _format_eu_float(avg_nm),
        dvd_s,
    ]


def build_sheet_rows(
    display_name: str,
    report: ParsedReport,
    tr: LabelGet,
) -> list[list[str]]:
    """
    Build a 2D matrix of strings (one sample) suitable for XLSX/CSV, matching the reference layout.

    Parameters:
        display_name: Sample or tab title for the first row.
        report: Structured ASAP data.
        tr: Lookup for ``export.*`` i18n keys (returns UTF-8 labels).

    Returns:
        A rectangular matrix with ``SHEET_COLS`` columns per row.
    """
    if not isinstance(display_name, str):
        raise TypeError("display_name must be str")
    if not isinstance(report, ParsedReport):
        raise TypeError("report must be ParsedReport")
    if not callable(tr):
        raise TypeError("tr must be callable")
    w = SHEET_COLS
    out: list[list[str]] = []

    def r(cells: list[str]) -> None:
        out.append(_padded_row(cells, w))

    r([tr("export.name_label"), display_name])
    r([tr("export.section"), tr("export.section_name_analysis")])
    r([""] * w)
    r(
        [
            tr("export.al_col_rel_p"),
            tr("export.al_col_pressure"),
            tr("export.al_col_volume"),
        ]
    )
    r(
        [
            "",
            tr("export.al_unit_pressure"),
            tr("export.al_unit_volume"),
        ]
    )
    r([""] * w)
    for ar in report.analysis_log:
        r(
            [
                _format_eu_float(ar.relative_pressure),
                _format_eu_float(ar.pressure_mmhg),
                _format_eu_float(ar.vol_adsorbed_cc_g_stp),
            ]
        )
    r([""] * w)
    r([tr("export.section"), tr("export.section_name_bjh")])
    r([""] * w)
    r(
        [
            tr("export.bjh_h1_pore_d_max"),
            tr("export.bjh_h1_pore_d_min"),
            tr("export.bjh_h1_pore_d_avg_a"),
            tr("export.bjh_h1_incr_vol"),
            tr("export.bjh_h1_cum_vol"),
            tr("export.bjh_h1_incr_area"),
            tr("export.bjh_h1_cum_area"),
            tr("export.bjh_h1_avg_nm"),
            tr("export.bjh_h1_dVdD"),
        ]
    )
    r(
        [
            tr("export.bjh_h2_a"),
            tr("export.bjh_h2_a"),
            tr("export.bjh_h2_a"),
            tr("export.bjh_h2_cc_g"),
            tr("export.bjh_h2_cc_g"),
            tr("export.bjh_h2_m2g"),
            tr("export.bjh_h2_m2g"),
            tr("export.bjh_h2_nm"),
            tr("export.bjh_h2_per_nm_g"),
        ]
    )
    r([""] * w)
    for br in report.bjh_desorption_rows:
        r(bjh_data_cells(br))
    return out


def merge_sheet_blocks(
    blocks: Sequence[Sequence[Sequence[str]]],
    gap_columns: int = 2,
) -> list[list[str]]:
    """
    Place multiple sample blocks side by side, separated by empty column gaps, row-aligned to max height.

    For each block, column width is the maximum row length in that block; every row in the block
    is right-padded to that width. Global height is the maximum of block row counts; shorter
    blocks are bottom-padded with empty rows.

    Parameters:
        blocks: Non-empty list of 2D string grids (one per sample).
        gap_columns: Number of empty columns between adjacent blocks (default: 2).

    Returns:
        A single 2D grid. Empty if ``blocks`` is empty.
    """
    if gap_columns < 0:
        raise ValueError("gap_columns must be non-negative")
    if not blocks:
        return []
    block_lists = [[list(r) for r in b] for b in blocks]
    widths: list[int] = [max((len(x) for x in bl), default=0) for bl in block_lists]
    h_max = max((len(b) for b in block_lists), default=0)
    padded: list[list[list[str]]] = []
    for bi, bl in enumerate(block_lists):
        w_i = widths[bi]
        pbi: list[list[str]] = []
        for r_i in range(h_max):
            if r_i < len(bl):
                row = bl[r_i] + [""] * (w_i - len(bl[r_i]))
                pbi.append(row[:w_i] if w_i else [])
            else:
                pbi.append([""] * w_i)
        padded.append(pbi)
    out: list[list[str]] = []
    for r_i in range(h_max):
        line: list[str] = []
        for bi, block in enumerate(padded):
            if bi > 0:
                line.extend([""] * gap_columns)
            line.extend(block[r_i])
        out.append(line)
    return out


def write_csv(path: Path, matrix: Sequence[Sequence[str]]) -> None:
    """
    Write a matrix to UTF-8 CSV with semicolon field delimiter; fields are always quoted.
    """
    if not isinstance(path, Path):
        raise TypeError("path must be pathlib.Path")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as fp:
        writer = csv.writer(fp, delimiter=";", quoting=csv.QUOTE_ALL, lineterminator="\n")
        for row in matrix:
            if not isinstance(row, Sequence):
                raise TypeError("matrix rows must be str sequences")
            row_list: list[str] = [c if c is not None else "" for c in row]
            writer.writerow(row_list)
    logger.info("Wrote CSV to %s", path)


def write_xlsx(path: Path, matrix: Sequence[Sequence[str]]) -> None:
    """
    Write a matrix to the first worksheet of a new .xlsx file (cell values as text).
    """
    if not isinstance(path, Path):
        raise TypeError("path must be pathlib.Path")
    path.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    if ws is None:
        raise RuntimeError("workbook has no active sheet")
    ws.title = "Export"
    for ri, row in enumerate(matrix, start=1):
        if not isinstance(row, Sequence):
            raise TypeError("matrix rows must be str sequences")
        for ci, cell in enumerate(row, start=1):
            val: str = cell if isinstance(cell, str) else ("" if cell is None else str(cell))
            ws.cell(ri, ci, value=val)
    wb.save(str(path))
    logger.info("Wrote XLSX to %s", path)


def export_parsed_to_file(
    target_path: Path,
    report: ParsedReport,
    display_name: str,
    label: LabelGet,
) -> None:
    """
    Write a single sample matrix to the path, choosing CSV or XLSX from the file suffix.

    Parameters:
        target_path: File path; extension must be ``.xlsx`` or ``.csv``.
        report: Parsed report.
        display_name: Name row text (e.g. sample id).
        label: i18n for ``export.*`` keys.

    Raises:
        TypeError: If a parameter is wrong.
        ValueError: If the extension is not supported.
    """
    if not isinstance(target_path, Path):
        raise TypeError("target_path must be pathlib.Path")
    if not isinstance(report, ParsedReport):
        raise TypeError("report must be ParsedReport")
    if not isinstance(display_name, str):
        raise TypeError("display_name must be str")
    if not callable(label):
        raise TypeError("label must be callable")
    suf = target_path.suffix.lower()
    matrix = build_sheet_rows(display_name, report, label)
    if suf == ".csv":
        write_csv(target_path, matrix)
        return
    if suf == ".xlsx":
        write_xlsx(target_path, matrix)
        return
    raise ValueError("unsupported file extension, expected .csv or .xlsx")
