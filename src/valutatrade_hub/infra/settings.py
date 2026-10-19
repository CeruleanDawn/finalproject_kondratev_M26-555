"""Singleton configuration loader backed by pyproject.toml."""

import threading
import tomllib
from pathlib import Path

DEFAULTS = {
    "data_dir": "data",
    "users_file": "data/users.json",
    "portfolios_file": "data/portfolios.json",
    "rates_file": "data/rates.json",
    "history_file": "data/exchange_rates.json",
    "rates_ttl_seconds": 300,
    "base_currency": "USD",
    "request_timeout": 10,
    "log_dir": "logs",
    "log_level": "INFO",
    "log_max_bytes": 1_048_576,
    "log_backup_count": 3,
    "parser_refresh_seconds": 300,
}


class SettingsLoader:
    """Load settings once; __new__ ensures one instance per process."""

    # __new__ is sufficient here and easier to follow than a custom metaclass.
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
        cwd = Path.cwd()
        # CLI commands are normally started from the project directory. When
        # installed as a standalone tool, keep runtime data relative to cwd.
        self._root = cwd.resolve()
        self._config = {}
        self.reload()
        self._initialized = True

    @property
    def root(self) -> Path:
        """Project root used to resolve relative data and log paths."""
        return self._root

    def reload(self):
        """Reload [tool.valutatrade] configuration from pyproject.toml."""
        config = dict(DEFAULTS)
        pyproject = self._root / "pyproject.toml"
        if pyproject.is_file():
            try:
                with pyproject.open("rb") as file:
                    document = tomllib.load(file)
                custom = document.get("tool", {}).get("valutatrade", {})
                config.update(custom)
            except (OSError, tomllib.TOMLDecodeError) as error:
                raise ValueError(
                    f"Не удалось прочитать pyproject.toml: {error}"
                ) from error
        self._config = config

    def get(self, key: str, default=None):
        """Get a setting with optional fallback."""
        return self._config.get(key, default)

    def path(self, key: str) -> Path:
        """Resolve a path setting against the project root."""
        value = Path(str(self.get(key)))
        return value if value.is_absolute() else self._root / value
