"""Pairing phones: a 6-digit code shown on the laptop, then a token the phone sends with every
request. Tokens are stored hashed (devices.json, readable only by the user)."""

import hashlib
import json
import secrets
import time
import uuid
from pathlib import Path

from ...core import private_files
from ...core.settings import settings

CODE_SECONDS = 120
MAX_TRIES = 5


class Pairing:
    def __init__(self) -> None:
        self.code: str | None = None
        self.expires = 0.0
        self.tries = 0

    # ---------- codes ----------

    def start(self) -> str:
        self.code, self.expires, self.tries = f"{secrets.randbelow(10**6):06d}", time.time() + CODE_SECONDS, 0
        return self.code

    def pair(self, code: str, name: str) -> tuple[str, dict] | None:
        """The new device's token and entry, or None for a wrong, expired or used-up code.
        A code works once, and only within its first few tries."""
        ok = (
            self.code is not None
            and time.time() < self.expires
            and self.tries < MAX_TRIES
            and secrets.compare_digest(code.strip(), self.code)
        )
        self.tries += 1
        if not ok:
            return None
        self.code = None
        token = secrets.token_urlsafe(32)
        device = {
            "id": str(uuid.uuid4()),
            "name": name[:60],
            "paired": time.time(),
            "token_sha256": hashlib.sha256(token.encode()).hexdigest(),
        }
        self._save([*self.devices(), device])
        return token, device

    # ---------- paired devices ----------

    def device_for(self, token: str) -> str | None:
        """The id of the device this token belongs to."""
        if not token:
            return None
        digest = hashlib.sha256(token.encode()).hexdigest()
        return next((d["id"] for d in self.devices() if secrets.compare_digest(d["token_sha256"], digest)), None)

    def devices(self) -> list[dict]:
        try:
            return json.loads(self._file().read_text())
        except (OSError, ValueError):
            return []

    def unpair(self, device_id: str) -> None:
        self._save([d for d in self.devices() if d["id"] != device_id])

    def _file(self) -> Path:
        return settings.data_dir / "devices.json"

    def _save(self, devices: list[dict]) -> None:
        private_files.write_json(self._file(), devices)
