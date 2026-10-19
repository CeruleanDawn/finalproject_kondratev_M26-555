"""Currency hierarchy and registry."""

import math
import re
from abc import ABC, abstractmethod

from valutatrade_hub.core.exceptions import CurrencyNotFoundError

CURRENCY_CODE_PATTERN = re.compile(r"^[A-Z0-9]{2,5}$")


class Currency(ABC):
    """Abstract currency with validated name and public code/name properties."""

    def __init__(self, name: str, code: str):
        self.name = name
        self.code = code

    @property
    def name(self):
        """Human-readable currency name."""
        return self._name

    @name.setter
    def name(self, value):
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Название валюты не должно быть пустым")
        self._name = value.strip()

    @property
    def code(self):
        """Uppercase ISO currency code or accepted crypto ticker."""
        return self._code

    @code.setter
    def code(self, value):
        if not isinstance(value, str) or value != value.upper():
            raise ValueError("Код валюты должен быть в верхнем регистре")
        if not CURRENCY_CODE_PATTERN.fullmatch(value):
            raise ValueError("Код валюты должен содержать 2–5 символов без пробелов")
        self._code = value

    @abstractmethod
    def get_display_info(self) -> str:
        """Return a human-readable currency description."""


class FiatCurrency(Currency):
    """Fiat currency issued by a country or currency zone."""

    def __init__(self, name: str, code: str, issuing_country: str):
        super().__init__(name, code)
        self.issuing_country = issuing_country

    @property
    def issuing_country(self):
        """Country or monetary zone issuing the currency."""
        return self._issuing_country

    @issuing_country.setter
    def issuing_country(self, value):
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Страна/зона эмиссии не должна быть пустой")
        self._issuing_country = value.strip()

    def get_display_info(self) -> str:
        """Return fiat currency details."""
        return f"[FIAT] {self.code} — {self.name} (Issuing: {self.issuing_country})"


class CryptoCurrency(Currency):
    """Cryptocurrency with algorithm and market capitalisation."""

    def __init__(
        self,
        name: str,
        code: str,
        algorithm: str,
        market_cap: float,
    ):
        super().__init__(name, code)
        self.algorithm = algorithm
        self.market_cap = market_cap

    @property
    def algorithm(self):
        """Consensus/mining algorithm label."""
        return self._algorithm

    @algorithm.setter
    def algorithm(self, value):
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Алгоритм не должен быть пустым")
        self._algorithm = value.strip()

    @property
    def market_cap(self):
        """Latest known market capitalization."""
        return self._market_cap

    @market_cap.setter
    def market_cap(self, value):
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or value < 0
        ):
            raise ValueError("Капитализация должна быть неотрицательным числом")
        self._market_cap = float(value)

    def get_display_info(self) -> str:
        """Return crypto details with compact market capitalization."""
        market_cap = f"{self.market_cap:.2e}".replace("e+", "e")
        return (
            f"[CRYPTO] {self.code} — {self.name} "
            f"(Algo: {self.algorithm}, MCAP: {market_cap})"
        )


_CURRENCY_LIST = (
    FiatCurrency("US Dollar", "USD", "United States"),
    FiatCurrency("Euro", "EUR", "Eurozone"),
    FiatCurrency("British Pound", "GBP", "United Kingdom"),
    FiatCurrency("Russian Ruble", "RUB", "Russia"),
    FiatCurrency("Japanese Yen", "JPY", "Japan"),
    FiatCurrency("Canadian Dollar", "CAD", "Canada"),
    FiatCurrency("Australian Dollar", "AUD", "Australia"),
    FiatCurrency("Swiss Franc", "CHF", "Switzerland"),
    CryptoCurrency("Bitcoin", "BTC", "SHA-256", 1.12e12),
    CryptoCurrency("Ethereum", "ETH", "Ethash", 4.45e11),
    CryptoCurrency("Solana", "SOL", "Proof of History", 7.0e10),
)
CURRENCY_REGISTRY = {currency.code: currency for currency in _CURRENCY_LIST}


def get_currency(code: str) -> Currency:
    """Get a registered currency by code or raise CurrencyNotFoundError."""
    if not isinstance(code, str):
        raise CurrencyNotFoundError(code)
    normalized = code.strip().upper()
    if not CURRENCY_CODE_PATTERN.fullmatch(normalized):
        raise CurrencyNotFoundError(code)
    try:
        return CURRENCY_REGISTRY[normalized]
    except KeyError as error:
        raise CurrencyNotFoundError(normalized) from error


def list_supported_codes() -> list[str]:
    """Return sorted supported currency codes."""
    return sorted(CURRENCY_REGISTRY)
