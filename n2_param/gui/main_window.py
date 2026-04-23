"""
Primary application window with menus, drag-and-drop, and nested tabs.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QByteArray, QSettings, QTimer
from PySide6.QtGui import QAction, QActionGroup, QCloseEvent, QDragEnterEvent, QDropEvent, QKeySequence
from PySide6.QtWidgets import (
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QTabBar,
    QTabWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from n2_param.core.parsing.asap_report_parser import AsapReportParser
from n2_param.gui.dialogs.about_dialog import AboutDialog
from n2_param.gui.file_session import OpenFileSession
from n2_param.gui.file_tab_page import FileTabPage
from n2_param.gui.summary_tab_page import SummaryTabPage
from n2_param.i18n.translator import Translator
from n2_param.io.text_files import read_text_file_best_effort

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Hosts multi-file tabs and wires global actions."""

    _SETTING_LAST_OPEN_DIR: str = "file/last_open_directory"
    _SETTING_WINDOW_GEOMETRY: str = "window/geometry"

    def __init__(self, parent: QWidget | None = None) -> None:
        """Create menus, central tabs, and localization bindings."""
        super().__init__(parent)
        self._translator = Translator(self)
        self._parser = AsapReportParser()
        self._open_paths: set[Path] = set()
        self._summary_page: SummaryTabPage | None = None
        self._open_batch_last_path: Path | None = None
        self._open_batch_multi: bool = False
        self._language_actions: dict[str, QAction] = {}

        central = QWidget(self)
        layout = QVBoxLayout(central)
        self._hint = QLabel("", central)
        self._file_tabs = QTabWidget(central)
        self._file_tabs.setTabsClosable(True)
        self._file_tabs.tabCloseRequested.connect(self._close_tab)
        layout.addWidget(self._hint)
        layout.addWidget(self._file_tabs, stretch=1)
        self.setCentralWidget(central)

        self.setAcceptDrops(True)
        self._build_menu()
        self._build_toolbar()
        self._apply_window_geometry()
        self._translator.locale_changed.connect(self._on_locale_changed)
        self._on_locale_changed(self._translator.current_language)

    def _build_menu(self) -> None:
        """Construct menu bar actions and shortcuts."""
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu("")
        open_action = QAction("", self)
        open_action.setShortcut(QKeySequence.Open)
        open_action.triggered.connect(self._choose_files)
        file_menu.addAction(open_action)

        quit_action = QAction("", self)
        quit_action.setShortcut(QKeySequence.Quit)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        language_menu = menu_bar.addMenu("")
        self._language_group = QActionGroup(self)
        self._language_group.setExclusive(True)
        for lang in self._translator.available_languages():
            lang_action = QAction(lang.upper(), self)
            lang_action.setCheckable(True)
            lang_action.setChecked(lang == self._translator.current_language)
            self._language_group.addAction(lang_action)
            language_menu.addAction(lang_action)
            lang_action.triggered.connect(lambda _checked=False, code=lang: self._select_language(code))
            self._language_actions[lang] = lang_action

        help_menu = menu_bar.addMenu("")
        about_action = QAction("", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

        self._menu_file = file_menu
        self._menu_language = language_menu
        self._menu_help = help_menu
        self._action_open = open_action
        self._action_quit = quit_action
        self._action_about = about_action

        self._refresh_menu_texts()

    def _build_toolbar(self) -> None:
        """Add a top toolbar with the same Open action as the File menu."""
        tool_bar = QToolBar(self)
        tool_bar.setObjectName("mainToolBar")
        tool_bar.setMovable(False)
        tool_bar.setFloatable(False)
        tool_bar.addAction(self._action_open)
        self.addToolBar(tool_bar)

    def _file_dialog_start_directory(self) -> str:
        """
        Restore the last directory used by the file picker, if still valid.

        Returns:
            Absolute path string for ``QFileDialog`` start, or an empty string.
        """
        store = QSettings()
        store.sync()
        raw = store.value(self._SETTING_LAST_OPEN_DIR, "", type=str)
        if not isinstance(raw, str) or not raw.strip():
            return ""
        candidate = Path(raw).expanduser()
        try:
            resolved = candidate.resolve(strict=False)
        except (OSError, ValueError) as exc:
            logger.debug("Invalid stored open directory %r: %s", raw, exc)
            return ""
        if resolved.is_dir():
            return str(resolved)
        return ""

    def _remember_file_dialog_directory(self, directory: Path) -> None:
        """
        Persist a directory for the next file picker.

        Args:
            directory: Folder that the user was browsing (typically a parent of the selection).
        """
        if not isinstance(directory, Path):
            raise TypeError("directory must be pathlib.Path")
        try:
            resolved = directory.expanduser().resolve(strict=False)
        except (OSError, ValueError) as exc:
            logger.debug("Not persisting open directory: %s", exc)
            return
        if not resolved.is_dir():
            return
        store = QSettings()
        store.setValue(self._SETTING_LAST_OPEN_DIR, str(resolved))
        store.sync()

    def _apply_window_geometry(self) -> None:
        """
        Restore a saved main-window size, or use 1024x768 on first run.

        Geometry is read from the same QSettings group as the rest of the app.
        """
        store = QSettings()
        store.sync()
        raw: object = store.value(self._SETTING_WINDOW_GEOMETRY, b"")
        geometry = QByteArray()
        if isinstance(raw, QByteArray):
            geometry = raw
        elif isinstance(raw, (bytes, bytearray)):
            geometry = QByteArray(bytes(raw))
        if geometry.isEmpty() or not self.restoreGeometry(geometry):
            self.resize(1024, 768)

    def _outer_tab_session(self, w: QWidget | None) -> OpenFileSession | None:
        """
        Return the per-file session for an outer tab page.

        Uses ``OpenFileSession`` on the widget instead of ``isinstance(..., FileTabPage)``
        so a duplicate import of ``file_tab_page`` cannot hide real file tabs.
        """
        if w is None or isinstance(w, SummaryTabPage):
            return None
        session = getattr(w, "session", None)
        if session is not None and isinstance(session, OpenFileSession):
            return session
        return None

    def _list_sessions_from_file_tabs(self) -> list[OpenFileSession]:
        """Return opened file sessions in outer tab order (Summary excluded)."""
        out: list[OpenFileSession] = []
        for i in range(self._file_tabs.count()):
            s = self._outer_tab_session(self._file_tabs.widget(i))
            if s is not None:
                out.append(s)
        return out

    def _sync_summary_tab(self) -> None:
        """
        Create, update, or remove the Summary tab so it always mirrors all file tabs.
        """
        if self._summary_page is not None and self._file_tabs.indexOf(self._summary_page) < 0:
            self._summary_page = None
        sessions = self._list_sessions_from_file_tabs()
        if not sessions:
            if self._summary_page is not None:
                to_remove: SummaryTabPage = self._summary_page
                for idx in range(self._file_tabs.count() - 1, -1, -1):
                    w = self._file_tabs.widget(idx)
                    if w is to_remove:
                        self._file_tabs.removeTab(idx)
                        to_remove.deleteLater()
                self._summary_page = None
            return
        if self._summary_page is None:
            self._summary_page = SummaryTabPage(self._translator, parent=self._file_tabs)
            self._file_tabs.insertTab(0, self._summary_page, self._translator.tr_key("tab.summary"))
        self._summary_page.set_sessions(sessions)
        self._ensure_summary_is_first()
        self._summary_tab_bring_title_in_sync()
        self._apply_summary_tab_no_close_button()

    def _ensure_summary_is_first(self) -> None:
        """Move the Summary tab to the first (left) position, before any file tabs."""
        if self._summary_page is None:
            return
        at = self._file_tabs.indexOf(self._summary_page)
        if at < 0 or at == 0:
            return
        label = self._file_tabs.tabText(at)
        self._file_tabs.removeTab(at)
        self._file_tabs.insertTab(0, self._summary_page, label)

    def _summary_tab_bring_title_in_sync(self) -> None:
        """Keep the outer Summary label translated."""
        if self._summary_page is None:
            return
        pos = self._file_tabs.indexOf(self._summary_page)
        if pos < 0:
            return
        self._file_tabs.setTabText(pos, self._translator.tr_key("tab.summary"))

    def _apply_summary_tab_no_close_button(self) -> None:
        """The Summary tab must not be closable like per-file tabs."""
        bar = self._file_tabs.tabBar()
        for i in range(self._file_tabs.count()):
            w = self._file_tabs.widget(i)
            if isinstance(w, SummaryTabPage):
                bar.setTabButton(i, QTabBar.ButtonPosition.RightSide, None)
                break

    def _refresh_menu_texts(self) -> None:
        """Apply localized captions to menus and actions."""
        tr = self._translator.tr_key
        self._menu_file.setTitle(tr("menu.file"))
        self._menu_language.setTitle(tr("menu.language"))
        self._menu_help.setTitle(tr("menu.help"))
        self._action_open.setText(tr("menu.file.open"))
        self._action_quit.setText(tr("menu.file.exit"))
        self._action_about.setText(tr("menu.help.about"))
        self._hint.setText(tr("drop.hint"))

    def _on_locale_changed(self, language: str) -> None:
        """Update chrome when Translation language changes."""
        _ = language
        self.setWindowTitle(self._translator.tr_key("window.title"))
        self._refresh_menu_texts()
        self._summary_tab_bring_title_in_sync()
        for lang, action in self._language_actions.items():
            action.setChecked(lang == self._translator.current_language)

    def _select_language(self, lang_code: str) -> None:
        """Handle explicit language picks from the menu."""
        try:
            self._translator.set_language(lang_code)
        except ValueError:
            logger.warning("Ignored unknown language selection: %s", lang_code)

    def _choose_files(self) -> None:
        """Open native file picker for one or many ASAP exports."""
        start = self._file_dialog_start_directory()
        paths_str, _selected_filter = QFileDialog.getOpenFileNames(
            self,
            self._translator.tr_key("menu.file.open"),
            start,
            "All files (*.*)",
        )
        if paths_str:
            self._remember_file_dialog_directory(Path(paths_str[0]).parent)
        paths = [Path(entry) for entry in paths_str]
        self._open_paths_from_local(paths)

    def _open_paths_from_local(self, paths: list[Path]) -> None:
        """Load files from absolute or relative paths."""
        cleaned: list[Path] = []
        for raw in paths:
            candidate = raw.expanduser()
            resolved = candidate.resolve()
            if not resolved.exists() or not resolved.is_file():
                logger.warning("Skipping missing path: %s", resolved)
                continue
            cleaned.append(resolved)
        self._open_resolved_paths(cleaned)

    def _open_resolved_paths(self, paths: list[Path]) -> None:
        """Create sessions and tabs for unique paths."""
        if not paths:
            return
        self._open_batch_last_path = None
        for path in paths:
            if path in self._open_paths:
                idx = self._find_tab_index_for_path(path)
                if idx is not None:
                    self._file_tabs.setCurrentIndex(idx)
                continue
            try:
                text, encoding = read_text_file_best_effort(path)
                parsed = self._parser.parse(text)
            except (OSError, UnicodeError, ValueError) as exc:
                logger.exception("Failed to open %s", path)
                QMessageBox.critical(self, self._translator.tr_key("menu.file"), str(exc))
                continue

            session = OpenFileSession(path, text, encoding, parsed, parent=self)
            page = FileTabPage(session, self._translator, parent=self._file_tabs)
            title = session.display_title()
            self._file_tabs.addTab(page, title)
            self._open_paths.add(path)
            self._open_batch_last_path = path
            session.parsed_changed.connect(lambda s=session: self._update_tab_title(s))
        self._open_batch_multi = len(paths) > 1
        QTimer.singleShot(0, self._complete_open_resolved_batch)

    def _complete_open_resolved_batch(self) -> None:
        """
        Apply Summary and focus after the event loop: sync visibility of tabs and
        (when the batch had several paths) select the Summary so it is not
        scrolled off the tab bar when the last file is selected.
        """
        if self._summary_page is not None and self._file_tabs.indexOf(self._summary_page) < 0:
            self._summary_page = None
        self._sync_summary_tab()
        n_tabs = self._file_tabs.count()
        if n_tabs < 1:
            self._open_batch_last_path = None
            self._open_batch_multi = False
            return
        if self._open_batch_multi:
            self._file_tabs.setCurrentIndex(0)
        elif self._open_batch_last_path is not None:
            tab_idx = self._find_tab_index_for_path(self._open_batch_last_path)
            if tab_idx is not None:
                self._file_tabs.setCurrentIndex(tab_idx)
        self._open_batch_last_path = None
        self._open_batch_multi = False

    def _find_tab_index_for_path(self, path: Path) -> int | None:
        """Locate an existing file tab (not Summary) by filesystem path."""
        for idx in range(self._file_tabs.count()):
            s = self._outer_tab_session(self._file_tabs.widget(idx))
            if s is not None and s.path == path:
                return idx
        return None

    def _update_tab_title(self, session: OpenFileSession) -> None:
        """Refresh outer tab text when SAMPLE ID changes after reparse."""
        idx = self._find_tab_index_for_session(session)
        if idx is None:
            return
        self._file_tabs.setTabText(idx, session.display_title())

    def _find_tab_index_for_session(self, session: OpenFileSession) -> int | None:
        """Locate the tab hosting a session instance."""
        for idx in range(self._file_tabs.count()):
            s = self._outer_tab_session(self._file_tabs.widget(idx))
            if s is not None and s is session:
                return idx
        return None

    def _close_tab(self, index: int) -> None:
        """Remove a tab and forget its path guard."""
        widget = self._file_tabs.widget(index)
        if isinstance(widget, SummaryTabPage):
            return
        s = self._outer_tab_session(widget)
        if s is not None:
            self._open_paths.discard(s.path)
        self._file_tabs.removeTab(index)
        self._sync_summary_tab()

    def _show_about(self) -> None:
        """Present developer information."""
        dialog = AboutDialog(self._translator, parent=self)
        dialog.exec()

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        """Accept local file drops."""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        """Load dropped files into new tabs."""
        paths: list[Path] = []
        for url in event.mimeData().urls():
            local = url.toLocalFile()
            if local:
                paths.append(Path(local))
        if paths:
            self._open_paths_from_local(paths)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)

    def closeEvent(self, event: QCloseEvent) -> None:
        """Persist main-window geometry before shutdown."""
        store = QSettings()
        store.setValue(self._SETTING_WINDOW_GEOMETRY, self.saveGeometry())
        store.sync()
        super().closeEvent(event)
