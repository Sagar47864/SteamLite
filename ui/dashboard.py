"""Live Stream Mode dashboard with values sourced from monitor snapshots."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QMessageBox,
    QPushButton, QScrollArea, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from config.settings import SettingsStore
from core.models import ProcessInfo, SystemSnapshot
from core.optimization_engine import OptimizationEngine


def _bytes(value: int | None) -> str:
    if value is None:
        return "Unavailable"
    if value >= 1024 ** 3:
        return f"{value / 1024 ** 3:.1f} GB"
    return f"{value / 1024 ** 2:.0f} MB"


def _percent(value: float | int | None) -> str:
    return f"{value:.1f}%" if value is not None else "Unavailable"


class DashboardPage(QWidget):
    stream_toggle_requested = Signal()
    priority_requested = Signal(str)
    close_process_requested = Signal(int, str, float)

    def __init__(self, settings: SettingsStore) -> None:
        super().__init__()
        self.settings = settings
        self.optimizations = OptimizationEngine()
        self._ignored_this_session: set[str] = set()
        self._process_rows: dict[int, int] = {}
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        outer = QVBoxLayout(content)
        outer.setContentsMargins(32, 24, 32, 24)
        outer.setSpacing(12)

        header = QHBoxLayout()
        title_block = QVBoxLayout()
        title = QLabel("Dashboard")
        title.setObjectName("pageTitle")
        subtitle = QLabel("Live system telemetry and OBS health")
        subtitle.setObjectName("muted")
        title_block.addWidget(title)
        title_block.addWidget(subtitle)
        header.addLayout(title_block)
        header.addStretch(1)
        self.mode_status = QLabel("STREAM MODE  •  INACTIVE")
        self.mode_status.setObjectName("muted")
        header.addWidget(self.mode_status)
        self.stream_button = QPushButton("START STREAM MODE")
        self.stream_button.setObjectName("primaryButton")
        self.stream_button.clicked.connect(self.stream_toggle_requested.emit)
        header.addWidget(self.stream_button)
        outer.addLayout(header)

        self.warning = QLabel("Monitoring is off. Start Stream Mode to collect actual system measurements.")
        self.warning.setObjectName("notice")
        self.warning.setWordWrap(True)
        outer.addWidget(self.warning)

        grid = QGridLayout()
        grid.setSpacing(10)
        self.metrics = {}
        metric_names = ["CPU", "RAM", "GPU", "Disk", "Network", "Game FPS"]
        for index, name in enumerate(metric_names):
            card, value, detail = self._metric_card(name)
            self.metrics[name] = (value, detail)
            grid.addWidget(card, index // 3, index % 3)
        outer.addLayout(grid)

        secondary = QHBoxLayout()
        secondary.setSpacing(10)
        game_card = self._card()
        game_layout = QVBoxLayout(game_card)
        game_layout.setContentsMargins(15, 12, 15, 12)
        game_heading = QLabel("DETECTED GAME")
        game_heading.setObjectName("sectionHeading")
        self.game_value = QLabel("None")
        self.game_value.setStyleSheet("font-size: 15pt; font-weight: 700;")
        self.game_detail = QLabel("Game process metrics unavailable")
        self.game_detail.setObjectName("muted")
        priority_row = QHBoxLayout()
        self.priority = QComboBox()
        self.priority.addItem("Normal", "normal")
        self.priority.addItem("Above Normal", "above_normal")
        self.priority.addItem("High", "high")
        self.priority.setCurrentIndex(1)
        priority_apply = QPushButton("Set priority")
        priority_apply.setObjectName("secondaryButton")
        priority_apply.clicked.connect(lambda: self.priority_requested.emit(self.priority.currentData()))
        priority_row.addWidget(self.priority, 1)
        priority_row.addWidget(priority_apply)
        explanation = QLabel("High priority may cause instability if used aggressively. Original priority is restored when Stream Mode stops.")
        explanation.setObjectName("muted")
        explanation.setWordWrap(True)
        game_layout.addWidget(game_heading)
        game_layout.addWidget(self.game_value)
        game_layout.addWidget(self.game_detail)
        game_layout.addLayout(priority_row)
        game_layout.addWidget(explanation)
        secondary.addWidget(game_card, 1)

        obs_card = self._card()
        obs_layout = QVBoxLayout(obs_card)
        obs_layout.setContentsMargins(15, 12, 15, 12)
        obs_heading = QLabel("OBS STUDIO")
        obs_heading.setObjectName("sectionHeading")
        self.obs_status = QLabel("○  Not connected")
        self.obs_scene = QLabel("Scene: Unavailable")
        self.obs_stream = QLabel("Stream: Unavailable   ·   Recording: Unavailable")
        self.obs_output = QLabel("Output: Unavailable   ·   FPS: Unavailable")
        self.obs_bitrate = QLabel("Bitrate: Unavailable   ·   Duration: Unavailable")
        for label in (self.obs_scene, self.obs_stream, self.obs_output, self.obs_bitrate):
            label.setObjectName("muted")
        obs_layout.addWidget(obs_heading)
        obs_layout.addWidget(self.obs_status)
        obs_layout.addWidget(self.obs_scene)
        obs_layout.addWidget(self.obs_stream)
        obs_layout.addWidget(self.obs_output)
        obs_layout.addWidget(self.obs_bitrate)
        obs_layout.addStretch(1)
        secondary.addWidget(obs_card, 1)
        outer.addLayout(secondary)

        health_row = QHBoxLayout()
        health_card = self._card()
        health_layout = QVBoxLayout(health_card)
        health_layout.setContentsMargins(15, 12, 15, 12)
        health_layout.addWidget(self._heading("STREAM STABILITY (APPROXIMATE)"))
        self.score_value = QLabel("Unavailable")
        self.score_value.setStyleSheet("font-size: 22pt; font-weight: 700; color: #78d8b0;")
        health_layout.addWidget(self.score_value)
        self.health_detail = QLabel("CPU: —   GPU: —   RAM: —   OBS: —   Network: —")
        self.health_detail.setObjectName("muted")
        health_layout.addWidget(self.health_detail)
        health_row.addWidget(health_card, 1)

        lag_card = self._card()
        lag_layout = QVBoxLayout(lag_card)
        lag_layout.setContentsMargins(15, 12, 15, 12)
        lag_layout.addWidget(self._heading("OBS OUTPUT HEALTH"))
        self.dropped_value = QLabel("Network dropped frames: Unavailable")
        self.render_value = QLabel("Rendering lag: Unavailable")
        self.encode_value = QLabel("Encoding lag: Unavailable")
        for label in (self.dropped_value, self.render_value, self.encode_value):
            lag_layout.addWidget(label)
        health_row.addWidget(lag_card, 1)
        outer.addLayout(health_row)

        process_card = self._card()
        process_layout = QVBoxLayout(process_card)
        process_layout.setContentsMargins(15, 12, 15, 12)
        process_layout.addWidget(self._heading("TOP PROCESSES AND POSSIBLE BACKGROUND OPTIMIZATIONS"))
        self.process_table = QTableWidget(0, 4)
        self.process_table.setHorizontalHeaderLabels(["Process", "CPU", "RAM", "User action"])
        self.process_table.verticalHeader().setVisible(False)
        self.process_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.process_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.process_table.horizontalHeader().setStretchLastSection(True)
        self.process_table.setMaximumHeight(180)
        process_layout.addWidget(self.process_table)
        outer.addWidget(process_card, 1)
        scroll.setWidget(content)
        root.addWidget(scroll)

    @staticmethod
    def _card() -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        return card

    @staticmethod
    def _heading(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("sectionHeading")
        return label

    def _metric_card(self, name: str) -> tuple[QFrame, QLabel, QLabel]:
        card = self._card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 11, 14, 11)
        layout.setSpacing(4)
        label = QLabel(name.upper())
        label.setObjectName("muted")
        value = QLabel("Unavailable")
        value.setStyleSheet("font-size: 20pt; font-weight: 700;")
        detail = QLabel("Stream Mode inactive")
        detail.setObjectName("muted")
        layout.addWidget(label)
        layout.addWidget(value)
        layout.addWidget(detail)
        return card, value, detail

    def set_stream_active(self, active: bool, stopping: bool = False) -> None:
        self.stream_button.setEnabled(not stopping)
        if stopping:
            self.stream_button.setText("STOPPING…")
            self.mode_status.setText("STREAM MODE  •  STOPPING")
            return
        self.stream_button.setText("STOP STREAM MODE" if active else "START STREAM MODE")
        self.mode_status.setText("STREAM MODE  •  ACTIVE" if active else "STREAM MODE  •  INACTIVE")
        if not active:
            self.warning.setText("Monitoring is off. Start Stream Mode to collect actual system measurements.")

    def update_snapshot(self, snapshot: SystemSnapshot) -> None:
        self.metrics["CPU"][0].setText(_percent(snapshot.cpu_percent))
        self.metrics["CPU"][1].setText(f"Temperature: {snapshot.cpu_temperature:.0f} °C" if snapshot.cpu_temperature is not None else "Temperature unavailable")
        self.metrics["RAM"][0].setText(_percent(snapshot.ram_percent))
        self.metrics["RAM"][1].setText(f"{_bytes(snapshot.ram_used)} used  ·  {_bytes(snapshot.ram_available)} available")
        self.metrics["GPU"][0].setText(_percent(snapshot.gpu_percent))
        gpu_detail = f"VRAM: {_percent(snapshot.gpu_memory_percent)} · {_bytes(snapshot.gpu_memory_used)} / {_bytes(snapshot.gpu_memory_total)}"
        if snapshot.gpu_temperature is not None:
            gpu_detail += f" · {snapshot.gpu_temperature:.0f} °C"
        self.metrics["GPU"][1].setText(gpu_detail if snapshot.gpu_percent is not None else "GPU telemetry unavailable")
        self.metrics["Disk"][0].setText(_percent(snapshot.disk_percent))
        self.metrics["Disk"][1].setText("System volume usage")
        self.metrics["Network"][0].setText(f"↑ {_bytes_rate(snapshot.upload_bytes_per_sec)}  ↓ {_bytes_rate(snapshot.download_bytes_per_sec)}")
        self.metrics["Network"][1].setText("System network interface throughput")
        self.metrics["Game FPS"][0].setText("Unavailable")
        self.metrics["Game FPS"][1].setText("FPS is not exposed by a safe system API")

        game = snapshot.game
        self.game_value.setText(game.name if game else "None")
        self.game_detail.setText(
            f"CPU: {game.cpu_percent:.1f}%  ·  RAM: {_bytes(game.memory_bytes)}" if game else "No configured or recognized foreground game detected"
        )
        self.priority.setEnabled(game is not None)

        obs = snapshot.obs
        if obs.get("connected"):
            self.obs_status.setText("●  Connected")
            self.obs_status.setStyleSheet("color: #78d8b0; font-weight: 600;")
            self.obs_scene.setText(f"Scene: {obs.get('scene', 'Unavailable')}")
            self.obs_stream.setText(f"Stream: {'LIVE' if obs.get('streaming') else 'Off'}   ·   Recording: {'On' if obs.get('recording') else 'Off'}")
            fps = _fps(obs.get("fps_num"), obs.get("fps_den"))
            self.obs_output.setText(f"Output: {_resolution(obs.get('width'), obs.get('height'))}   ·   FPS: {fps}   ·   Encoder: {obs.get('encoder', 'Unavailable')}")
            bitrate = obs.get("bitrate_kbps")
            bitrate_text = f"{bitrate:.0f} kb/s" if bitrate is not None else "Unavailable"
            self.obs_bitrate.setText(f"Avg bitrate: {bitrate_text}   ·   Duration: {obs.get('stream_duration', 'Unavailable')}")
        else:
            self.obs_status.setText("○  Not connected")
            self.obs_status.setStyleSheet("color: #e4b968; font-weight: 600;")
            error = obs.get("error") or "OBS not configured or unavailable; system monitoring continues."
            self.obs_scene.setText(f"Scene: {error[:90]}")
            self.obs_stream.setText("Stream: Unavailable   ·   Recording: Unavailable")
            self.obs_output.setText("Output: Unavailable   ·   FPS: Unavailable")
            self.obs_bitrate.setText("Bitrate: Unavailable   ·   Duration: Unavailable")

        dropped_frames = obs.get("network_dropped_frames")
        dropped_text = str(dropped_frames) if dropped_frames is not None else "Unavailable"
        self.dropped_value.setText(f"Network dropped frames: {dropped_text} ({_percent(obs.get('network_dropped_percent'))})")
        self.render_value.setText(f"Rendering lag: {_percent(obs.get('rendering_lag_percent'))}")
        self.encode_value.setText(f"Encoding lag: {_percent(obs.get('encoding_lag_percent'))}")
        self.score_value.setText(f"{snapshot.stability} / 100")
        health = snapshot.health
        self.health_detail.setText("   ".join(f"{key}: {value}" for key, value in health.items()))

        if snapshot.warnings:
            self.warning.setText("  •  ".join(snapshot.warnings))
            self.warning.setStyleSheet("color: #f0bd68; background: #292318; padding: 8px; border-radius: 6px;")
        else:
            self.warning.setText("Stream health checks are active. No current threshold warnings.")
            self.warning.setStyleSheet("color: #8d9aab; background: #171d27; padding: 8px; border-radius: 6px;")

        self._update_processes(snapshot)

    def _update_processes(self, snapshot: SystemSnapshot) -> None:
        processes = {item.pid: item for item in snapshot.top_cpu + snapshot.top_memory}
        candidates = self.optimizations.candidates(
            list(processes.values()), snapshot.game.pid if snapshot.game else None,
            self.settings.ignored_processes() | self._ignored_this_session,
        )
        display = sorted(processes.values(), key=lambda item: item.memory_bytes, reverse=True)[:5]
        display_ids = {item.pid for item in display}
        for candidate in candidates:
            if len(display_ids) < 5:
                display.append(candidate)
                display_ids.add(candidate.pid)
        signature = [(item.pid, item.name, item in candidates) for item in display]
        existing_signature = getattr(self, "_signature", None)
        if signature != existing_signature:
            self._signature = signature
            self.process_table.setRowCount(len(display))
            self._process_rows = {item.pid: row for row, item in enumerate(display)}
            for row, process in enumerate(display):
                self.process_table.setItem(row, 0, QTableWidgetItem(process.name))
                self.process_table.setItem(row, 1, QTableWidgetItem(_percent(process.cpu_percent)))
                self.process_table.setItem(row, 2, QTableWidgetItem(_bytes(process.memory_bytes)))
                actions = QWidget()
                action_layout = QHBoxLayout(actions)
                action_layout.setContentsMargins(2, 1, 2, 1)
                candidate = process in candidates
                if candidate:
                    close = QPushButton("Close")
                    close.setObjectName("secondaryButton")
                    close.clicked.connect(lambda checked=False, p=process: self._confirm_close(p))
                    ignore = QPushButton("Ignore")
                    ignore.setObjectName("secondaryButton")
                    ignore.clicked.connect(lambda checked=False, name=process.name: self._ignore(name, False))
                    always = QPushButton("Always ignore")
                    always.setObjectName("secondaryButton")
                    always.clicked.connect(lambda checked=False, name=process.name: self._ignore(name, True))
                    for button in (close, ignore, always):
                        action_layout.addWidget(button)
                else:
                    action_layout.addWidget(QLabel("—"))
                self.process_table.setCellWidget(row, 3, actions)
        else:
            for process in display:
                row = self._process_rows.get(process.pid)
                if row is not None:
                    self.process_table.item(row, 1).setText(_percent(process.cpu_percent))
                    self.process_table.item(row, 2).setText(_bytes(process.memory_bytes))

    def _confirm_close(self, process: ProcessInfo) -> None:
        result = QMessageBox.warning(
            self,
            "Close application?",
            f"StreamLite wants to close {process.name} because it is using {_bytes(process.memory_bytes)} of RAM.\n\nThe process will not be force-terminated if it does not exit promptly.",
            QMessageBox.StandardButton.Close | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if result == QMessageBox.StandardButton.Close:
            self.close_process_requested.emit(process.pid, process.name, process.creation_time or -1.0)

    def _ignore(self, name: str, always: bool) -> None:
        if always:
            self.settings.add_ignored_process(name)
        else:
            self._ignored_this_session.add(name.casefold())


def _bytes_rate(value: float) -> str:
    if value >= 1024 ** 2:
        return f"{value / 1024 ** 2:.1f} MB/s"
    if value >= 1024:
        return f"{value / 1024:.0f} KB/s"
    return f"{value:.0f} B/s"


def _resolution(width, height) -> str:
    return f"{width} × {height}" if width and height else "Unavailable"


def _fps(numerator, denominator) -> str:
    try:
        return f"{int(numerator) / int(denominator):g}" if numerator and denominator else "Unavailable"
    except (TypeError, ValueError, ZeroDivisionError):
        return "Unavailable"
