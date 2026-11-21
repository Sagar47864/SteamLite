"""QThread worker that samples once per second and never touches UI widgets."""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any

import psutil
from PySide6.QtCore import QThread, Signal

from config.settings import AppSettings
from core.game_detector import GameDetector
from core.models import ProcessInfo, SystemSnapshot
from core.performance_analyzer import PerformanceAnalyzer
from core.system_monitor import SystemMonitor
from obs.obs_client import ObsClient


class MonitorWorker(QThread):
    snapshot_ready = Signal(object)
    summary_ready = Signal(object)

    def __init__(self, settings: AppSettings, parent=None) -> None:
        super().__init__(parent)
        self.settings = settings
        self._system: SystemMonitor | None = None
        self._obs: ObsClient | None = None
        self._obs_status: dict[str, Any] = {"connected": False, "error": "Not connected"}
        self._last_obs_poll = 0.0
        self._last_connection_attempt = 0.0
        self._analyzer = PerformanceAnalyzer()
        self._game_detector = GameDetector()
        self._sample_count = 0
        self._sum_cpu = 0.0
        self._sum_gpu = 0.0
        self._gpu_count = 0
        self._sum_ram = 0.0
        self._peak_cpu = 0.0
        self._peak_gpu: float | None = None
        self._peak_ram = 0.0
        self._sum_score = 0
        self._last_game = "None"
        self._latest_obs = self._obs_status
        self._session_dropped_frames = 0
        self._completed_stream_drops = 0
        self._network_counter_baseline: int | None = None
        self._last_network_counter: int | None = None
        self._session_peak_metrics: dict[str, float | None] = {
            "network_dropped_percent": None,
            "rendering_lag_percent": None,
            "encoding_lag_percent": None,
        }
        self._started_at = datetime.now().astimezone().isoformat(timespec="seconds")

    def run(self) -> None:
        deadline = time.monotonic()
        try:
            self._system = SystemMonitor()
            deadline += self.settings.monitoring_interval
            while not self.isInterruptionRequested():
                while not self.isInterruptionRequested() and time.monotonic() < deadline:
                    time.sleep(min(0.1, deadline - time.monotonic()))
                if self.isInterruptionRequested():
                    break
                now = time.monotonic()
                metrics = self._system.sample()
                processes = [ProcessInfo(**item) for item in metrics.pop("processes")]
                game = self._game_detector.detect(processes, self.settings.game_executable)
                if game is not None:
                    self._last_game = game.name

                if now - self._last_obs_poll >= 3.0:
                    self._poll_obs(now)
                    self._last_obs_poll = now

                stability, health, warnings = self._analyzer.analyze(
                    metrics["cpu_percent"], metrics["gpu_percent"], metrics["ram_percent"], self._obs_status
                )
                top_cpu = sorted(processes, key=lambda item: item.cpu_percent, reverse=True)[:5]
                top_memory = sorted(processes, key=lambda item: item.memory_bytes, reverse=True)[:5]
                snapshot = SystemSnapshot(
                    **metrics,
                    top_cpu=top_cpu,
                    top_memory=top_memory,
                    game=game,
                    obs=dict(self._obs_status),
                    stability=stability,
                    health=health,
                    warnings=warnings,
                )
                self._record(snapshot)
                self.snapshot_ready.emit(snapshot)
                deadline += self.settings.monitoring_interval
        except Exception as exc:
            self.snapshot_ready.emit({"worker_error": str(exc)})
        finally:
            if self._obs is not None:
                self._obs.disconnect()
            if self._system is not None:
                self._system.close()
            self.summary_ready.emit(self._summary())

    def _poll_obs(self, now: float) -> None:
        if self._obs is None and now - self._last_connection_attempt < 5.0:
            return
        if self._obs is None:
            self._last_connection_attempt = now
            self._obs = ObsClient(self.settings.obs_host, self.settings.obs_port, self.settings.obs_password)
        status = self._obs.poll()
        self._obs_status = status
        self._latest_obs = status
        if not status.get("connected"):
            self._obs = None

    def _record(self, sample: SystemSnapshot) -> None:
        self._sample_count += 1
        self._sum_cpu += sample.cpu_percent
        self._sum_ram += sample.ram_percent
        self._peak_cpu = max(self._peak_cpu, sample.cpu_percent)
        self._peak_ram = max(self._peak_ram, sample.ram_percent)
        if sample.gpu_percent is not None:
            self._sum_gpu += sample.gpu_percent
            self._gpu_count += 1
            self._peak_gpu = max(self._peak_gpu or 0.0, sample.gpu_percent)
        self._sum_score += sample.stability
        obs = sample.obs
        if obs.get("streaming") and obs.get("network_dropped_frames") is not None:
            current = int(obs["network_dropped_frames"])
            if self._network_counter_baseline is None or (
                self._last_network_counter is not None and current < self._last_network_counter
            ):
                if self._last_network_counter is not None and self._network_counter_baseline is not None:
                    self._completed_stream_drops += max(0, self._last_network_counter - self._network_counter_baseline)
                self._network_counter_baseline = current
            self._last_network_counter = current
            self._session_dropped_frames = self._completed_stream_drops + max(0, current - self._network_counter_baseline)
        for key in self._session_peak_metrics:
            value = obs.get(key)
            if value is not None:
                previous = self._session_peak_metrics[key]
                self._session_peak_metrics[key] = max(previous or 0.0, float(value))

    def _summary(self) -> dict[str, Any]:
        count = max(1, self._sample_count)
        return {
            "started_at": self._started_at,
            "ended_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "game": self._last_game,
            "average_cpu": self._sum_cpu / count if self._sample_count else None,
            "peak_cpu": self._peak_cpu if self._sample_count else None,
            "average_gpu": self._sum_gpu / self._gpu_count if self._gpu_count else None,
            "peak_gpu": self._peak_gpu,
            "average_ram": self._sum_ram / count if self._sample_count else None,
            "peak_ram": self._peak_ram if self._sample_count else None,
            "network_dropped_percent": self._session_peak_metrics["network_dropped_percent"],
            "network_dropped_frames": self._session_dropped_frames if self._network_counter_baseline is not None else None,
            "rendering_lag_percent": self._session_peak_metrics["rendering_lag_percent"],
            "encoding_lag_percent": self._session_peak_metrics["encoding_lag_percent"],
            "stability": round(self._sum_score / count) if self._sample_count else None,
        }
