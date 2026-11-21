"""Conservative thresholds and a plainly labeled, approximate health score."""

from __future__ import annotations

import time
from typing import Any


class PerformanceAnalyzer:
    def __init__(self) -> None:
        self._cpu_high_since: float | None = None
        self._gpu_high_since: float | None = None
        self._last_obs_counters: dict[str, float] = {}

    def analyze(self, cpu: float, gpu: float | None, ram: float, obs: dict[str, Any]) -> tuple[int, dict[str, str], list[str]]:
        now = time.monotonic()
        warnings: list[str] = []
        self._cpu_high_since = self._threshold_since(cpu > 90, self._cpu_high_since, now)
        self._gpu_high_since = self._threshold_since(gpu is not None and gpu > 95, self._gpu_high_since, now)
        if self._cpu_high_since is not None and now - self._cpu_high_since >= 10:
            warnings.append("High CPU usage detected (over 90% for at least 10 seconds).")
        if self._gpu_high_since is not None and now - self._gpu_high_since >= 10:
            warnings.append("GPU is nearly fully utilized (over 95% for at least 10 seconds).")

        if (obs.get("rendering_lag_percent") or 0) >= 1:
            warnings.append(f"OBS rendering is overloaded ({obs['rendering_lag_percent']:.1f}% rendering lag).")
        if (obs.get("encoding_lag_percent") or 0) >= 1:
            warnings.append(f"OBS encoder is overloaded ({obs['encoding_lag_percent']:.1f}% encoding lag).")
        if obs.get("network_dropped_percent") is not None and obs["network_dropped_percent"] > 0:
            warnings.append("Network-related dropped frames reported by OBS.")

        health = {
            "CPU": "Good" if cpu < 80 else "Busy" if cpu <= 90 else "High",
            "GPU": "Unavailable" if gpu is None else "Good" if gpu < 85 else "Busy" if gpu <= 95 else "High",
            "RAM": "Good" if ram < 85 else "Busy" if ram <= 95 else "High",
            "OBS": "Unavailable" if not obs.get("connected") else "Good",
            "Network": "Unavailable" if obs.get("network_dropped_percent") is None else "Good" if obs.get("network_dropped_percent", 0) == 0 else "Dropped frames",
        }
        score = 100
        score -= max(0, int((cpu - 65) * 0.5))
        if gpu is not None:
            score -= max(0, int((gpu - 75) * 0.35))
        score -= max(0, int((ram - 75) * 0.4))
        score -= min(25, int((obs.get("rendering_lag_percent") or 0) * 2))
        score -= min(25, int((obs.get("encoding_lag_percent") or 0) * 2))
        if obs.get("network_dropped_percent") is not None:
            score -= min(20, int(obs["network_dropped_percent"] * 4))
        return max(0, min(100, score)), health, warnings

    @staticmethod
    def _threshold_since(active: bool, since: float | None, now: float) -> float | None:
        if not active:
            return None
        return since if since is not None else now
