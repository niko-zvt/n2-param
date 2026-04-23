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


def bjh_series(rows: Sequence[BJHDesorptionRow], field: BJHSeries) -> list[float]:
    """
    Extract one column from the BJH desorption distribution table.

    Args:
        rows: Parsed BJH rows.
        field: Column selector.

    Returns:
        Numeric sequence matching ``rows`` order.

    Raises:
        ValueError: If field is unknown.
    """
    result: list[float] = []
    for row in rows:
        if field == "average_diameter_a":
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
