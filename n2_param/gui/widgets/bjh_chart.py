"""
Matplotlib BJH desorption pore distribution plot.
"""

from __future__ import annotations

import logging

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PySide6.QtWidgets import QVBoxLayout, QWidget

from n2_param.gui.chart_config import (
    BJHSeries,
    SINGLE_CHART_DEFAULT_MARKER,
    SINGLE_CHART_DEFAULT_MARKERSIZE,
    XBJH_DEFAULT,
    YBJH_DEFAULT,
)
from n2_param.gui.chart_series import bjh_series
from n2_param.gui.file_session import OpenFileSession
from n2_param.gui.mpl_navigation_toolbar import N2ParamNavigationToolbar2QT
from n2_param.gui.mpl_util import bind_figure_size_to_canvas
from n2_param.i18n.translator import Translator

logger = logging.getLogger(__name__)


class BjhChartWidget(QWidget):
    """BJH (desorption): dV/dD over pore diameter D in nm, from the report table."""

    def __init__(self, session: OpenFileSession, translator: Translator, parent: QWidget | None = None) -> None:
        """
        Wire the widget to session updates and localization events.

        Args:
            session: Source of parsed BJH rows.
            translator: Localization helper for axis labels.
            parent: Optional Qt parent widget.
        """
        super().__init__(parent)
        self._session = session
        self._translator = translator
        self._x_field: BJHSeries = XBJH_DEFAULT
        self._y_field: BJHSeries = YBJH_DEFAULT

        layout = QVBoxLayout(self)
        self._figure = Figure(figsize=(5.5, 4.0), layout="tight")
        self._canvas = FigureCanvasQTAgg(self._figure)
        self._toolbar = N2ParamNavigationToolbar2QT(
            self._canvas,
            self,
            translator=translator,
        )
        layout.addWidget(self._toolbar)
        layout.addWidget(self._canvas, stretch=1)
        self._axes = self._figure.add_subplot(111)
        bind_figure_size_to_canvas(self._figure, self._canvas)

        session.parsed_changed.connect(self._render)
        translator.locale_changed.connect(self._render)
        self._render()

    def _axis_label(self, field: BJHSeries) -> str:
        """Translate axis titles for supported BJH columns."""
        mapping: dict[BJHSeries, str] = {
            "pore_diameter_avg_nm": "axis.pore_diameter_nm",
            "dV_dD_cc_g_nm": "axis.dV_dD",
            "average_diameter_a": "axis.avg_diameter",
            "incremental_pore_volume_cc_g": "axis.incr_vol",
            "cumulative_pore_volume_cc_g": "axis.cum_vol",
            "incremental_pore_area_sq_m_g": "axis.incr_area",
            "cumulative_pore_area_sq_m_g": "axis.cum_area",
        }
        return self._translator.tr_key(mapping[field])

    def _render(self) -> None:
        """Redraw using the latest BJH table."""
        self._axes.clear()
        report = self._session.parsed
        rows = report.bjh_desorption_rows
        title = self._translator.tr_key("chart.bjh.title")
        self._axes.set_title(title)
        if not rows:
            self._canvas.draw_idle()
            logger.info("BJH chart skipped: no rows")
            return

        try:
            xs = bjh_series(rows, self._x_field)
            ys = bjh_series(rows, self._y_field)
        except ValueError:
            logger.exception("Failed to extract BJH series")
            self._canvas.draw_idle()
            return

        self._axes.plot(
            xs,
            ys,
            color="#d62728",
            linewidth=1.5,
            marker=SINGLE_CHART_DEFAULT_MARKER,
            markersize=SINGLE_CHART_DEFAULT_MARKERSIZE,
            label=self._session.display_title(),
        )
        self._axes.set_xlabel(self._axis_label(self._x_field))
        self._axes.set_ylabel(self._axis_label(self._y_field))
        self._axes.grid(True, linestyle="--", linewidth=0.5, alpha=0.6)
        self._canvas.draw_idle()
