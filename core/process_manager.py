"""Explicitly confirmed process close and reversible game priority changes."""

from __future__ import annotations

import os
import psutil

_PROTECTED = {
    "system", "system idle process", "registry", "smss.exe", "csrss.exe", "wininit.exe",
    "services.exe", "lsass.exe", "winlogon.exe", "svchost.exe", "fontdrvhost.exe",
    "dwm.exe", "explorer.exe", "audiodg.exe", "securityhealthservice.exe",
    "msmpeng.exe", "nissrv.exe", "nvcontainer.exe", "nvdisplay.container.exe",
    "amdfendrsr.exe", "atieclxx.exe", "atiesrxx.exe", "igfxem.exe",
}
_PROTECTED_PARTS = (
    "defender", "antivirus", "antimalware", "malwarebytes", "security", "firewall",
    "crowdstrike", "sentinel", "driver", "service host", "network service", "vpn",
    "wireguard", "wlan", "dhcp", "audio service", "realtek",
)


class ProcessManager:
    def __init__(self) -> None:
        self._original_priorities: dict[int, tuple[int, float, str]] = {}

    @staticmethod
    def is_protected(name: str) -> bool:
        normalized = name.casefold()
        return normalized in _PROTECTED or any(part in normalized for part in _PROTECTED_PARTS)

    def close_process(
        self, pid: int, expected_name: str | None = None, expected_created_at: float | None = None
    ) -> tuple[bool, str]:
        try:
            process = psutil.Process(pid)
            current_name = process.name()
            if expected_name and current_name.casefold() != expected_name.casefold():
                return False, "The process changed since it was listed. Refresh the dashboard before trying again."
            if expected_created_at is not None and abs(process.create_time() - expected_created_at) > 0.01:
                return False, "The process changed since it was listed. Refresh the dashboard before trying again."
            if self.is_protected(current_name):
                return False, "StreamLite will not close a protected Windows or security process."
            if os.name == "nt":
                if not self._request_windows_close(pid):
                    return False, "No closable application window was found. StreamLite did not terminate the process."
            else:
                process.terminate()
            try:
                process.wait(timeout=5)
            except psutil.TimeoutExpired:
                return False, "The application did not close within 5 seconds. It was not force-terminated."
            return True, "Application closed."
        except psutil.NoSuchProcess:
            return False, "The application has already exited."
        except (psutil.AccessDenied, psutil.Error, OSError) as exc:
            return False, f"Could not close the application: {exc}"

    @staticmethod
    def _request_windows_close(pid: int) -> bool:
        """Send WM_CLOSE to the process's windows; never force-kill on Windows."""
        try:
            import ctypes

            user32 = ctypes.windll.user32
            user32.GetWindowThreadProcessId.argtypes = (ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong))
            user32.GetWindowThreadProcessId.restype = ctypes.c_ulong
            user32.IsWindowVisible.argtypes = (ctypes.c_void_p,)
            user32.IsWindowVisible.restype = ctypes.c_bool
            user32.PostMessageW.argtypes = (ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t)
            user32.PostMessageW.restype = ctypes.c_bool
            window_pids: list[int] = []
            callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

            def inspect_window(hwnd, _lparam):
                window_pid = ctypes.c_ulong()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(window_pid))
                if int(window_pid.value) == pid and user32.IsWindowVisible(hwnd):
                    window_pids.append(int(hwnd))
                return True

            callback = callback_type(inspect_window)
            user32.EnumWindows.argtypes = (callback_type, ctypes.c_void_p)
            user32.EnumWindows.restype = ctypes.c_bool
            user32.EnumWindows(callback, 0)
            for hwnd in window_pids:
                user32.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE
            return bool(window_pids)
        except Exception:
            return False

    def set_game_priority(
        self, pid: int, priority: str, expected_name: str | None = None,
        expected_created_at: float | None = None,
    ) -> tuple[bool, str]:
        if priority not in {"normal", "above_normal", "high"}:
            return False, "Unsupported priority. Realtime priority is not available."
        try:
            process = psutil.Process(pid)
            if expected_name and process.name().casefold() != expected_name.casefold():
                return False, "The detected game process changed. Detect the game again before changing priority."
            if expected_created_at is not None and abs(process.create_time() - expected_created_at) > 0.01:
                return False, "The detected game process changed. Detect the game again before changing priority."
            if pid not in self._original_priorities:
                self._original_priorities[pid] = (process.nice(), process.create_time(), process.name())
            if hasattr(psutil, "ABOVE_NORMAL_PRIORITY_CLASS"):
                values = {
                    "normal": psutil.NORMAL_PRIORITY_CLASS,
                    "above_normal": psutil.ABOVE_NORMAL_PRIORITY_CLASS,
                    "high": psutil.HIGH_PRIORITY_CLASS,
                }
                process.nice(values[priority])
            else:
                values = {"normal": 0, "above_normal": -5, "high": -10}
                process.nice(values[priority])
            return True, f"Game priority set to {priority.replace('_', ' ').title()}."
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.Error, OSError) as exc:
            return False, f"Could not change game priority: {exc}"

    def restore_priorities(self) -> list[str]:
        messages: list[str] = []
        for pid, (original, created_at, name) in self._original_priorities.items():
            try:
                process = psutil.Process(pid)
                if process.name() != name or abs(process.create_time() - created_at) > 0.01:
                    messages.append(f"Skipped priority restoration for PID {pid}; that process has exited or changed.")
                    continue
                process.nice(original)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.Error, OSError) as exc:
                messages.append(f"Could not restore priority for PID {pid}: {exc}")
        self._original_priorities.clear()
        return messages
