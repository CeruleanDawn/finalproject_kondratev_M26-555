"""Configure action and parser logs with rotating files."""

import logging
from logging.handlers import RotatingFileHandler

from valutatrade_hub.infra.settings import SettingsLoader

LOG_FORMAT = "%(levelname)s %(asctime)s %(message)s"
DATE_FORMAT = "%Y-%m-%dT%H:%M:%S"


def _build_handler(path, max_bytes, backup_count):
    """Create a UTF-8 rotating file handler."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        path,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))
    return handler


def configure_logging():
    """Set up dedicated action and parser loggers."""
    settings = SettingsLoader()
    log_dir = settings.path("log_dir")
    max_bytes = int(settings.get("log_max_bytes", 1_048_576))
    backup_count = int(settings.get("log_backup_count", 3))
    configured_level = str(settings.get("log_level", "INFO")).upper()
    level = getattr(logging, configured_level, logging.INFO)

    definitions = {
        "valutatrade_hub.actions": log_dir / "actions.log",
        "valutatrade_hub.parser": log_dir / "parser.log",
    }

    for logger_name, path in definitions.items():
        logger = logging.getLogger(logger_name)
        logger.setLevel(level)
        logger.propagate = False
        for old_handler in logger.handlers[:]:
            logger.removeHandler(old_handler)
            old_handler.close()
        logger.addHandler(_build_handler(path, max_bytes, backup_count))

        console = logging.StreamHandler()
        console.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))
        console.setLevel(level)
        logger.addHandler(console)
