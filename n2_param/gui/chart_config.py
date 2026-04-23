"""
Configurable axis mappings for matplotlib views.

Defaults follow the ASAP workflow requested for stage 1 and can be swapped later.
"""

from __future__ import annotations

from typing import Literal

# Columns (ANALYSIS LOG); default pair plot: X = relative pressure (P/p₀), Y = adsorbed volume.
AnalysisLogField = Literal[
    "relative_pressure",
    "pressure_mmhg",
    "vol_adsorbed_cc_g_stp",
]

BJHSeries = Literal[
    "pore_diameter_avg_nm",
    "dV_dD_cc_g_nm",
    "average_diameter_a",
    "incremental_pore_volume_cc_g",
    "cumulative_pore_volume_cc_g",
    "incremental_pore_area_sq_m_g",
    "cumulative_pore_area_sq_m_g",
]

X_ANALYSIS_LOG_PLOT_DEFAULT: AnalysisLogField = "relative_pressure"
Y_ANALYSIS_LOG_PLOT_DEFAULT: AnalysisLogField = "vol_adsorbed_cc_g_stp"

# BJH: X = average diameter (nm), Y = dV/dD in cm³·g⁻¹·nm⁻¹; see chart_series.bjh_series.
XBJH_DEFAULT: BJHSeries = "pore_diameter_avg_nm"
YBJH_DEFAULT: BJHSeries = "dV_dD_cc_g_nm"
