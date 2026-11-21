"""OBS and game settings page."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

from config.settings import SettingsStore


class SettingsPage(QWidget):
    def __init__(self, settings: SettingsStore) -> None:
        super().__init__()
        self.settings = settings
        values = settings.load()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(36, 32, 36, 32)
        outer.setSpacing(18)
        title = QLabel("Settings")
        title.setObjectName("pageTitle")
        outer.addWidget(title)

        form = QFormLayout()
        self.host = QLineEdit(values.obs_host)
        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        self.port.setValue(values.obs_port)
        self.password = QLineEdit(values.obs_password)
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.game = QLineEdit(values.game_executable)
        game_row = QHBoxLayout()
        game_row.addWidget(self.game)
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse_game)
        game_row.addWidget(browse)
        form.addRow("OBS host", self.host)
        form.addRow("OBS WebSocket port", self.port)
        form.addRow("OBS password", self.password)
        form.addRow("Game executable (optional)", game_row)
        outer.addLayout(form)

        note = QLabel("The OBS password is stored in the Windows credential store when available. StreamLite defaults to 127.0.0.1:4455.")
        note.setObjectName("muted")
        note.setWordWrap(True)
        outer.addWidget(note)
        save = QPushButton("Save settings")
        save.setObjectName("primaryButton")
        save.clicked.connect(self._save)
        outer.addWidget(save, 0)
        outer.addStretch(1)

    def _browse_game(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select game executable", "", "Applications (*.exe)")
        if path:
            self.game.setText(path)

    def _save(self) -> None:
        self.settings.save(host=self.host.text(), port=self.port.value(), game_executable=self.game.text())
        stored = self.settings.set_password(self.password.text())
        if stored or not self.password.text():
            QMessageBox.information(self, "Settings saved", "Settings saved. The OBS password is stored in the Windows credential store.")
        else:
            QMessageBox.warning(self, "Settings saved", "Other settings were saved, but the password could not be stored securely. Configure OBS without a password or check Windows credential-store access.")
