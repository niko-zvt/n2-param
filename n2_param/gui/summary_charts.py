"""
Multi-series matplotlib views that overlay all open ASAP reports in the Summary tab.

Each file maps to a persistent Line2D: visibility and color are updated without clearing axes
so the zoom and pan (axis limits) stay in place; full rebuild only when data or the file set
changes, or on locale change for the chart chrome.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from pathlib import Path

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from PySide6.QtWidgets import QVBoxLayout, QWidget

from n2_param.gui.chart_config import (
    AnalysisLogField,
    BJHSeries,
    XBJH_DEFAULT,
    X_ANALYSIS_LOG_PLOT_DEFAULT,
    YBJH_DEFAULT,
    Y_ANALYSIS_LOG_PLOT_DEFAULT,
)
from n2_param.gui.chart_series import analysis_series, bjh_series
from n2_param.gui.file_session import OpenFileSession
from n2_param.gui.mpl_navigation_toolbar import N2ParamNavigationToolbar2QT
from n2_param.gui.mpl_util import bind_figure_size_to_canvas
from n2_param.i18n.translator import Translator

logger = logging.getLogger(__name__)

_DEFAULT_COLOR: str = "#1f77b4"

# Default cycle for new files in the Summary list (must stay in sync with the UI palette).
DEFAULT_CURVE_COLORS: tuple[str, ...] = (
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


def _default_color() -> str:
    """Return a non-empty line color for missing callbacks."""
    return _DEFAULT_COLOR


_LINE_W: float = 1.2


def _curve_legend_label(session: OpenFileSession) -> str:
    """
    Human-readable name for a matplotlib line (Sample ID, else file name).

    The Line2D ``label`` is shown in the navigation toolbar, legend, and replaces the
    default names like ``_line0`` / internal ``_child*``-style labels when not set.
    """
    if not isinstance(session, OpenFileSession):
        raise TypeError("session must be OpenFileSession")
    t = session.display_title()
    if isinstance(t, str) and t.strip():
        return t.strip()
    return session.path.name


def _curve_gid_for_path(path: Path) -> str:
    """
    Stable artist id (``Line2D.set_gid``) for the summary overlay for this path.

    Args:
        path: Absolute path to the open file.

    Returns:
        A short ASCII identifier safe for pickers and debugging.
    """
    if not isinstance(path, Path):
        raise TypeError("path must be pathlib.Path")
    return f"n2_param:summary:curve:{path.as_posix()}"


class MultiAnalysisLogChartWidget(QWidget):
    """Adsorbed volume vs. P/p₀: one line per file; visibility and color are incremental updates."""

    def __init__(self, translator: Translator, parent: QWidget | None = None) -> None:
        """
        Build the ANALYSIS LOG plot (X: P/p₀, Y: adsorbed volume), axes, and resize binding.

        Args:
            translator: Localized axis and title strings.
            parent: Optional Qt parent.
        """
        super().__init__(parent)
        self._translator = translator
        self._x_field: AnalysisLogField = X_ANALYSIS_LOG_PLOT_DEFAULT
        self._y_field: AnalysisLogField = Y_ANALYSIS_LOG_PLOT_DEFAULT
        self._sessions: tuple[OpenFileSession, ...] = ()
        self._lines: dict[Path, Line2D] = {}
        self._visible: Callable[[Path], bool] = lambda _p: True
        self._get_color: Callable[[Path], str] = lambda _p: _default_color()

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

        translator.locale_changed.connect(self._rebuild_plots)
        self._rebuild_plots()

    def set_sessions(
        self,
        sessions: Sequence[OpenFileSession],
        is_visible: Callable[[Path], bool],
        get_color: Callable[[Path], str],
    ) -> None:
        """
        Replace the session set, wire parsed_changed, and rebuild all lines.

        Args:
            sessions: All open per-file sessions.
            is_visible: Per-path show/hide in the multi plot.
            get_color: Per-path line color in matplotlib format (e.g. ``#aabbcc``).
        """
        if not callable(is_visible):
            raise TypeError("is_visible must be a callable")
        if not callable(get_color):
            raise TypeError("get_color must be a callable")
        for previous in self._sessions:
            try:
                previous.parsed_changed.disconnect(self._rebuild_plots)
            except TypeError:
                logger.debug("ANALYSIS LOG plot: parsed_changed already detached for %s", previous.path)
        self._sessions = tuple(sessions)
        self._visible = is_visible
        self._get_color = get_color
        for s in self._sessions:
            s.parsed_changed.connect(self._rebuild_plots)
        self._rebuild_plots()

    def set_path_visibility(self, is_visible: Callable[[Path], bool]) -> None:
        """Point the visibility callback at a new function and update lines without full redraw."""
        if not callable(is_visible):
            raise TypeError("is_visible must be a callable")
        self._visible = is_visible
        self.apply_appearance()

    def apply_appearance(self) -> None:
        """Update visibility and colors only, preserving the current x/y limits and pan/zoom state."""
        if not self._lines:
            return
        x0, x1 = self._axes.get_xlim()
        y0, y1 = self._axes.get_ylim()
        self._axes.set_autoscalex_on(False)
        self._axes.set_autoscaley_on(False)
        for p, line in self._lines.items():
            line.set_visible(self._visible(p))
            c = _safe_color(self._get_color, p)
            line.set_color(c)
        self._axes.set_xlim(x0, x1)
        self._axes.set_ylim(y0, y1)
        self._canvas.draw_idle()

    def _axis_label(self, field: AnalysisLogField) -> str:
        """Translate axis label for an ANALYSIS LOG column."""
        mapping: dict[AnalysisLogField, str] = {
            "relative_pressure": "axis.relative_pressure",
            "pressure_mmhg": "axis.pressure_mmhg",
            "vol_adsorbed_cc_g_stp": "axis.vol_adsorbed",
        }
        return self._translator.tr_key(mapping[field])

    def _rebuild_plots(self) -> None:
        """Recompute all series: clears axes, used for data changes and after locale change."""
        self._axes.clear()
        self._lines.clear()
        title = self._translator.tr_key("chart.analysis_log.title")
        self._axes.set_title(title)
        if not self._sessions:
            self._canvas.draw_idle()
            return
        for _idx, session in enumerate(self._sessions):
            path = session.path
            report = session.parsed
            rows = report.analysis_log
            if not rows:
                continue
            try:
                xs = analysis_series(rows, self._x_field)
                ys = analysis_series(rows, self._y_field)
            except ValueError:
                logger.exception("ANALYSIS LOG multi-plot: series extraction failed for %s", path)
                continue
            c = _safe_color(self._get_color, path)
            lbl = _curve_legend_label(session)
            (line,) = self._axes.plot(
                xs,
                ys,
                color=c,
                linewidth=_LINE_W,
                visible=self._visible(path),
                label=lbl,
            )
            line.set_gid(_curve_gid_for_path(path))
            self._lines[path] = line
        self._axes.set_xlabel(self._axis_label(self._x_field))
        self._axes.set_ylabel(self._axis_label(self._y_field))
        self._axes.grid(True, linestyle="--", linewidth=0.5, alpha=0.6)
        self._axes.set_autoscalex_on(True)
        self._axes.set_autoscaley_on(True)
        self._canvas.draw_idle()


class MultiBjhChartWidget(QWidget):
    """BJH multi-file chart with incremental appearance updates."""

    def __init__(self, translator: Translator, parent: QWidget | None = None) -> None:
        """
        Build the BJH shell, axes, and resize binding.

        Args:
            translator: Localized axis and title strings.
            parent: Optional Qt parent.
        """
        super().__init__(parent)
        self._translator = translator
        self._x_field: BJHSeries = XBJH_DEFAULT
        self._y_field: BJHSeries = YBJH_DEFAULT
        self._sessions: tuple[OpenFileSession, ...] = ()
        self._lines: dict[Path, Line2D] = {}
        self._visible: Callable[[Path], bool] = lambda _p: True
        self._get_color: Callable[[Path], str] = lambda _p: _default_color()

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

        translator.locale_changed.connect(self._rebuild_plots)
        self._rebuild_plots()

    def set_sessions(
        self,
        sessions: Sequence[OpenFileSession],
        is_visible: Callable[[Path], bool],
        get_color: Callable[[Path], str],
    ) -> None:
        """
        Replace the session set, wire updates, and rebuild BJH lines.

        Args:
            sessions: All open per-file sessions.
            is_visible: Per-path show/hide.
            get_color: Per-path line color.
        """
        if not callable(is_visible):
            raise TypeError("is_visible must be a callable")
        if not callable(get_color):
            raise TypeError("get_color must be a callable")
        for previous in self._sessions:
            try:
                previous.parsed_changed.disconnect(self._rebuild_plots)
            except TypeError:
                logger.debug("BJH: parsed_changed already disconnected for %s", previous.path)
        self._sessions = tuple(sessions)
        self._visible = is_visible
        self._get_color = get_color
        for s in self._sessions:
            s.parsed_changed.connect(self._rebuild_plots)
        self._rebuild_plots()

    def set_path_visibility(self, is_visible: Callable[[Path], bool]) -> None:
        """Update visibility only without rebuilding geometry."""
        if not callable(is_visible):
            raise TypeError("is_visible must be a callable")
        self._visible = is_visible
        self.apply_appearance()

    def apply_appearance(self) -> None:
        """Update visibility and colors, preserving the current view limits."""
        if not self._lines:
            return
        x0, x1 = self._axes.get_xlim()
        y0, y1 = self._axes.get_ylim()
        self._axes.set_autoscalex_on(False)
        self._axes.set_autoscaley_on(False)
        for p, line in self._lines.items():
            line.set_visible(self._visible(p))
            c = _safe_color(self._get_color, p)
            line.set_color(c)
        self._axes.set_xlim(x0, x1)
        self._axes.set_ylim(y0, y1)
        self._canvas.draw_idle()

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

    def _rebuild_plots(self) -> None:
        """Clear and repopulate BJH lines; restores autoscaling for new data."""
        self._axes.clear()
        self._lines.clear()
        title = self._translator.tr_key("chart.bjh.title")
        self._axes.set_title(title)
        if not self._sessions:
            self._canvas.draw_idle()
            return
        for _idx, session in enumerate(self._sessions):
            path = session.path
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
            c = _safe_color(self._get_color, path)
            lbl = _curve_legend_label(session)
            (line,) = self._axes.plot(
                xs,
                ys,
                color=c,
                linewidth=_LINE_W,
                visible=self._visible(path),
                label=lbl,
            )
            line.set_gid(_curve_gid_for_path(path))
            self._lines[path] = line
        self._axes.set_xlabel(self._axis_label(self._x_field))
        self._axes.set_ylabel(self._axis_label(self._y_field))
        self._axes.grid(True, linestyle="--", linewidth=0.5, alpha=0.6)
        self._axes.set_autoscalex_on(True)
        self._axes.set_autoscaley_on(True)
        self._canvas.draw_idle()


def _safe_color(get_color: Callable[[Path], str], path: Path) -> str:
    """Call ``get_color`` and validate; fall back to a default on errors."""
    if not isinstance(path, Path):
        raise TypeError("path must be pathlib.Path")
    if not callable(get_color):
        raise TypeError("get_color must be a callable")
    try:
        raw = get_color(path)
    except Exception as exc:
        logger.debug("get_color failed for %s: %s", path, exc)
        return _default_color()
    if not isinstance(raw, str) or not raw.strip():
        return _default_color()
    return raw.strip()
