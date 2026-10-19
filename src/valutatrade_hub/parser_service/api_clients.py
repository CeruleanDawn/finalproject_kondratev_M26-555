"""Unified API clients for crypto and fiat exchange rates."""

import time
from abc import ABC, abstractmethod

import requests

from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.parser_service.config import ParserConfig


class BaseApiClient(ABC):
    """Common contract for rates providers."""

    source = "base"

    @abstractmethod
    def fetch_rates(self) -> dict[str, float]:
        """Return rates normalised as pair -> units of TO per one FROM."""


class CoinGeckoClient(BaseApiClient):
    """Fetch BTC, ETH, and SOL prices in USD from CoinGecko."""

    source = "coingecko"

    def __init__(self, config: ParserConfig | None = None):
        self.config = config or ParserConfig.from_settings()

    def fetch_rates(self) -> dict[str, float]:
        ids = ",".join(self.config.crypto_id_map.values())
        start = time.monotonic()
        try:
            response = requests.get(
                self.config.coingecko_url,
                params={
                    "ids": ids,
                    "vs_currencies": self.config.base_fiat_currency.lower(),
                },
                timeout=self.config.request_timeout,
            )
            if response.status_code != 200:
                raise ApiRequestError(f"CoinGecko вернул HTTP {response.status_code}")
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as error:
            raise ApiRequestError(f"CoinGecko: {error}") from error
        except ValueError as error:
            raise ApiRequestError(
                f"CoinGecko вернул некорректный JSON: {error}"
            ) from error

        rates = {}
        base = self.config.base_fiat_currency
        for code, raw_id in self.config.crypto_id_map.items():
            quote = payload.get(raw_id, {}).get(base.lower())
            if isinstance(quote, bool) or not isinstance(quote, (int, float)):
                continue
            if quote > 0:
                rates[f"{code}_{base}"] = float(quote)

        if not rates:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            raise ApiRequestError(
                f"CoinGecko не вернул поддерживаемые курсы (request_ms={elapsed_ms})"
            )
        return rates


class ExchangeRateApiClient(BaseApiClient):
    """Fetch fiat prices from ExchangeRate-API and normalise them to USD pairs."""

    source = "exchangerate"

    def __init__(self, config: ParserConfig | None = None):
        self.config = config or ParserConfig.from_settings()

    def fetch_rates(self) -> dict[str, float]:
        api_key = self.config.exchange_rate_api_key
        if not api_key:
            raise ApiRequestError(
                "не задан EXCHANGERATE_API_KEY; установите ключ в переменную окружения"
            )

        url = (
            f"{self.config.exchange_rate_api_url.rstrip('/')}/"
            f"{api_key}/latest/{self.config.base_fiat_currency}"
        )
        try:
            response = requests.get(url, timeout=self.config.request_timeout)
            if response.status_code != 200:
                raise ApiRequestError(
                    f"ExchangeRate-API вернул HTTP {response.status_code}"
                )
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as error:
            raise ApiRequestError(f"ExchangeRate-API: {error}") from error
        except ValueError as error:
            raise ApiRequestError(
                f"ExchangeRate-API вернул некорректный JSON: {error}"
            ) from error

        if payload.get("result") != "success":
            reason = payload.get("error-type", "неизвестная ошибка API")
            raise ApiRequestError(f"ExchangeRate-API: {reason}")

        rates = payload.get("conversion_rates", payload.get("rates", {}))
        base = self.config.base_fiat_currency
        result = {}
        for code in self.config.fiat_currencies:
            units_per_base = rates.get(code)
            if (
                isinstance(units_per_base, bool)
                or not isinstance(units_per_base, (int, float))
                or units_per_base <= 0
            ):
                continue
            # Invert foreign units per USD to get USD per one foreign unit.
            result[f"{code}_{base}"] = 1.0 / float(units_per_base)

        if not result:
            raise ApiRequestError(
                "ExchangeRate-API не вернул поддерживаемые фиатные курсы"
            )
        return result
