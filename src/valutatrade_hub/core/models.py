"""Domain models: User, Wallet, and Portfolio."""

import hashlib
import hmac
import math
import secrets
from datetime import datetime, timezone

from valutatrade_hub.core.currencies import get_currency
from valutatrade_hub.core.exceptions import InsufficientFundsError
from valutatrade_hub.core.utils import normalize_currency_code, validate_amount

MIN_PASSWORD_LENGTH = 4


def _parse_datetime(value):
    """Parse ISO datetime stored in JSON."""
    if isinstance(value, datetime):
        return value
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


class User:
    """Registered user with salted SHA-256 password hash."""

    def __init__(
        self,
        user_id: int,
        username: str,
        password: str | None = None,
        hashed_password: str | None = None,
        salt: str | None = None,
        registration_date: str | datetime | None = None,
    ):
        if isinstance(user_id, bool) or not isinstance(user_id, int) or user_id < 1:
            raise ValueError("user_id должен быть положительным целым числом")
        self._user_id = user_id
        self.username = username
        if password is not None:
            self.change_password(password)
        else:
            if not hashed_password or not salt:
                raise ValueError("Не задан хеш пароля или соль")
            self._salt = salt
            self._hashed_password = hashed_password
        self._registration_date = _parse_datetime(
            registration_date or datetime.now(timezone.utc)
        )

    @property
    def user_id(self):
        """Read-only numeric user ID."""
        return self._user_id

    @property
    def username(self):
        """Username."""
        return self._username

    @username.setter
    def username(self, value):
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Имя пользователя не должно быть пустым")
        self._username = value.strip()

    @property
    def hashed_password(self):
        """Stored password hash (not included in public user info)."""
        return self._hashed_password

    @property
    def salt(self):
        """Salt used for the password hash."""
        return self._salt

    @property
    def registration_date(self):
        """Registration date as a datetime."""
        return self._registration_date

    def change_password(self, new_password: str):
        """Generate a fresh per-user salt and hash a new password."""
        if not isinstance(new_password, str) or len(new_password) < MIN_PASSWORD_LENGTH:
            raise ValueError("Пароль должен быть не короче 4 символов")
        self._salt = secrets.token_hex(16)
        self._hashed_password = hashlib.sha256(
            f"{new_password}{self._salt}".encode("utf-8")
        ).hexdigest()

    def verify_password(self, password: str) -> bool:
        """Check a password without exposing the original secret."""
        if not isinstance(password, str):
            return False
        actual = hashlib.sha256(f"{password}{self._salt}".encode("utf-8")).hexdigest()
        return hmac.compare_digest(actual, self._hashed_password)

    def get_user_info(self) -> dict:
        """Return safe user details without password or salt."""
        return {
            "user_id": self._user_id,
            "username": self._username,
            "registration_date": self._registration_date.isoformat(),
        }

    def to_dict(self) -> dict:
        """Serialize user for users.json."""
        return {
            "user_id": self._user_id,
            "username": self._username,
            "hashed_password": self._hashed_password,
            "salt": self._salt,
            "registration_date": self._registration_date.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict):
        """Restore a User from the JSON representation."""
        return cls(
            user_id=int(data["user_id"]),
            username=data["username"],
            hashed_password=data["hashed_password"],
            salt=data["salt"],
            registration_date=data["registration_date"],
        )


class Wallet:
    """Wallet for one currency."""

    def __init__(self, currency_code: str, balance: float = 0.0):
        self.currency_code = normalize_currency_code(currency_code)
        self._balance = 0.0
        self.balance = balance

    @property
    def balance(self) -> float:
        """Current nonnegative wallet balance."""
        return self._balance

    @balance.setter
    def balance(self, value):
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or value < 0
        ):
            raise ValueError("Баланс должен быть неотрицательным числом")
        self._balance = round(float(value), 10)

    def deposit(self, amount: float):
        """Deposit a positive amount."""
        value = validate_amount(amount)
        self.balance = self._balance + value

    def withdraw(self, amount: float):
        """Withdraw only if the current balance covers the amount."""
        value = validate_amount(amount)
        if value > self._balance + 1e-9:
            raise InsufficientFundsError(self._balance, value, self.currency_code)
        self.balance = max(0.0, self._balance - value)

    def get_balance_info(self) -> str:
        """Return human-readable wallet balance."""
        return f"{self.currency_code}: {self._balance:.4f}"

    def to_dict(self) -> dict:
        """Serialize wallet."""
        return {"currency_code": self.currency_code, "balance": self._balance}


