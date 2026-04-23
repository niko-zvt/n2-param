"""
Summary outer tab: combined charts for all open files and a per-file visibility panel.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QGroupBox,
    QHBoxLayout,
    QScrollArea,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from n2_param.gui.file_session import OpenFileSession
from n2_param.gui.summary_charts import MultiBjhChartWidget, MultiIsothermChartWidget
from n2_param.i18n.translator import Translator

logger = logging.getLogger(__name__)


class SummaryTabPage(QWidget):
    """
    First tab: two inner chart views (isotherm, BJH) and a left column of file checkboxes.
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
        self._checkboxes: dict[Path, QCheckBox] = {}
        self._label_slots: list[tuple[OpenFileSession, object]] = []

        root = QHBoxLayout(self)
        self._splitter = QSplitter(Qt.Orientation.Horizontal, self)
        root.addWidget(self._splitter, stretch=1)

        self._file_group = QGroupBox(self)
        self._file_group_layout = QVBoxLayout(self._file_group)
        self._file_scroll = QScrollArea(self)
        self._file_scroll.setWidgetResizable(True)
        self._file_panel = QWidget(self._file_scroll)
        self._file_list_layout = QVBoxLayout(self._file_panel)
        self._file_scroll.setWidget(self._file_panel)
        self._file_group_layout.addWidget(self._file_scroll)
        self._splitter.addWidget(self._file_group)
        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)
        self._splitter.setSizes([240, 800])

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

    def set_sessions(self, sessions: Sequence[OpenFileSession]) -> None:
        """
        Rebuild the file checkbox list and multi-series charts for the current open files.

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
        self._checkboxes.clear()
        self._sessions = list(sessions)
        for session in self._sessions:
            box = QCheckBox(self._file_panel)
            box.setChecked(True)
            box.toggled.connect(self._on_file_toggle)
            self._file_list_layout.addWidget(box)
            self._checkboxes[session.path] = box
        self._file_list_layout.addStretch(1)
        self._refresh_file_labels()
        for session in self._sessions:
            slot = self._make_label_slot(session)
            session.parsed_changed.connect(slot)
            self._label_slots.append((session, slot))
        v = self._is_file_visible
        self._iso.set_sessions(self._sessions, v)
        self._bjh.set_sessions(self._sessions, v)

    def _make_label_slot(self, session: OpenFileSession) -> object:
        """Build a unique slot to refresh a checkbox caption when the sample name changes."""
        ch = self._checkboxes[session.path]

        def on_change() -> None:
            if self._checkboxes.get(session.path) is ch:
                ch.setText(session.display_title())

        return on_change

    def _on_locale_change(self, _language: str = "") -> None:
        """Refresh static texts after language change."""
        _ = _language
        self._update_file_group_title()
        self._inner.setTabText(0, self._translator.tr_key("tab.chart_isotherm"))
        self._inner.setTabText(1, self._translator.tr_key("tab.chart_bjh"))

    def _update_file_group_title(self) -> None:
        """Apply the translatable file list caption."""
        self._file_group.setTitle(self._translator.tr_key("summary.file_list_title"))

    def _refresh_file_labels(self) -> None:
        """Write checkbox text from the current display title of each session."""
        for p, box in self._checkboxes.items():
            for s in self._sessions:
                if s.path == p:
                    box.setText(s.display_title())
                    break

    def _on_file_toggle(self) -> None:
        """Re-render only line visibility; session wiring stays the same."""
        v = self._is_file_visible
        self._iso.set_path_visibility(v)
        self._bjh.set_path_visibility(v)

    def _is_file_visible(self, path: Path) -> bool:
        """Return whether a path is checked in the left list."""
        if not isinstance(path, Path):
            raise TypeError("path must be pathlib.Path")
        if path in self._checkboxes:
            return self._checkboxes[path].isChecked()
        return True
