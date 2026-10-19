"""Validation and currency conversion helpers."""

import math
import re
from collections.abc import Callable

from valutatrade_hub.core.currencies import get_currency
from valutatrade_hub.core.exceptions import CurrencyNotFoundError

CODE_PATTERN = re.compile(r"^[A-Z0-9]{2,5}$")


def normalize_currency_code(code: str) -> str:
    """Normalize and validate a registered currency code."""
    if not isinstance(code, str):
        raise CurrencyNotFoundError(code)
    normalized = code.strip().upper()
    if not CODE_PATTERN.fullmatch(normalized):
        raise CurrencyNotFoundError(code)
    get_currency(normalized)
    return normalized


def validate_amount(amount: float) -> float:
    """Convert a positive finite numeric value to float."""
    if isinstance(amount, bool):
        raise ValueError("'amount' должен быть положительным числом")
    try:
        value = float(amount)
    except (TypeError, ValueError) as error:
        raise ValueError("'amount' должен быть положительным числом") from error
    if not math.isfinite(value) or value <= 0:
        raise ValueError("'amount' должен быть положительным числом")
    return value


def convert_amount(amount, from_code, to_code, rate_provider: Callable):
    """Convert an amount using a callable that returns a rate object or number."""
    value = validate_amount(amount)
    source = normalize_currency_code(from_code)
    target = normalize_currency_code(to_code)
    if source == target:
        return value
    quote = rate_provider(source, target)
    rate = quote["rate"] if isinstance(quote, dict) else float(quote)
    if not math.isfinite(rate) or rate <= 0:
        raise ValueError("Курс должен быть положительным числом")
    return value * rate
