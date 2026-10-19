"""Simple periodic parser-service scheduler."""

import logging
import time

from valutatrade_hub.infra.settings import SettingsLoader
from valutatrade_hub.logging_config import configure_logging
from valutatrade_hub.parser_service.updater import RatesUpdater

LOGGER = logging.getLogger("valutatrade_hub.parser")


def run_scheduler(interval_seconds: int | None = None):
    """Update rates repeatedly until interrupted."""
    settings = SettingsLoader()
    interval = int(interval_seconds or settings.get("parser_refresh_seconds", 300))
    updater = RatesUpdater()
    LOGGER.info("Parser scheduler started; interval=%s seconds", interval)
    try:
        while True:
            try:
                updater.run_update()
            except Exception as error:
                LOGGER.error("Scheduled update failed: %s", error)
            time.sleep(max(1, interval))
    except KeyboardInterrupt:
        LOGGER.info("Parser scheduler stopped by user")


def main():
    """Configure logs and start scheduler."""
    configure_logging()
    run_scheduler()


if __name__ == "__main__":
    main()
