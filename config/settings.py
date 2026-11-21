"""Small QSettings wrapper with OBS passwords kept in the OS keyring."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QSettings

try:
    import keyring
except ImportError:  # pragma: no cover - shown as a UI warning at runtime
    keyring = None


@dataclass(frozen=True)
class AppSettings:
    obs_host: str
    obs_port: int
    obs_password: str
    game_executable: str
    monitoring_interval: float
    ignored_processes: tuple[str, ...]


class SettingsStore:
    """Persist non-secret preferences in QSettings and secrets in keyring."""

    KEYRING_SERVICE = "StreamLite OBS WebSocket"
    KEYRING_USER = "default"

    def __init__(self) -> None:
        self._settings = QSettings()

    def load(self) -> AppSettings:
        return AppSettings(
            obs_host=str(self._settings.value("obs/host", "127.0.0.1")),
            obs_port=self._as_int(self._settings.value("obs/port", 4455), 4455),
            obs_password=self.get_password(),
            game_executable=str(self._settings.value("game/executable", "")),
            monitoring_interval=1.0,
            ignored_processes=tuple(self._settings.value("process/ignored", [])),
        )

    def save(self, *, host: str, port: int, game_executable: str) -> None:
        self._settings.setValue("obs/host", host.strip() or "127.0.0.1")
        self._settings.setValue("obs/port", int(port))
        self._settings.setValue("game/executable", game_executable.strip())
        self._settings.sync()

    def set_password(self, password: str) -> bool:
        if not password:
            if keyring is None:
                return True
            try:
                keyring.delete_password(self.KEYRING_SERVICE, self.KEYRING_USER)
            except Exception:
                pass  # No stored password is already the desired state.
            return True
        if keyring is None:
            return False
        try:
            keyring.set_password(self.KEYRING_SERVICE, self.KEYRING_USER, password)
        except Exception:
            return False
        return True

    def get_password(self) -> str:
        if keyring is None:
            return ""
        try:
            return keyring.get_password(self.KEYRING_SERVICE, self.KEYRING_USER) or ""
        except Exception:
            return ""

    def ignored_processes(self) -> set[str]:
        return {str(name).casefold() for name in self._settings.value("process/ignored", [])}

    def add_ignored_process(self, name: str) -> None:
        names = self.ignored_processes()
        names.add(name.casefold())
        self._settings.setValue("process/ignored", sorted(names))
        self._settings.sync()

    @staticmethod
    def _as_int(value: object, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default
