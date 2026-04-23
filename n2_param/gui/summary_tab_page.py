"""
Summary outer tab: combined charts and a per-file list with check, color, and name.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QShowEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from n2_param.gui.file_session import OpenFileSession
from n2_param.gui.summary_charts import DEFAULT_CURVE_COLORS, MultiBjhChartWidget, MultiIsothermChartWidget
from n2_param.i18n.translator import Translator

logger = logging.getLogger(__name__)

# Swatch (color) button: compact size for a single list row; layout aligns it with the checkbox and label.
_SWATCH_W: int = 16
_SWATCH_H: int = 14


@dataclass(frozen=True, slots=True)
class _SummaryRow:
    """One row in the file list: checkbox, color, label."""

    check: QCheckBox
    color_btn: QToolButton
    name: QLabel
    row_widget: QWidget


class SummaryTabPage(QWidget):
    """
    First tab: inner chart isotherm/BJH and a left file list (check, color swatch, name).
    """

    def __init__(self, translator: Translator, parent: QWidget | None = None) -> None:
        """
        Create an empty summary layout; call ``set_sessions`` when file tabs are available.

        Args:
            translator: Localization for inner tab titles and the file list group.
            parent: Optional Qt parent.
        """
        super().__init__(parent)
        self._translator = translator
        self._sessions: list[OpenFileSession] = []
        self._path_colors: dict[Path, str] = {}
        self._path_rows: dict[Path, _SummaryRow] = {}
        self._label_slots: list[tuple[OpenFileSession, object]] = []

        root = QHBoxLayout(self)
        self._splitter = QSplitter(Qt.Orientation.Horizontal, self)
        root.addWidget(self._splitter, stretch=1)

        self._file_group = QGroupBox(self)
        self._file_group.setSizePolicy(QSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))
        self._file_group_layout = QVBoxLayout(self._file_group)
        self._file_scroll = QScrollArea(self)
        self._file_scroll.setSizePolicy(
            QSizePolicy(
                QSizePolicy.Policy.MinimumExpanding,
                QSizePolicy.Policy.Expanding,
            )
        )
        # Keep the file list as tall as its content only: no stretching rows across the viewport.
        self._file_scroll.setWidgetResizable(False)
        self._file_scroll.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
        )
        self._file_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._file_panel = QWidget(self._file_scroll)
        self._file_panel.setSizePolicy(
            QSizePolicy(
                QSizePolicy.Policy.Minimum,
                QSizePolicy.Policy.Minimum,
            )
        )
        self._file_list_layout = QVBoxLayout(self._file_panel)
        self._file_list_layout.setContentsMargins(4, 2, 4, 2)
        self._file_list_layout.setSpacing(4)
        self._file_scroll.setWidget(self._file_panel)
        self._file_group_layout.addWidget(self._file_scroll)
        self._splitter.addWidget(self._file_group)
        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)

        self._inner = QTabWidget(self)
        self._iso = MultiIsothermChartWidget(translator, parent=self)
        self._bjh = MultiBjhChartWidget(translator, parent=self)
        self._inner.addTab(
            self._iso,
            translator.tr_key("tab.chart_isotherm"),
        )
        self._inner.addTab(
            self._bjh,
            translator.tr_key("tab.chart_bjh"),
        )
        self._splitter.addWidget(self._inner)
        translator.locale_changed.connect(self._on_locale_change)
        self._on_locale_change()
        self._update_file_group_title()

    def showEvent(self, event: QShowEvent) -> None:
        """Tie left-panel width to content the first time the page is shown."""
        super().showEvent(event)
        QTimer.singleShot(0, self._tune_left_panel_to_content)

    def set_sessions(self, sessions: Sequence[OpenFileSession]) -> None:
        """
        Rebuild the file list and point multi-series charts at the same sessions and colors.

        Args:
            sessions: All ``OpenFileSession`` instances from per-file outer tabs, in tab order.
        """
        for session, slot in self._label_slots:
            try:
                session.parsed_changed.disconnect(slot)
            except TypeError:
                logger.debug("Summary: label update already detached for %s", session.path)
        self._label_slots.clear()
        while (item := self._file_list_layout.takeAt(0)) is not None:
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._path_rows.clear()
        previous_colors = self._path_colors
        new_sessions = list(sessions)
        new_colors: dict[Path, str] = {}
        for idx, s in enumerate(new_sessions):
            p = s.path
            if p in previous_colors:
                new_colors[p] = previous_colors[p]
            else:
                new_colors[p] = DEFAULT_CURVE_COLORS[idx % len(DEFAULT_CURVE_COLORS)]
        self._path_colors = new_colors
        self._sessions = new_sessions

        for session in self._sessions:
            row = self._make_file_row(session)
            self._path_rows[session.path] = row
        self._refresh_name_labels()
        for session in self._sessions:
            slot = self._make_label_slot(session)
            session.parsed_changed.connect(slot)
            self._label_slots.append((session, slot))

        v = self._is_file_visible
        g = self._color_for_path
        self._iso.set_sessions(self._sessions, v, g)
        self._bjh.set_sessions(self._sessions, v, g)
        QTimer.singleShot(0, self._tune_left_panel_to_content)

    def _make_file_row(self, session: OpenFileSession) -> _SummaryRow:
        """Create one [check][color][name] row and wire signals."""
        path = session.path
        row_widget = QWidget(self._file_panel)
        row_widget.setSizePolicy(
            QSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Preferred,
            )
        )
        layout = QHBoxLayout(row_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        layout.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        )

        check = QCheckBox(row_widget)
        check.setChecked(True)
        check.toggled.connect(self._on_appearance_changed)
        check.setSizePolicy(
            QSizePolicy(
                QSizePolicy.Policy.Minimum,
                QSizePolicy.Policy.Fixed,
            )
        )
        c = self._path_colors[path]
        color_btn = QToolButton(row_widget)
        _apply_color_to_swatch_button(color_btn, c, _SWATCH_W, _SWATCH_H)
        color_btn.setFixedSize(_SWATCH_W, _SWATCH_H)
        color_btn.setSizePolicy(
            QSizePolicy(
                QSizePolicy.Policy.Fixed,
                QSizePolicy.Policy.Fixed,
            )
        )
        color_btn.setAutoRaise(True)
        color_btn.clicked.connect(
            lambda _=False, p=path, b=color_btn: self._choose_path_color(p, b),
        )

        name = QLabel(row_widget)
        name.setText(session.display_title())
        name.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        name.setWordWrap(False)
        name.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        name.setSizePolicy(
            QSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Minimum,
            )
        )
        row = _SummaryRow(check, color_btn, name, row_widget)
        layout.addWidget(check, 0)
        layout.addWidget(color_btn, 0)
        layout.addWidget(name, 1, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._file_list_layout.addWidget(row_widget, 0)
        return row

    def _tune_left_panel_to_content(self) -> None:
        """
        Set splitter so the file list is only as wide as its content; the chart gets the rest.

        Recomputes the scroll's inner widget after rows change (``setWidgetResizable False``).
        """
        self._file_panel.updateGeometry()
        self._file_panel.adjustSize()
        self._file_scroll.updateGeometry()
        self._file_group.adjustSize()
        w_left = self._file_group.sizeHint().width() + 12
        w_left = max(120, min(520, w_left))
        w_total = int(self._splitter.width() or 0) or (self.width() or 0) or (self.window().width() if self.window() is not None else 0) or 640
        if w_total > 200:
            w_left = min(w_left, w_total - 200)
        w_right = max(400, w_total - w_left)
        self._splitter.setSizes([w_left, w_right])

    def _on_appearance_changed(self) -> None:
        """Reapply visibility and colors; Multi* keep axis limits in ``apply_appearance``."""
        self._iso.apply_appearance()
        self._bjh.apply_appearance()

    def _choose_path_color(self, path: Path, color_btn: QToolButton) -> None:
        """Handle the color-swatch click for one path."""
        if not isinstance(path, Path):
            raise TypeError("path must be pathlib.Path")
        cur = self._path_colors.get(path) or "#7f7f7f"
        c = QColorDialog.getColor(QColor(cur), self, "")
        if not c.isValid():
            return
        hex_ = c.name()
        if not isinstance(hex_, str) or not hex_:
            return
        self._path_colors[path] = hex_
        _apply_color_to_swatch_button(color_btn, hex_, _SWATCH_W, _SWATCH_H)
        self._iso.apply_appearance()
        self._bjh.apply_appearance()

    def _color_for_path(self, path: Path) -> str:
        """Color string for the matplotlib lines (Summary charts)."""
        if not isinstance(path, Path):
            raise TypeError("path must be pathlib.Path")
        if path in self._path_colors:
            return self._path_colors[path]
        return _default_color_for_path(path, self._sessions, DEFAULT_CURVE_COLORS)

    def _is_file_visible(self, path: Path) -> bool:
        """Whether the file row is checked and the curve is drawn."""
        if not isinstance(path, Path):
            raise TypeError("path must be pathlib.Path")
        r = self._path_rows.get(path)
        if r is None:
            return True
        return r.check.isChecked()

    def _refresh_name_labels(self) -> None:
        """Set QLabel text to ``display_title()`` for all rows."""
        for p, row in self._path_rows.items():
            for s in self._sessions:
                if s.path == p:
                    row.name.setText(s.display_title())
                    break

    def _make_label_slot(self, session: OpenFileSession) -> object:
        """Refresh the name when parsing updates the title."""
        p = session.path
        name_l = self._path_rows[p].name

        def on_change() -> None:
            name_l.setText(session.display_title())

        return on_change

    def _on_locale_change(self, _language: str = "") -> None:
        """
        Re-translate the Summary group title and inner tab names.

        Chart text is updated by the shared ``Translator.locale_changed`` signal
        (already connected inside ``MultiIsothermChartWidget`` / ``MultiBjhChartWidget``).
        """
        _ = _language
        self._update_file_group_title()
        self._inner.setTabText(0, self._translator.tr_key("tab.chart_isotherm"))
        self._inner.setTabText(1, self._translator.tr_key("tab.chart_bjh"))

    def _update_file_group_title(self) -> None:
        """Set the file list group box title."""
        self._file_group.setTitle(self._translator.tr_key("summary.file_list_title"))


def _default_color_for_path(path: Path, sessions: list[OpenFileSession], palette: tuple[str, ...]) -> str:
    """Pick a default palette color from the file order in the Summary list."""
    for i, s in enumerate(sessions):
        if s.path == path:
            return palette[i % len(palette)]
    return "#7f7f7f"


def _apply_color_to_swatch_button(
    button: QToolButton,
    color_hex: str,
    width: int = _SWATCH_W,
    height: int = _SWATCH_H,
) -> None:
    """
    Paint a small color swatch on a ``QToolButton``; border for contrast in light and dark mode.

    The ``width``/``height`` (pixels) should match the widget ``setFixedSize`` of the same button.
    """
    c = QColor(color_hex)
    if not c.isValid():
        c = QColor("#7f7f7f")
    r, g, b, _a = c.getRgb()
    w, h = width, height
    button.setStyleSheet(
        (
            "QToolButton { background: rgb(%d, %d, %d); border: 1px solid #666; "
            "border-radius: 1px; min-width: %dpx; min-height: %dpx; max-width: %dpx; max-height: %dpx; }"
        )
        % (r, g, b, w, h, w, h)
    )