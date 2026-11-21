"""Data structures exchanged between the worker and UI."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ProcessInfo:
    pid: int
    name: str
    cpu_percent: float
    memory_bytes: int
    executable: str = ""
    creation_time: float | None = None


@dataclass
class SystemSnapshot:
    timestamp: float
    cpu_percent: float
    ram_percent: float
    ram_used: int
    ram_available: int
    gpu_percent: float | None
    gpu_memory_percent: float | None
    gpu_memory_used: int | None
    gpu_memory_total: int | None
    cpu_temperature: float | None
    gpu_temperature: float | None
    disk_percent: float | None
    upload_bytes_per_sec: float
    download_bytes_per_sec: float
    top_cpu: list[ProcessInfo] = field(default_factory=list)
    top_memory: list[ProcessInfo] = field(default_factory=list)
    game: ProcessInfo | None = None
    obs: dict[str, Any] = field(default_factory=dict)
    stability: int = 0
    health: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
