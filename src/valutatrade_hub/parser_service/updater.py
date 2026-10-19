"""Coordinate providers, resilient partial refreshes, and JSON persistence."""

import logging

from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.infra.database import utc_now_iso
from valutatrade_hub.parser_service.api_clients import (
    CoinGeckoClient,
    ExchangeRateApiClient,
)
from valutatrade_hub.parser_service.storage import RatesStorage

PARSER_LOGGER = logging.getLogger("valutatrade_hub.parser")


class RatesUpdater:
    """Fetch rates from providers and save a merged, normalised snapshot."""

    def __init__(self, clients=None, storage: RatesStorage | None = None):
        self.clients = clients or [
            CoinGeckoClient(),
            ExchangeRateApiClient(),
        ]
        self.storage = storage or RatesStorage()

    def run_update(self, source: str | None = None) -> dict:
        """Update chosen providers; a failed provider does not stop the others."""
        allowed_sources = {client.source for client in self.clients}
        if source is not None:
            source = source.lower()
            if source not in allowed_sources:
                raise ValueError("source должен быть coingecko или exchangerate")
            clients = [client for client in self.clients if client.source == source]
        else:
            clients = self.clients

        if not clients:
            raise ApiRequestError("не найден настроенный источник курсов")

        PARSER_LOGGER.info("Starting rates update...")
        updates = {}
        errors = []

        for client in clients:
            PARSER_LOGGER.info("Fetching from %s...", client.source)
            try:
                quotes = client.fetch_rates()
                for pair, rate in quotes.items():
                    if isinstance(rate, bool) or not isinstance(rate, (int, float)):
                        raise ApiRequestError(
                            f"{client.source}: некорректный тип курса для {pair}"
                        )
                    if float(rate) <= 0:
                        raise ApiRequestError(
                            f"{client.source}: неположительный курс для {pair}"
                        )
                    updates[pair] = {
                        "rate": float(rate),
                        "source": (
                            "CoinGecko"
                            if client.source == "coingecko"
                            else "ExchangeRate-API"
                        ),
                    }
                PARSER_LOGGER.info(
                    "Fetching from %s... OK (%d rates)",
                    client.source,
                    len(quotes),
                )
            except ApiRequestError as error:
                errors.append(f"{client.source}: {error}")
                PARSER_LOGGER.error("Failed to fetch from %s: %s", client.source, error)
            except Exception as error:
                errors.append(f"{client.source}: {error}")
                PARSER_LOGGER.exception(
                    "Unexpected provider error from %s", client.source
                )

        if not updates:
            details = "; ".join(errors) or "источники не вернули курсы"
            raise ApiRequestError(details)

        timestamp = utc_now_iso()
        PARSER_LOGGER.info("Writing %d rates to local cache...", len(updates))
        self.storage.save_updates(updates, timestamp)
        summary = {
            "updated_count": len(updates),
            "last_refresh": timestamp,
            "errors": errors,
        }
        if errors:
            PARSER_LOGGER.warning(
                "Update completed with errors. Check logs/parser.log for details."
            )
        else:
            PARSER_LOGGER.info(
                "Update successful. Total rates updated: %d. Last refresh: %s",
                len(updates),
                timestamp,
            )
        return summary
