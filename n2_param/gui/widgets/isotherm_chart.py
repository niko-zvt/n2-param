"""
Matplotlib isotherm view driven by the first ANALYSIS LOG block.
"""

from __future__ import annotations

import logging

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from n2_param.gui.chart_config import (
    IsothermSeries,
    XISOTHERM_DEFAULT,
    YISOTHERM_DEFAULT,
)
from n2_param.gui.chart_series import analysis_series
from n2_param.gui.mpl_util import bind_figure_size_to_canvas
from n2_param.gui.file_session import OpenFileSession
from n2_param.i18n.translator import Translator

logger = logging.getLogger(__name__)


class IsothermChartWidget(QWidget):
    """Interactive line plot with zoom/pan toolbar."""

    def __init__(self, session: OpenFileSession, translator: Translator, parent: QWidget | None = None) -> None:
        """
        Build the chart shell and subscribe to parse updates.

        Args:
            session: Active file session providing ParsedReport updates.
            translator: Localization helper for axis labels.
            parent: Optional Qt parent widget.
        """
        super().__init__(parent)
        self._session = session
        self._translator = translator
        self._x_field: IsothermSeries = XISOTHERM_DEFAULT
        self._y_field: IsothermSeries = YISOTHERM_DEFAULT

        layout = QVBoxLayout(self)
        self._hint = QLabel("", self)
        layout.addWidget(self._hint)

        self._figure = Figure(figsize=(5.5, 4.0), layout="tight")
        self._canvas = FigureCanvasQTAgg(self._figure)
        self._toolbar = NavigationToolbar2QT(self._canvas, self)
        layout.addWidget(self._toolbar)
        layout.addWidget(self._canvas, stretch=1)
        self._axes = self._figure.add_subplot(111)
        bind_figure_size_to_canvas(self._figure, self._canvas)

        session.parsed_changed.connect(self._render)
        translator.locale_changed.connect(self._render)
        self._render()

    def _axis_label(self, field: IsothermSeries) -> str:
        """Translate axis titles based on selected series."""
        mapping = {
            "relative_pressure": "axis.relative_pressure",
            "pressure_mmhg": "axis.pressure_mmhg",
            "vol_adsorbed_cc_g_stp": "axis.vol_adsorbed",
        }
        key = mapping[field]
        return self._translator.tr_key(key)

    def _render(self) -> None:
        """Redraw plot using the latest ParsedReport snapshot."""
        self._axes.clear()
        report = self._session.parsed
        rows = report.analysis_log
        title = self._translator.tr_key("chart.isotherm.title")
        self._axes.set_title(title)
        if not rows:
            self._hint.setText("")
            self._canvas.draw_idle()
            logger.info("Isotherm chart skipped: no ANALYSIS LOG rows")
            return

        try:
            xs = analysis_series(rows, self._x_field)
            ys = analysis_series(rows, self._y_field)
        except ValueError:
            logger.exception("Failed to extract isotherm series")
            self._hint.setText("")
            self._canvas.draw_idle()
            return

        self._axes.plot(xs, ys, color="#1f77b4", linewidth=1.5)
        self._axes.set_xlabel(self._axis_label(self._x_field))
        self._axes.set_ylabel(self._axis_label(self._y_field))
        self._axes.grid(True, linestyle="--", linewidth=0.5, alpha=0.6)
        self._hint.setText("")
        self._canvas.draw_idle()
