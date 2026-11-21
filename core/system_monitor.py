"""Low-frequency system sampling using psutil and optional NVML."""

from __future__ import annotations

import time
from typing import Any

import psutil

try:
    import pynvml
except ImportError:  # NVIDIA telemetry is optional
    pynvml = None


class SystemMonitor:
    def __init__(self) -> None:
        self._net_last = psutil.net_io_counters()
        self._net_time = time.monotonic()
        psutil.cpu_percent(None)  # Prime psutil's non-blocking CPU sampler.
        self._nvml_ready = False
        self._gpu_handle: Any = None
        self._prime_process_cpu()

    @staticmethod
    def _prime_process_cpu() -> None:
        for process in psutil.process_iter():
            try:
                process.cpu_percent(None)
            except (psutil.Error, OSError):
                continue

    def sample(self) -> dict[str, Any]:
        virtual = psutil.virtual_memory()
        cpu = psutil.cpu_percent(None)
        now = time.monotonic()
        net = psutil.net_io_counters()
        elapsed = max(now - self._net_time, 0.001)
        upload = max(0, net.bytes_sent - self._net_last.bytes_sent) / elapsed
        download = max(0, net.bytes_recv - self._net_last.bytes_recv) / elapsed
        self._net_last, self._net_time = net, now

        processes: list[dict[str, Any]] = []
        for process in psutil.process_iter(["pid", "name", "memory_info", "exe", "create_time"]):
            try:
                info = process.info
                memory = info.get("memory_info")
                processes.append({
                    "pid": int(info["pid"]),
                    "name": str(info.get("name") or "Unknown"),
                    "cpu_percent": max(0.0, process.cpu_percent(None)),
                    "memory_bytes": int(memory.rss) if memory else 0,
                    "executable": str(info.get("exe") or ""),
                    "creation_time": float(info["create_time"]) if info.get("create_time") is not None else None,
                })
            except (psutil.Error, OSError, TypeError, ValueError, KeyError):
                continue

        disk_percent: float | None = None
        try:
            disk_percent = float(psutil.disk_usage(psutil.disk_partitions(all=False)[0].mountpoint).percent)
        except (psutil.Error, OSError, IndexError):
            pass

        cpu_temp = self._cpu_temperature()
        gpu_percent, gpu_mem_percent, gpu_mem_used, gpu_mem_total, gpu_temp = self._gpu_metrics()
        return {
            "timestamp": time.time(),
            "cpu_percent": cpu,
            "ram_percent": float(virtual.percent),
            "ram_used": int(virtual.used),
            "ram_available": int(virtual.available),
            "gpu_percent": gpu_percent,
            "gpu_memory_percent": gpu_mem_percent,
            "gpu_memory_used": gpu_mem_used,
            "gpu_memory_total": gpu_mem_total,
            "cpu_temperature": cpu_temp,
            "gpu_temperature": gpu_temp,
            "disk_percent": disk_percent,
            "upload_bytes_per_sec": upload,
            "download_bytes_per_sec": download,
            "processes": processes,
        }

    @staticmethod
    def _cpu_temperature() -> float | None:
        try:
            sensors = psutil.sensors_temperatures(fahrenheit=False)
            for readings in sensors.values():
                for reading in readings:
                    if reading.current is not None:
                        return float(reading.current)
        except (AttributeError, OSError, psutil.Error):
            pass
        return None

    def _gpu_metrics(self) -> tuple[float | None, float | None, int | None, int | None, float | None]:
        if pynvml is None:
            return None, None, None, None, None
        try:
            if not self._nvml_ready:
                pynvml.nvmlInit()
                self._gpu_handle = pynvml.nvmlDeviceGetHandleByIndex(0)
                self._nvml_ready = True
            utilization = pynvml.nvmlDeviceGetUtilizationRates(self._gpu_handle)
            memory = pynvml.nvmlDeviceGetMemoryInfo(self._gpu_handle)
            try:
                temperature = float(pynvml.nvmlDeviceGetTemperature(self._gpu_handle, pynvml.NVML_TEMPERATURE_GPU))
            except Exception:
                temperature = None
            memory_percent = (memory.used / memory.total * 100.0) if memory.total else 0.0
            return float(utilization.gpu), memory_percent, int(memory.used), int(memory.total), temperature
        except Exception:
            return None, None, None, None, None

    def close(self) -> None:
        if self._nvml_ready and pynvml is not None:
            try:
                pynvml.nvmlShutdown()
            except Exception:
                pass
            self._nvml_ready = False
