"""Domain exceptions with user-facing messages."""


class InsufficientFundsError(Exception):
    """Raised when a wallet does not have enough funds."""

    def __init__(self, available, required, code):
        self.available = float(available)
        self.required = float(required)
        self.code = code
        super().__init__(
            f"Недостаточно средств: доступно {self.available:.4f} {code}, "
            f"требуется {self.required:.4f} {code}"
        )


class CurrencyNotFoundError(Exception):
    """Raised when a currency code is not in the supported registry."""

    def __init__(self, code):
        self.code = str(code)
        super().__init__(f"Неизвестная валюта '{self.code}'")


class ApiRequestError(Exception):
    """Raised when a rates API request or refresh fails."""

    def __init__(self, reason):
        self.reason = str(reason)
        super().__init__(f"Ошибка при обращении к внешнему API: {self.reason}")
