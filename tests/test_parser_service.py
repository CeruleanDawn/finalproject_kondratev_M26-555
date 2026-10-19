"""Offline tests for API clients and resilient parser-service updates."""

import unittest
from unittest.mock import Mock, patch

from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.parser_service.api_clients import (
    CoinGeckoClient,
    ExchangeRateApiClient,
)
from valutatrade_hub.parser_service.config import ParserConfig
from valutatrade_hub.parser_service.updater import RatesUpdater


class FakeClient:
    """Small provider fake used to avoid real HTTP requests in tests."""

    def __init__(self, source, rates=None, error=None):
        self.source = source
        self.rates = rates or {}
        self.error = error

    def fetch_rates(self):
        if self.error:
            raise ApiRequestError(self.error)
        return self.rates


class FakeStorage:
    """Capture updates instead of writing project JSON files."""

    def __init__(self):
        self.rates = None
        self.timestamp = None

    def save_updates(self, rates, timestamp=None):
        self.rates = rates
        self.timestamp = timestamp


class ApiClientTests(unittest.TestCase):
    @patch("valutatrade_hub.parser_service.api_clients.requests.get")
    def test_coingecko_response_is_normalized(self, mocked_get):
        response = Mock()
        response.status_code = 200
        response.json.return_value = {
            "bitcoin": {"usd": 60000.0},
            "ethereum": {"usd": 3000.0},
            "solana": {"usd": 150.0},
        }
        response.raise_for_status.return_value = None
        mocked_get.return_value = response

        result = CoinGeckoClient(ParserConfig()).fetch_rates()

        self.assertEqual(result["BTC_USD"], 60000.0)
        self.assertEqual(result["ETH_USD"], 3000.0)
        self.assertEqual(result["SOL_USD"], 150.0)
        mocked_get.assert_called_once()

    @patch("valutatrade_hub.parser_service.api_clients.requests.get")
    def test_exchange_rate_response_is_normalized(self, mocked_get):
        response = Mock()
        response.status_code = 200
        response.json.return_value = {
            "result": "success",
            "base_code": "USD",
            "conversion_rates": {"EUR": 0.5, "GBP": 0.8, "RUB": 100.0},
        }
        response.raise_for_status.return_value = None
        mocked_get.return_value = response

        config = ParserConfig(exchange_rate_api_key="test-key")
        result = ExchangeRateApiClient(config).fetch_rates()

        self.assertEqual(result["EUR_USD"], 2.0)
        self.assertEqual(result["GBP_USD"], 1.25)
        self.assertEqual(result["RUB_USD"], 0.01)

    def test_exchange_rate_api_key_is_required(self):
        config = ParserConfig(exchange_rate_api_key=None)
        with self.assertRaisesRegex(ApiRequestError, "EXCHANGERATE_API_KEY"):
            ExchangeRateApiClient(config).fetch_rates()


class RatesUpdaterTests(unittest.TestCase):
    def test_one_failed_provider_does_not_stop_another(self):
        storage = FakeStorage()
        updater = RatesUpdater(
            clients=[
                FakeClient("coingecko", {"BTC_USD": 60000.0}),
                FakeClient("exchangerate", error="missing key"),
            ],
            storage=storage,
        )
        result = updater.run_update()
        self.assertEqual(result["updated_count"], 1)
        self.assertEqual(len(result["errors"]), 1)
        self.assertEqual(storage.rates["BTC_USD"]["rate"], 60000.0)
        self.assertEqual(storage.rates["BTC_USD"]["source"], "CoinGecko")

    def test_all_failed_providers_raise_api_error(self):
        updater = RatesUpdater(
            clients=[
                FakeClient("coingecko", error="offline"),
                FakeClient("exchangerate", error="missing key"),
            ],
            storage=FakeStorage(),
        )
        with self.assertRaises(ApiRequestError):
            updater.run_update()


if __name__ == "__main__":
    unittest.main()
