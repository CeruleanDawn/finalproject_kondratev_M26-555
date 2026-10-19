"""Singleton JSON database with atomic writes and guarded transactions."""

import json
import os
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from valutatrade_hub.infra.settings import SettingsLoader


def utc_now_iso() -> str:
    """Return a timezone-aware ISO-8601 timestamp in UTC."""
    return (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )


DEMO_USD_RATES = {
    "USD": 1.0,
    "EUR": 1.0786,
    "GBP": 1.25,
    "RUB": 0.01016,
    "JPY": 0.0067,
    "CAD": 0.74,
    "AUD": 0.66,
    "CHF": 1.1,
    "BTC": 59337.21,
    "ETH": 3720.0,
    "SOL": 145.12,
}


class DatabaseManager:
    """Central JSON repository; singleton avoids divergent storage managers."""

    # __new__ keeps the Singleton implementation small and readable.
    _instance = None
    _instance_lock = threading.Lock()

    def __new__(cls):
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return
        self.settings = SettingsLoader()
        self._lock = threading.RLock()
        self._initialized = True

    @contextmanager
    def transaction(self):
        """Serialize read-modify-write operations within this process."""
        with self._lock:
            yield self

    def _path(self, setting_key: str) -> Path:
        return self.settings.path(setting_key)

    def _read(self, setting_key: str, default):
        path = self._path(setting_key)
        with self._lock:
            if not path.exists():
                self._write_path(path, default)
            try:
                with path.open(encoding="utf-8") as file:
                    return json.load(file)
            except json.JSONDecodeError as error:
                raise ValueError(f"Повреждён JSON-файл {path}: {error}") from error

    def _write_path(self, path: Path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        with temporary.open("w", encoding="utf-8", newline="\n") as file:
            json.dump(data, file, ensure_ascii=False, indent=2, allow_nan=False)
            file.write("\n")
        os.replace(temporary, path)

    def _write(self, setting_key: str, data):
        path = self._path(setting_key)
        with self._lock:
            self._write_path(path, data)

    def load_users(self) -> list[dict]:
        """Read users.json."""
        return self._read("users_file", [])

    def save_users(self, data: list[dict]):
        """Write users.json."""
        self._write("users_file", data)

    def load_portfolios(self) -> list[dict]:
        """Read portfolios.json."""
        return self._read("portfolios_file", [])

    def save_portfolios(self, data: list[dict]):
        """Write portfolios.json."""
        self._write("portfolios_file", data)

    def load_rates(self) -> dict:
        """Read the rates snapshot."""
        return self._read("rates_file", {"pairs": {}, "last_refresh": None})

    def save_rates(self, data: dict):
        """Atomically save the rates snapshot."""
        self._write("rates_file", data)

    def load_history(self) -> list[dict]:
        """Read historical exchange-rate records."""
        return self._read("history_file", [])

    def save_history(self, data: list[dict]):
        """Atomically save historical records."""
        self._write("history_file", data)

    def ensure_initialized(self):
        """Create storage files and seed a small demo cache only if empty."""
        with self.transaction():
            for key, default in (
                ("users_file", []),
                ("portfolios_file", []),
                ("history_file", []),
            ):
                path = self._path(key)
                if not path.exists():
                    self._write_path(path, default)

            rates_path = self._path("rates_file")
            if not rates_path.exists():
                self._write_path(
                    rates_path,
                    {"pairs": {}, "last_refresh": None},
                )

            rates_data = self.load_rates()
            if not rates_data.get("pairs"):
                timestamp = utc_now_iso()
                pairs = {}
                for code, usd_price in DEMO_USD_RATES.items():
                    if code == "USD":
                        continue
                    pairs[f"{code}_USD"] = {
                        "rate": usd_price,
                        "updated_at": timestamp,
                        "source": "DemoStub",
                    }
                self.save_rates({"pairs": pairs, "last_refresh": timestamp})
