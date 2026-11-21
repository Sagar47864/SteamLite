"""Read-only display of saved local Stream Mode sessions."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtWidgets import QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from database.database import SessionDatabase


class HistoryPage(QWidget):
    def __init__(self, database: SessionDatabase) -> None:
        super().__init__()
        self.database = database
        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 32, 36, 32)
        heading = QLabel("Session History")
        heading.setObjectName("pageTitle")
        layout.addWidget(heading)
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(["Started", "Game", "Avg CPU", "Peak CPU", "Avg GPU", "Avg RAM", "Network drops", "Stability"])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)
        self.refresh()

    def refresh(self) -> None:
        sessions = self.database.recent_sessions()
        self.table.setRowCount(len(sessions))
        for row, session in enumerate(sessions):
            started = session["started_at"]
            try:
                started = datetime.fromisoformat(started).strftime("%d %b %Y %H:%M")
            except (TypeError, ValueError):
                pass
            values = [
                started, session["game"] or "None", self._percent(session["average_cpu"]),
                self._percent(session["peak_cpu"]), self._percent(session["average_gpu"]),
                self._percent(session["average_ram"]),
                str(session["network_dropped_frames"]) if session["network_dropped_frames"] is not None else "Unavailable",
                f"{session['stability']} / 100" if session["stability"] is not None else "Unavailable",
            ]
            for column, value in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(str(value)))

    @staticmethod
    def _percent(value) -> str:
        return f"{value:.1f}%" if value is not None else "Unavailable"
