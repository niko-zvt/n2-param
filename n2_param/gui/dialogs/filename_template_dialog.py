"""
Dialog to collect a single-line file name pattern for batch export (e.g. ``{sample_name}``).
"""

from __future__ import annotations

from typing import Final

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from n2_param.i18n.translator import Translator

SAMPLE_NAME_PLACEHOLDER: Final[str] = "{sample_name}"


class FilenameTemplateDialog(QDialog):
    """
    Return a name pattern when accepted; the default line contains the ``{sample_name}`` token.
    """

    def __init__(self, translator: Translator, parent: QWidget | None = None) -> None:
        """
        Build the form with a default pattern from the translator.
        """
        super().__init__(parent)
        self._translator = translator
        self.setWindowTitle(translator.tr_key("export.name_template_title"))
        root = QVBoxLayout(self)
        hint = QLabel(translator.tr_key("export.name_template_label"), self)
        hint.setWordWrap(True)
        root.addWidget(hint)
        self._line = QLineEdit(self)
        default_pt = translator.tr_key("export.name_template_default").strip()
        self._line.setText(default_pt if default_pt else SAMPLE_NAME_PLACEHOLDER)
        self._line.setClearButtonEnabled(True)
        self._line.setMinimumWidth(320)
        root.addWidget(self._line)
        box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        root.addWidget(box)

    @property
    def pattern(self) -> str:
        """
        The user-entered pattern, stripped (may be empty; caller may reject).
        """
        return self._line.text().strip()

    def set_pattern(self, text: str) -> None:
        """
        Replace the editor text (e.g. before showing the dialog).
        """
        if not isinstance(text, str):
            raise TypeError("text must be str")
        self._line.setText(text)
