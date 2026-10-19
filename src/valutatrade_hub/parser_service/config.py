"""Configuration for external exchange-rate clients."""

import os
from dataclasses import dataclass, field

from valutatrade_hub.infra.settings import SettingsLoader


@dataclass(frozen=True)
class ParserConfig:
    """Typed parser settings; secrets are read only from environment variables."""

    exchange_rate_api_key: str | None = field(
        default_factory=lambda: os.getenv("EXCHANGERATE_API_KEY") or None
    )
    coingecko_url: str = "https://api.coingecko.com/api/v3/simple/price"
    exchange_rate_api_url: str = "https://v6.exchangerate-api.com/v6"
    base_fiat_currency: str = "USD"
    fiat_currencies: tuple[str, ...] = ("EUR", "GBP", "RUB", "JPY", "CAD", "AUD", "CHF")
    crypto_currencies: tuple[str, ...] = ("BTC", "ETH", "SOL")
    crypto_id_map: dict[str, str] = field(
        default_factory=lambda: {
            "BTC": "bitcoin",
            "ETH": "ethereum",
            "SOL": "solana",
        }
    )
    rates_file_path: str = "data/rates.json"
    history_file_path: str = "data/exchange_rates.json"
    request_timeout: int = 10

    @classmethod
    def from_settings(cls):
        """Build parser configuration using project settings and environment."""
        settings = SettingsLoader()
        return cls(
            base_fiat_currency=str(settings.get("base_currency", "USD")).upper(),
            rates_file_path=str(settings.get("rates_file", "data/rates.json")),
            history_file_path=str(
                settings.get("history_file", "data/exchange_rates.json")
            ),
            request_timeout=int(settings.get("request_timeout", 10)),
        )
