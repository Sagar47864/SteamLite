"""Main window, Stream Mode lifecycle, and page navigation."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPushButton,
    QStackedWidget, QVBoxLayout, QWidget,
)

from config.settings import SettingsStore
from core.models import SystemSnapshot
from core.monitor_worker import MonitorWorker
from core.process_action_worker import ProcessActionWorker
from core.process_manager import ProcessManager
from database.database import SessionDatabase
from ui.dashboard import DashboardPage
from ui.history import HistoryPage
from ui.settings import SettingsPage


class MainWindow(QMainWindow):
    """Owns the worker thread and restores reversible process changes."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("StreamLite")
        self.resize(1180, 900)
        self.setMinimumSize(1000, 720)
        self.setStyleSheet(_STYLESHEET)
        self.settings_store = SettingsStore()
        self.database = SessionDatabase()
        self.process_manager = ProcessManager()
        self.worker: MonitorWorker | None = None
        self._stopping = False
        self._pending_summary: dict | None = None
        self._game_pid: int | None = None
        self._game_process = None
        self._close_when_stopped = False
        self._process_actions: list[ProcessActionWorker] = []

        root = QWidget()
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        sidebar = self._build_sidebar()
        self.pages = QStackedWidget()
        self.dashboard = DashboardPage(self.settings_store)
        self.history = HistoryPage(self.database)
        self.settings_page = SettingsPage(self.settings_store)
        self.pages.addWidget(self.dashboard)
        self.pages.addWidget(self.history)
        self.pages.addWidget(self.settings_page)
        self.dashboard.stream_toggle_requested.connect(self._toggle_stream_mode)
        self.dashboard.priority_requested.connect(self._set_game_priority)
        self.dashboard.close_process_requested.connect(self._close_process)
        root_layout.addWidget(sidebar)
        root_layout.addWidget(self.pages, 1)
        self.setCentralWidget(root)

    def _build_sidebar(self) -> QWidget:
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(220)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(18, 24, 18, 20)
        layout.setSpacing(10)
        brand = QLabel("StreamLite")
        brand.setObjectName("brand")
        subtitle = QLabel("STREAMING COMPANION")
        subtitle.setObjectName("sidebarSubtitle")
        layout.addWidget(brand)
        layout.addWidget(subtitle)
        layout.addSpacing(30)
        self.nav_buttons: list[QPushButton] = []
        for index, title in enumerate(("Dashboard", "History", "Settings")):
            button = QPushButton(title)
            button.setObjectName("navButton")
            button.setCheckable(True)
            button.clicked.connect(lambda checked=False, page=index: self._show_page(page))
            layout.addWidget(button)
            self.nav_buttons.append(button)
        layout.addStretch(1)
        note = QLabel("Local monitoring and safe stream assistance.")
        note.setObjectName("sidebarNote")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.nav_buttons[0].setChecked(True)
        return sidebar

    def _show_page(self, index: int) -> None:
        self.pages.setCurrentIndex(index)
        for button_index, button in enumerate(self.nav_buttons):
            button.setChecked(button_index == index)
        if index == 1:
            self.history.refresh()

    def _toggle_stream_mode(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            self._stop_stream_mode()
        else:
            self._start_stream_mode()

    def _start_stream_mode(self) -> None:
        settings = self.settings_store.load()
        self._pending_summary = None
        self._stopping = False
        self._game_pid = None
        self._game_process = None
        self.dashboard._ignored_this_session.clear()
        self.worker = MonitorWorker(settings, self)
        self.worker.snapshot_ready.connect(self._on_snapshot)
        self.worker.summary_ready.connect(self._on_summary)
        self.worker.finished.connect(self._on_worker_finished)
        self.dashboard.set_stream_active(True)
        self.worker.start()

    def _stop_stream_mode(self) -> None:
        if self.worker is None or not self.worker.isRunning() or self._stopping:
            return
        self._stopping = True
        self.dashboard.set_stream_active(False, stopping=True)
        self.worker.requestInterruption()

    def _on_snapshot(self, snapshot: object) -> None:
        if isinstance(snapshot, dict) and snapshot.get("worker_error"):
            self.dashboard.warning.setText(f"Monitoring stopped after an error: {snapshot['worker_error']}")
            self.dashboard.set_stream_active(False, stopping=True)
            return
        if isinstance(snapshot, SystemSnapshot):
            self._game_pid = snapshot.game.pid if snapshot.game else None
            self._game_process = snapshot.game
            self.dashboard.update_snapshot(snapshot)

    def _on_summary(self, summary: object) -> None:
        if isinstance(summary, dict):
            self._pending_summary = summary

    def _on_worker_finished(self) -> None:
        worker = self.worker
        if worker is None:
            return
        self.worker = None
        worker.deleteLater()
        self._stopping = False
        restore_errors = self.process_manager.restore_priorities()
        self.dashboard.set_stream_active(False)
        self._game_pid = None
        self._game_process = None
        if self._pending_summary and self._pending_summary.get("average_cpu") is not None:
            try:
                self.database.save_session(self._pending_summary)
                self._pending_summary = None
                self.history.refresh()
            except Exception as exc:
                QMessageBox.warning(self, "History save failed", f"The monitoring session ended, but its history could not be saved: {exc}")
        if restore_errors:
            QMessageBox.warning(self, "Priority restoration", "Some process priorities could not be restored:\n" + "\n".join(restore_errors))
        self._finish_deferred_close()

    def _set_game_priority(self, priority: str) -> None:
        if self.worker is None or not self.worker.isRunning() or self._game_pid is None:
            QMessageBox.information(self, "Game not detected", "Start Stream Mode and select or focus a recognized game first.")
            return
        success, message = self.process_manager.set_game_priority(
            self._game_pid,
            priority,
            self._game_process.name if self._game_process else None,
            self._game_process.creation_time if self._game_process else None,
        )
        if success:
            QMessageBox.information(self, "Game priority", message)
        else:
            QMessageBox.warning(self, "Game priority", message)

    def _close_process(self, pid: int, expected_name: str, created_at: float) -> None:
        action = ProcessActionWorker(pid, expected_name, created_at if created_at >= 0 else None, self)
        action.finished_message.connect(self._show_close_result)
        action.finished.connect(lambda task=action: self._process_action_finished(task))
        self._process_actions.append(action)
        action.start()

    def _show_close_result(self, success: bool, message: str) -> None:
        if self._close_when_stopped:
            return
        if success:
            QMessageBox.information(self, "Application closed", message)
        else:
            QMessageBox.warning(self, "Could not close application", message)

    def _process_action_finished(self, action: ProcessActionWorker) -> None:
        if action in self._process_actions:
            self._process_actions.remove(action)
        action.deleteLater()
        self._finish_deferred_close()

    def _finish_deferred_close(self) -> None:
        worker_running = self.worker is not None and self.worker.isRunning()
        actions_running = any(action.isRunning() for action in self._process_actions)
        if self._close_when_stopped and not worker_running and not actions_running:
            self._close_when_stopped = False
            self.close()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt event method name
        worker_running = self.worker is not None and self.worker.isRunning()
        actions_running = any(action.isRunning() for action in self._process_actions)
        if worker_running or actions_running:
            self._close_when_stopped = True
            if worker_running:
                self.worker.requestInterruption()
                self.dashboard.set_stream_active(False, stopping=True)
            event.ignore()
            return
        if self.worker is not None:
            # The thread may have ended while its queued finished signal awaits UI delivery.
            self._pending_summary = self.worker._summary()
            if self._pending_summary.get("average_cpu") is not None:
                try:
                    self.database.save_session(self._pending_summary)
                except Exception:
                    pass
            self.process_manager.restore_priorities()
            self.worker.deleteLater()
            self.worker = None
        event.accept()


_STYLESHEET = """
QMainWindow, QWidget { background: #10141c; color: #e8edf5; font-family: 'Segoe UI'; font-size: 9.5pt; }
#sidebar { background: #0b0f16; border-right: 1px solid #252c38; }
#brand { font-size: 21pt; font-weight: 700; color: #f3f6fb; }
#sidebarSubtitle { color: #68758a; font-size: 8pt; font-weight: 700; letter-spacing: 1px; }
#navButton { text-align: left; padding: 11px 12px; border: 0; border-radius: 7px; color: #aab5c5; background: transparent; }
#navButton:hover { background: #171e2a; color: #edf2fa; }
#navButton:checked { color: #78d8b0; background: #17271f; font-weight: 600; }
#sidebarNote, #muted { color: #8d9aab; }
#pageTitle { font-size: 23pt; font-weight: 700; }
#sectionHeading { color: #aab5c5; font-weight: 700; font-size: 8.5pt; }
QFrame#card { background: #171d27; border: 1px solid #293240; border-radius: 10px; }
QLabel#notice { color: #8d9aab; background: #171d27; padding: 8px; border-radius: 6px; }
QPushButton#primaryButton { background: #51c995; color: #0b1712; border: 0; border-radius: 8px; padding: 11px 15px; font-weight: 700; }
QPushButton#primaryButton:hover { background: #68d9a9; }
QPushButton#secondaryButton { background: #202936; color: #dce4ef; border: 1px solid #344052; border-radius: 6px; padding: 5px 8px; }
QPushButton:disabled { color: #68758a; }
QLineEdit, QSpinBox, QComboBox, QTableWidget { background: #171d27; color: #e8edf5; border: 1px solid #344052; border-radius: 5px; padding: 5px; }
QHeaderView::section { background: #202936; color: #aab5c5; padding: 5px; border: 0; }
"""
