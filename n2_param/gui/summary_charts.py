"""
Multi-series matplotlib views that overlay all open ASAP reports in the Summary tab.

Each open file is one line; the parent view toggles line visibility with checkboxes.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from pathlib import Path

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure
from PySide6.QtWidgets import QVBoxLayout, QWidget

from n2_param.gui.chart_config import BJHSeries, IsothermSeries, XBJH_DEFAULT, XISOTHERM_DEFAULT, YBJH_DEFAULT, YISOTHERM_DEFAULT
from n2_param.gui.chart_series import analysis_series, bjh_series
from n2_param.gui.file_session import OpenFileSession
from n2_param.gui.mpl_util import bind_figure_size_to_canvas
from n2_param.i18n.translator import Translator

logger = logging.getLogger(__name__)

_MULTI_PLOT_COLORS: tuple[str, ...] = (
    "#1f77b4",
    "#ff7f0e",
    "#2ca02c",
    "#d62728",
    "#9467bd",
    "#8c564b",
    "#e377c2",
    "#7f7f7f",
    "#bcbd22",
    "#17becf",
)


class MultiIsothermChartWidget(QWidget):
    """Isotherm chart showing one curve per open file."""

    def __init__(self, translator: Translator, parent: QWidget | None = None) -> None:
        """
        Build a combined isotherm plot shell.

        Args:
            translator: Localized axis and title strings.
            parent: Optional Qt parent.
        """
        super().__init__(parent)
        self._translator = translator
        self._x_field: IsothermSeries = XISOTHERM_DEFAULT
        self._y_field: IsothermSeries = YISOTHERM_DEFAULT
        self._sessions: tuple[OpenFileSession, ...] = ()
        self._visible: Callable[[Path], bool] = lambda _p: True

        layout = QVBoxLayout(self)
        self._figure = Figure(figsize=(5.5, 4.0), layout="tight")
        self._canvas = FigureCanvasQTAgg(self._figure)
        self._toolbar = NavigationToolbar2QT(self._canvas, self)
        layout.addWidget(self._toolbar)
        layout.addWidget(self._canvas, stretch=1)
        self._axes = self._figure.add_subplot(111)
        bind_figure_size_to_canvas(self._figure, self._canvas)

        translator.locale_changed.connect(self._render)
        self._render()

    def set_sessions(self, sessions: Sequence[OpenFileSession], is_visible: Callable[[Path], bool]) -> None:
        """
        Replace the session list and visibility predicate, then re-subscribe to updates.

        Args:
            sessions: All open per-file sessions to plot.
            is_visible: For each file path, whether the curve should be drawn and exported.
        """
        if not callable(is_visible):
            raise TypeError("is_visible must be a callable")
        for previous in self._sessions:
            try:
                previous.parsed_changed.disconnect(self._render)
            except TypeError:
                logger.debug("Isotherm: parsed_changed already disconnected for %s", previous.path)
        self._sessions = tuple(sessions)
        self._visible = is_visible
        for s in self._sessions:
            s.parsed_changed.connect(self._render)
        self._render()

    def set_path_visibility(self, is_visible: Callable[[Path], bool]) -> None:
        """
        Update the visibility function without changing the session set.

        Args:
            is_visible: Predicate for drawing each path.
        """
        if not callable(is_visible):
            raise TypeError("is_visible must be a callable")
        self._visible = is_visible
        self._render()

    def _axis_label(self, field: IsothermSeries) -> str:
        """Translate isotherm axis title for the selected field."""
        mapping: dict[IsothermSeries, str] = {
            "relative_pressure": "axis.relative_pressure",
            "pressure_mmhg": "axis.pressure_mmhg",
            "vol_adsorbed_cc_g_stp": "axis.vol_adsorbed",
        }
        return self._translator.tr_key(mapping[field])

    def _render(self) -> None:
        """Plot one line per session when the path is selected as visible."""
        self._axes.clear()
        title = self._translator.tr_key("chart.isotherm.title")
        self._axes.set_title(title)
        if not self._sessions:
            self._canvas.draw_idle()
            return
        for idx, session in enumerate(self._sessions):
            path = session.path
            if not self._visible(path):
                continue
            report = session.parsed
            rows = report.analysis_log
            if not rows:
                continue
            try:
                xs = analysis_series(rows, self._x_field)
                ys = analysis_series(rows, self._y_field)
            except ValueError:
                logger.exception("Multi isotherm: series extraction failed for %s", path)
                continue
            color = _MULTI_PLOT_COLORS[idx % len(_MULTI_PLOT_COLORS)]
            self._axes.plot(xs, ys, color=color, linewidth=1.2)
        self._axes.set_xlabel(self._axis_label(self._x_field))
        self._axes.set_ylabel(self._axis_label(self._y_field))
        self._axes.grid(True, linestyle="--", linewidth=0.5, alpha=0.6)
        self._canvas.draw_idle()


class MultiBjhChartWidget(QWidget):
    """BJH desorption distribution plot with one curve per open file."""

    def __init__(self, translator: Translator, parent: QWidget | None = None) -> None:
        """
        Build a combined BJH plot shell.

        Args:
            translator: Localized axis and title strings.
            parent: Optional Qt parent.
        """
        super().__init__(parent)
        self._translator = translator
        self._x_field: BJHSeries = XBJH_DEFAULT
        self._y_field: BJHSeries = YBJH_DEFAULT
        self._sessions: tuple[OpenFileSession, ...] = ()
        self._visible: Callable[[Path], bool] = lambda _p: True

        layout = QVBoxLayout(self)
        self._figure = Figure(figsize=(5.5, 4.0), layout="tight")
        self._canvas = FigureCanvasQTAgg(self._figure)
        self._toolbar = NavigationToolbar2QT(self._canvas, self)
        layout.addWidget(self._toolbar)
        layout.addWidget(self._canvas, stretch=1)
        self._axes = self._figure.add_subplot(111)
        bind_figure_size_to_canvas(self._figure, self._canvas)

        translator.locale_changed.connect(self._render)
        self._render()

    def set_sessions(self, sessions: Sequence[OpenFileSession], is_visible: Callable[[Path], bool]) -> None:
        """
        Replace the session list and re-subscribe to BJH data updates.

        Args:
            sessions: All open per-file sessions to plot.
            is_visible: Predicate to draw a given path.
        """
        if not callable(is_visible):
            raise TypeError("is_visible must be a callable")
        for previous in self._sessions:
            try:
                previous.parsed_changed.disconnect(self._render)
            except TypeError:
                logger.debug("BJH: parsed_changed already disconnected for %s", previous.path)
        self._sessions = tuple(sessions)
        self._visible = is_visible
        for s in self._sessions:
            s.parsed_changed.connect(self._render)
        self._render()

    def set_path_visibility(self, is_visible: Callable[[Path], bool]) -> None:
        """
        Update the visibility function without re-binding session signals.

        Args:
            is_visible: Predicate for drawing each path.
        """
        if not callable(is_visible):
            raise TypeError("is_visible must be a callable")
        self._visible = is_visible
        self._render()

    def _axis_label(self, field: BJHSeries) -> str:
        """Translate BJH axis label for a column."""
        mapping: dict[BJHSeries, str] = {
            "average_diameter_a": "axis.avg_diameter",
            "incremental_pore_volume_cc_g": "axis.incr_vol",
            "cumulative_pore_volume_cc_g": "axis.cum_vol",
            "incremental_pore_area_sq_m_g": "axis.incr_area",
            "cumulative_pore_area_sq_m_g": "axis.cum_area",
        }
        return self._translator.tr_key(mapping[field])

    def _render(self) -> None:
        """Plot BJH for each visible file."""
        self._axes.clear()
        title = self._translator.tr_key("chart.bjh.title")
        self._axes.set_title(title)
        if not self._sessions:
            self._canvas.draw_idle()
            return
        for idx, session in enumerate(self._sessions):
            path = session.path
            if not self._visible(path):
                continue
            report = session.parsed
            rows = report.bjh_desorption_rows
            if not rows:
                continue
            try:
                xs = bjh_series(rows, self._x_field)
                ys = bjh_series(rows, self._y_field)
            except ValueError:
                logger.exception("Multi BJH: series extraction failed for %s", path)
                continue
            color = _MULTI_PLOT_COLORS[idx % len(_MULTI_PLOT_COLORS)]
            self._axes.plot(
                xs,
                ys,
                color=color,
                linewidth=1.2,
            )
        self._axes.set_xlabel(self._axis_label(self._x_field))
        self._axes.set_ylabel(self._axis_label(self._y_field))
        self._axes.grid(True, linestyle="--", linewidth=0.5, alpha=0.6)
        self._canvas.draw_idle()
