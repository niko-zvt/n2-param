"""
Raw ASAP text editor with explicit edit policy and save actions.

The buffer is plain text: tab (``\\t``) and space characters are preserved; display uses a
monospace font and a fixed tab stop so columns match the file layout.
"""

from __future__ import annotations

import logging

from PySide6.QtGui import QFont, QFontDatabase, QFontInfo, QFontMetricsF, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from n2_param.gui.file_session import OpenFileSession
from n2_param.i18n.translator import Translator

logger = logging.getLogger(__name__)

# Tab display width: eight spaces, matching how fixed-pitch / ASAP viewers align columns.
_TAB_STOPS_IN_SPACES: int = 8

# Explicit families: ``QFont`` with only :class:`QFont.StyleHint` often resolves to a proportional
# system UI font (e.g. on macOS); the list is chosen for fixed-pitch and OS availability.
_PREFERRED_MONO_FAMILIES: tuple[str, ...] = (
    "Menlo",
    "Monaco",
    "Consolas",
    "Liberation Mono",
    "DejaVu Sans Mono",
    "Courier New",
    "Courier",
)

_RAW_EDITOR_OBJECT_NAME: str = "n2_raw_file_plain"


def _pick_source_monospace_font(point_size: int) -> QFont:
    """
    Return a :class:`QFont` for which ``QFontInfo`` reports fixed pitch, using a named family when possible.

    Args:
        point_size: Base point size (typ. 9–10).

    Returns:
        A concrete font (never a hint-only :class:`QFont`).

    Raises:
        TypeError: If ``point_size`` is not a positive int.
    """
    if not isinstance(point_size, int) or point_size < 1:
        raise TypeError("point_size must be a positive int")
    for family in _PREFERRED_MONO_FAMILIES:
        if not QFontDatabase.hasFamily(family):
            continue
        if not QFontDatabase.isFixedPitch(family):
            continue
        candidate = QFont(family, point_size)
        if QFontInfo(candidate).fixedPitch():
            return candidate
    # Last resort: Courier New is widely available and monospaced.
    fallback = QFont("Courier New", point_size)
    if not QFontInfo(fallback).fixedPitch():
        logger.warning("Fallback raw-text font is not reported as fixed-pitch: %s", QFontInfo(fallback).family())
    return fallback


def _configure_plain_text_for_source(editor: QPlainTextEdit) -> None:
    """
    Monospace, fixed tab width, no wrap: preserve spaces and U+0009 in the file as the user expects.

    A named fixed-pitch family plus a scoped stylesheet are both applied so the widget does not fall
    back to a proportional system font (common when only :class:`QFont.StyleHint` is set).

    Args:
        editor: The raw file viewer; ``\t`` is not converted, only how it is drawn is fixed.
    """
    if not isinstance(editor, QPlainTextEdit):
        raise TypeError("editor must be a QPlainTextEdit")
    font = _pick_source_monospace_font(10)
    editor.setFont(font)
    editor.setObjectName(_RAW_EDITOR_OBJECT_NAME)
    # Reinforce the family: Fusion and platform default fonts can still override a hint-based font.
    _css = (
        "QPlainTextEdit#%s {"
        " font: 10pt 'Menlo', 'Monaco', 'Consolas', 'Liberation Mono', 'DejaVu Sans Mono',"
        " 'Courier New', 'Courier', monospace;"
        " }"
    ) % _RAW_EDITOR_OBJECT_NAME
    editor.setStyleSheet(_css)
    editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
    fm = QFontMetricsF(font)
    tab_px = _TAB_STOPS_IN_SPACES * float(fm.horizontalAdvance(" "))
    if tab_px > 0.0:
        editor.setTabStopDistance(tab_px)


class RawTextWidget(QWidget):
    """Editable plain-text view gated by user consent."""

    def __init__(self, session: OpenFileSession, translator: Translator, parent: QWidget | None = None) -> None:
        """
        Wire editor state to the backing session.

        Args:
            session: File buffer to display and persist.
            translator: Localization helper.
            parent: Optional Qt parent widget.
        """
        super().__init__(parent)
        self._session = session
        self._translator = translator

        layout = QVBoxLayout(self)
        controls = QHBoxLayout()
        self._allow_checkbox = QCheckBox("", self)
        self._save_button = QPushButton("", self)
        self._status_label = QLabel("", self)
        controls.addWidget(self._allow_checkbox)
        controls.addWidget(self._save_button)
        controls.addStretch(1)
        controls.addWidget(self._status_label)
        layout.addLayout(controls)

        self._editor = QPlainTextEdit(self)
        layout.addWidget(self._editor)
        _configure_plain_text_for_source(self._editor)

        self._editor.blockSignals(True)
        self._editor.setPlainText(session.text)
        self._editor.blockSignals(False)
        self._editor.setReadOnly(not session.allow_edit_raw)

        self._allow_checkbox.setChecked(session.allow_edit_raw)
        self._save_button.setEnabled(session.allow_edit_raw)

        self._allow_checkbox.toggled.connect(self._on_allow_toggled)
        self._save_button.clicked.connect(self._save)
        self._editor.textChanged.connect(self._on_text_changed)
        session.edit_policy_changed.connect(self._on_policy_changed)
        session.dirty_changed.connect(self._on_dirty_changed)
        translator.locale_changed.connect(self._refresh_static_text)

        shortcut = QShortcut(QKeySequence.Save, self)
        shortcut.activated.connect(self._save)

        self._refresh_static_text()
        self._on_dirty_changed(session.is_dirty)

    def _refresh_static_text(self) -> None:
        """Apply localized button and checkbox labels."""
        self._allow_checkbox.setText(self._translator.tr_key("raw.allow_edit"))
        self._save_button.setText(self._translator.tr_key("raw.save"))

    def _on_allow_toggled(self, checked: bool) -> None:
        """Mirror checkbox state into the session policy."""
        self._session.set_allow_edit_raw(checked)
        self._editor.setReadOnly(not checked)
        self._save_button.setEnabled(checked)

    def _on_policy_changed(self, allowed: bool) -> None:
        """Keep widgets aligned when policy changes externally."""
        self._allow_checkbox.blockSignals(True)
        self._allow_checkbox.setChecked(allowed)
        self._allow_checkbox.blockSignals(False)
        self._editor.setReadOnly(not allowed)
        self._save_button.setEnabled(allowed)

    def _on_text_changed(self) -> None:
        """Propagate editor changes into the session buffer."""
        self._session.set_text_buffer(self._editor.toPlainText())

    def _on_dirty_changed(self, dirty: bool) -> None:
        """Show a lightweight dirty indicator near the controls."""
        if dirty:
            self._status_label.setText(self._translator.tr_key("raw.unsaved"))
        else:
            self._status_label.setText("")

    def _save(self) -> None:
        """Persist buffer to disk if editing is enabled."""
        if not self._session.allow_edit_raw:
            return
        text = self._editor.toPlainText()
        if not text.strip():
            QMessageBox.warning(self, self._translator.tr_key("menu.file"), self._translator.tr_key("dialog.save_failed"))
            return
        try:
            self._session.set_text_buffer(text)
            self._session.reparse_buffer()
            self._session.save_to_disk()
        except OSError:
            logger.exception("Save failed")
            QMessageBox.critical(
                self,
                self._translator.tr_key("menu.file"),
                self._translator.tr_key("dialog.save_failed"),
            )
