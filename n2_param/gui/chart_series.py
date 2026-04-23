"""
Map ParsedReport tables to numeric series for plotting.
"""

from __future__ import annotations

from collections.abc import Sequence

from n2_param.core.models import AnalysisLogRow, BJHDesorptionRow
from n2_param.gui.chart_config import AnalysisLogField, BJHSeries


def analysis_series(rows: Sequence[AnalysisLogRow], field: AnalysisLogField) -> list[float]:
    """
    Extract one column from the analysis log as floats.

    Args:
        rows: Parsed rows from the first ANALYSIS LOG block.
        field: Column selector.

    Returns:
        Numeric sequence matching ``rows`` order.

    Raises:
        ValueError: If field is unknown.
    """
    result: list[float] = []
    for row in rows:
        if field == "relative_pressure":
            result.append(row.relative_pressure)
        elif field == "pressure_mmhg":
            result.append(row.pressure_mmhg)
        elif field == "vol_adsorbed_cc_g_stp":
            result.append(row.vol_adsorbed_cc_g_stp)
        else:
            raise ValueError(f"unknown ANALYSIS LOG plot field: {field}")
    return result


def _pore_diameter_endpoints_a(row: BJHDesorptionRow) -> tuple[float, float]:
    """
    Return the minimum and maximum of the PORE DIAMETER RANGE in angstroms.

    Args:
        row: Parsed BJH table row; the first two data columns are the two range ends.

    Returns:
        ``(C_min, B_max)`` with C_min = min(ends) and B_max = max(ends), both in Å.
    """
    lo = float(row.pore_diameter_low_a)
    hi = float(row.pore_diameter_high_a)
    c_min = min(lo, hi)
    b_max = max(lo, hi)
    return (c_min, b_max)


def bjh_dVdD_cc_g_nm(row: BJHDesorptionRow) -> float:
    """
    dV/dD in cm³·g⁻¹·nm⁻¹: (A * 10) / (B - C) with A incremental V (cc/g), B, C in Å.
    """
    a = float(row.incremental_pore_volume_cc_g)
    c_min, b_max = _pore_diameter_endpoints_a(row)
    w_a = b_max - c_min
    if w_a <= 0.0:
        return float("nan")
    return (a * 10.0) / w_a


def bjh_series(rows: Sequence[BJHDesorptionRow], field: BJHSeries) -> list[float]:
    """
    Extract one column or a derived BJH series for plotting.

    Pore axis D (nm) is AVERAGE DIAMETER (Å) / 10. Derivative dV/dD uses incremental
    pore volume and the diameter range (MAX − MIN) in Å, per the ASAP table.

    Args:
        rows: Parsed BJH rows.
        field: Column selector or derived name.

    Returns:
        One float per row (or NaN where dV/dD is undefined).

    Raises:
        ValueError: If field is unknown.
    """
    result: list[float] = []
    for row in rows:
        if field == "pore_diameter_avg_nm":
            result.append(float(row.average_diameter_a) / 10.0)
        elif field == "dV_dD_cc_g_nm":
            result.append(bjh_dVdD_cc_g_nm(row))
        elif field == "average_diameter_a":
            result.append(row.average_diameter_a)
        elif field == "incremental_pore_volume_cc_g":
            result.append(row.incremental_pore_volume_cc_g)
        elif field == "cumulative_pore_volume_cc_g":
            result.append(row.cumulative_pore_volume_cc_g)
        elif field == "incremental_pore_area_sq_m_g":
            result.append(row.incremental_pore_area_sq_m_g)
        elif field == "cumulative_pore_area_sq_m_g":
            result.append(row.cumulative_pore_area_sq_m_g)
        else:
            raise ValueError(f"unknown BJH field: {field}")
    return result