class Portfolio:
    """Wallet collection associated with one registered user."""

    def __init__(self, user: User, wallets: dict[str, Wallet] | None = None):
        if not isinstance(user, User):
            raise TypeError("Portfolio ожидает объект User")
        self._user = user
        self._user_id = user.user_id
        self._wallets = {}
        for code, wallet in (wallets or {}).items():
            normalized = normalize_currency_code(code)
            if not isinstance(wallet, Wallet):
                wallet = Wallet(normalized, wallet.get("balance", 0.0))
            if normalized in self._wallets:
                raise ValueError(f"Кошелёк '{normalized}' уже существует")
            self._wallets[normalized] = wallet

    @property
    def user(self) -> User:
        """Read-only associated User."""
        return self._user

    @property
    def wallets(self) -> dict[str, Wallet]:
        """Return a shallow copy of the wallet mapping."""
        return dict(self._wallets)

    @property
    def user_id(self) -> int:
        """User ID associated with the portfolio."""
        return self._user_id

    def add_currency(self, currency_code: str) -> Wallet:
        """Create a wallet for a currency not already in the portfolio."""
        code = normalize_currency_code(currency_code)
        if code in self._wallets:
            raise ValueError(f"Кошелёк '{code}' уже существует")
        self._wallets[code] = Wallet(code)
        return self._wallets[code]

    def get_wallet(self, currency_code: str) -> Wallet:
        """Return an existing wallet or raise a user-friendly KeyError."""
        code = normalize_currency_code(currency_code)
        try:
            return self._wallets[code]
        except KeyError as error:
            raise KeyError(
                f"У вас нет кошелька '{code}'. Добавьте его первой покупкой "
                "или командой deposit."
            ) from error

    def get_total_value(self, base_currency="USD", rate_lookup=None) -> float:
        """Convert and add wallet balances in the specified base currency."""
        base = normalize_currency_code(base_currency)
        if not self._wallets:
            return 0.0

        total = 0.0
        for code, wallet in self._wallets.items():
            if code == base:
                total += wallet.balance
                continue
            if rate_lookup is not None:
                quote = rate_lookup(code, base)
                rate = quote["rate"] if isinstance(quote, dict) else float(quote)
            else:
                rate = _offline_rate(code, base)
            total += wallet.balance * rate
        return round(total, 2)

    def to_dict(self) -> dict:
        """Serialize portfolio and all wallets."""
        return {
            "user_id": self._user_id,
            "wallets": {
                code: wallet.to_dict() for code, wallet in self._wallets.items()
            },
        }

    @classmethod
    def from_dict(cls, user: User, data: dict):
        """Restore a Portfolio and its wallets."""
        wallets = {
            code: Wallet(code, wallet_data.get("balance", 0.0))
            for code, wallet_data in data.get("wallets", {}).items()
        }
        return cls(user, wallets)


def _offline_rate(from_code, to_code):
    """Convert using demo USD prices when no callback is provided."""
    get_currency(from_code)
    get_currency(to_code)
    usd_prices = {
        "USD": 1.0,
        "EUR": 1.0786,
        "GBP": 1.25,
        "RUB": 0.01016,
        "JPY": 0.0067,
        "CAD": 0.74,
        "AUD": 0.66,
        "CHF": 1.1,
        "BTC": 59337.21,
        "ETH": 3720.0,
        "SOL": 145.12,
    }
    return usd_prices[from_code] / usd_prices[to_code]
