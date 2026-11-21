"""Select possible background process candidates; never takes action itself."""

from __future__ import annotations

from core.models import ProcessInfo
from core.process_manager import ProcessManager


class OptimizationEngine:
    def candidates(
        self,
        processes: list[ProcessInfo],
        game_pid: int | None,
        ignored_names: set[str],
        limit: int = 5,
    ) -> list[ProcessInfo]:
        candidates = [
            process for process in processes
            if process.pid != game_pid
            and process.memory_bytes >= 250 * 1024 * 1024
            and process.name.casefold() not in ignored_names
            and not ProcessManager.is_protected(process.name)
        ]
        return sorted(candidates, key=lambda process: process.memory_bytes, reverse=True)[:limit]
