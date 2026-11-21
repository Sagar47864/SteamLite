"""Conservative foreground game detection without interacting with games."""

from __future__ import annotations

import os

from core.models import ProcessInfo

_KNOWN_GAME_EXES = {
    "valorant-win64-shipping.exe", "cs2.exe", "csgo.exe", "fortniteclient-win64-shipping.exe",
    "league of legends.exe", "leagueclient.exe", "dota2.exe", "overwatch.exe",
    "overwatch 2.exe", "gta5.exe", "rdr2.exe", "eldenring.exe", "apex_legends.exe",
    "rocketleague.exe", "minecraft.exe", "javaw.exe", "pubg.exe", "helldivers2.exe",
}


def foreground_pid() -> int | None:
    if os.name != "nt":
        return None
    try:
        import ctypes

        hwnd = ctypes.windll.user32.GetForegroundWindow()
        if not hwnd:
            return None
        pid = ctypes.c_ulong()
        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return int(pid.value) or None
    except Exception:
        return None


class GameDetector:
    def detect(self, processes: list[ProcessInfo], configured_executable: str = "") -> ProcessInfo | None:
        if configured_executable:
            target = os.path.basename(configured_executable).casefold()
            for process in processes:
                if process.name.casefold() == target or os.path.basename(process.executable).casefold() == target:
                    return process
            return None

        pid = foreground_pid()
        if pid is not None:
            for process in processes:
                if process.pid == pid and process.name.casefold() in _KNOWN_GAME_EXES:
                    return process
        return None
