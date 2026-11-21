"""Run confirmed process-close requests outside the GUI thread."""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from core.process_manager import ProcessManager


class ProcessActionWorker(QThread):
    finished_message = Signal(bool, str)

    def __init__(self, pid: int, expected_name: str, expected_created_at: float | None, parent=None) -> None:
        super().__init__(parent)
        self.pid = pid
        self.expected_name = expected_name
        self.expected_created_at = expected_created_at

    def run(self) -> None:
        success, message = ProcessManager().close_process(self.pid, self.expected_name, self.expected_created_at)
        self.finished_message.emit(success, message)
