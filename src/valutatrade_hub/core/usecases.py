"""Application use cases: registration, login, wallets, and rate queries."""

import logging
from datetime import datetime, timezone

from valutatrade_hub.core.exceptions import (
    ApiRequestError,
    CurrencyNotFoundError,
    InsufficientFundsError,
)
from valutatrade_hub.core.models import Portfolio, User
from valutatrade_hub.core.utils import normalize_currency_code, validate_amount
from valutatrade_hub.decorators import log_action
from valutatrade_hub.infra.database import DatabaseManager
from valutatrade_hub.infra.settings import SettingsLoader

LOGGER = logging.getLogger("valutatrade_hub.actions")


def _database():
    """Get and initialise the singleton JSON database."""
    database = DatabaseManager()
    database.ensure_initialized()
    return database


def _find_user_record(username: str, users: list[dict]) -> dict | None:
    """Find a username case-insensitively."""
    target = username.casefold()
    return next(
        (
            record
            for record in users
            if str(record.get("username", "")).casefold() == target
        ),
        None,
    )


def _user_by_id(user_id: int) -> User:
    """Load a persisted user or fail with a domain-level message."""
    database = _database()
    for record in database.load_users():
        if record.get("user_id") == user_id:
            return User.from_dict(record)
    raise ValueError(f"Пользователь с id={user_id} не найден")


def _portfolio_for_user(user_id: int) -> Portfolio:
    """Load a user's portfolio from the JSON repository."""
    database = _database()
    user = _user_by_id(user_id)
    for record in database.load_portfolios():
        if record.get("user_id") == user_id:
            return Portfolio.from_dict(user, record)
    raise ValueError(f"Портфель пользователя '{user.username}' не найден")


def _save_portfolio(portfolio: Portfolio):
    """Persist one portfolio without replacing other users' data."""
    database = _database()
    with database.transaction():
        portfolios = database.load_portfolios()
        replacement = portfolio.to_dict()
        for index, record in enumerate(portfolios):
            if record.get("user_id") == portfolio.user_id:
                portfolios[index] = replacement
                break
        else:
            portfolios.append(replacement)
        database.save_portfolios(portfolios)


def register(username: str, password: str) -> User:
    """Register a unique user and create an empty portfolio."""
    database = _database()
    with database.transaction():
        users = database.load_users()
        if _find_user_record(username.strip(), users):
            raise ValueError(f"Имя пользователя '{username}' уже занято")
        user_id = (
            max(
                (int(record.get("user_id", 0)) for record in users),
                default=0,
            )
            + 1
        )
        user = User(user_id=user_id, username=username, password=password)
        users.append(user.to_dict())
        portfolios = database.load_portfolios()
        portfolios.append(Portfolio(user).to_dict())
        database.save_users(users)
        database.save_portfolios(portfolios)
    return user


def login(username: str, password: str) -> User:
    """Authenticate a user and return its domain model."""
    database = _database()
    record = _find_user_record(username.strip(), database.load_users())
    if record is None:
        raise ValueError(f"Пользователь '{username}' не найден")
    user = User.from_dict(record)
    if not user.verify_password(password):
        raise ValueError("Неверный пароль")
    return user


def get_user(user_id: int) -> User:
    """Return a registered user by ID."""
    return _user_by_id(user_id)


def deposit(user_id: int, currency_code: str, amount: float) -> dict:
    """Add virtual funds to a wallet (helper for initializing demo capital)."""
    code = normalize_currency_code(currency_code)
    value = validate_amount(amount)
    database = _database()
    with database.transaction():
        portfolio = _portfolio_for_user(user_id)
        wallet = portfolio.wallets.get(code)
        if wallet is None:
            wallet = portfolio.add_currency(code)
        before = wallet.balance
        wallet.deposit(value)
        _save_portfolio(portfolio)
        result = {
            "user_id": user_id,
            "username": portfolio.user.username,
            "currency_code": code,
            "amount": value,
            "previous_balance": before,
            "new_balance": wallet.balance,
        }
    return result


@log_action(action="BUY", verbose=True)
def buy(user_id: int, currency_code: str, amount: float) -> dict:
    """Buy an amount of currency, debiting its USD equivalent."""
    code = normalize_currency_code(currency_code)
    value = validate_amount(amount)
    if code == "USD":
        raise ValueError("USD уже является базовой валютой; используйте deposit")

    quote = get_rate(code, "USD")
    rate = float(quote["rate"])
    cost = round(value * rate, 8)
    database = _database()

    with database.transaction():
        portfolio = _portfolio_for_user(user_id)
        usd_wallet = portfolio.wallets.get("USD")
        available = usd_wallet.balance if usd_wallet else 0.0
        if available + 1e-9 < cost:
            raise InsufficientFundsError(available, cost, "USD")

        target_wallet = portfolio.wallets.get(code)
        if target_wallet is None:
            target_wallet = portfolio.add_currency(code)
        usd_wallet = portfolio.get_wallet("USD")
        before_target = target_wallet.balance
        before_usd = usd_wallet.balance

        usd_wallet.withdraw(cost)
        target_wallet.deposit(value)
        _save_portfolio(portfolio)

        result = {
            "user_id": user_id,
            "username": portfolio.user.username,
            "currency_code": code,
            "amount": value,
            "rate": rate,
            "base": "USD",
            "cost_usd": cost,
            "previous_balance": before_target,
            "new_balance": target_wallet.balance,
            "usd_before": before_usd,
            "usd_after": usd_wallet.balance,
            "context": (
                f"USD: {before_usd:.4f}->{usd_wallet.balance:.4f}; "
                f"{code}: {before_target:.4f}->{target_wallet.balance:.4f}"
            ),
        }
    return result


@log_action(action="SELL", verbose=True)
def sell(user_id: int, currency_code: str, amount: float) -> dict:
    """Sell currency, withdrawing it and crediting the USD equivalent."""
    code = normalize_currency_code(currency_code)
    value = validate_amount(amount)
    if code == "USD":
        raise ValueError("Нельзя продать USD за USD; выберите другую валюту")

    # Check the wallet before a network-backed rate lookup.
    portfolio = _portfolio_for_user(user_id)
    wallet = portfolio.wallets.get(code)
    if wallet is None:
        raise ValueError(
            f"У вас нет кошелька '{code}'. Добавьте валюту первой покупкой."
        )
    if wallet.balance + 1e-9 < value:
        raise InsufficientFundsError(wallet.balance, value, code)

    quote = get_rate(code, "USD")
    rate = float(quote["rate"])
    proceeds = round(value * rate, 8)
    database = _database()

    # Re-read under the same lock as the balance mutation and JSON write.
    with database.transaction():
        portfolio = _portfolio_for_user(user_id)
        wallet = portfolio.wallets.get(code)
        if wallet is None:
            raise ValueError(
                f"У вас нет кошелька '{code}'. Добавьте валюту первой покупкой."
            )
        if wallet.balance + 1e-9 < value:
            raise InsufficientFundsError(wallet.balance, value, code)

        usd_wallet = portfolio.wallets.get("USD")
        if usd_wallet is None:
            usd_wallet = portfolio.add_currency("USD")

        before_currency = wallet.balance
        before_usd = usd_wallet.balance
        wallet.withdraw(value)
        usd_wallet.deposit(proceeds)
        _save_portfolio(portfolio)

        result = {
            "user_id": user_id,
            "username": portfolio.user.username,
            "currency_code": code,
            "amount": value,
            "rate": rate,
            "base": "USD",
            "proceeds_usd": proceeds,
            "previous_balance": before_currency,
            "new_balance": wallet.balance,
            "usd_before": before_usd,
            "usd_after": usd_wallet.balance,
            "context": (
                f"{code}: {before_currency:.4f}->{wallet.balance:.4f}; "
                f"USD: {before_usd:.4f}->{usd_wallet.balance:.4f}"
            ),
        }
    return result


def _parse_timestamp(value: str) -> datetime:
    """Parse an ISO timestamp and normalise it to UTC."""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _is_fresh(record: dict, ttl_seconds: int) -> bool:
    """Return whether a quote fits the configured TTL."""
    value = record.get("updated_at")
    if not value:
        return False
    try:
        age = (datetime.now(timezone.utc) - _parse_timestamp(value)).total_seconds()
    except (ValueError, TypeError):
        return False
    return -60 <= age <= ttl_seconds


def _single_pair_rate(snapshot: dict, source: str, target: str, ttl: int):
    """Find a fresh direct or reverse pair in the snapshot."""
    if source == target:
        return {
            "rate": 1.0,
            "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "source": "identity",
        }
    pairs = snapshot.get("pairs", {})
    direct = pairs.get(f"{source}_{target}")
    if direct and _is_fresh(direct, ttl):
        return {
            "rate": float(direct["rate"]),
            "updated_at": direct["updated_at"],
            "source": direct.get("source", "cache"),
        }
    reverse = pairs.get(f"{target}_{source}")
    if reverse and _is_fresh(reverse, ttl) and float(reverse.get("rate", 0)) > 0:
        return {
            "rate": 1.0 / float(reverse["rate"]),
            "updated_at": reverse["updated_at"],
            "source": reverse.get("source", "cache"),
        }
    return None


def _lookup_rate(snapshot: dict, source: str, target: str, ttl: int):
    """Resolve direct, reverse, or USD-cross rates from fresh cache entries."""
    direct = _single_pair_rate(snapshot, source, target, ttl)
    if direct:
        return direct

    left = _single_pair_rate(snapshot, source, "USD", ttl)
    right = _single_pair_rate(snapshot, "USD", target, ttl)
    if left and right:
        timestamps = [left["updated_at"], right["updated_at"]]
        oldest = min(timestamps)
        sources = sorted({left["source"], right["source"]})
        return {
            "rate": float(left["rate"]) * float(right["rate"]),
            "updated_at": oldest,
            "source": "+".join(sources),
        }
    return None


@log_action(action="GET_RATE")
def get_rate(from_code: str, to_code: str) -> dict:
    """Return a fresh quote with its update timestamp and source."""
    source = normalize_currency_code(from_code)
    target = normalize_currency_code(to_code)
    database = _database()
    if source == target:
        return {
            "from_currency": source,
            "to_currency": target,
            "rate": 1.0,
            "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "source": "identity",
        }

    ttl = int(SettingsLoader().get("rates_ttl_seconds", 300))
    snapshot = database.load_rates()
    quote = _lookup_rate(snapshot, source, target, ttl)
    if quote is None:
        LOGGER.info(
            "Cached rate %s_%s is missing or stale; updating rates",
            source,
            target,
        )
        from valutatrade_hub.parser_service.updater import RatesUpdater

        try:
            RatesUpdater().run_update()
        except ApiRequestError as error:
            LOGGER.error("Rate refresh failed: %s", error)
        snapshot = database.load_rates()
        quote = _lookup_rate(snapshot, source, target, ttl)

    if quote is None:
        raise ApiRequestError(
            f"курс {source}→{target} недоступен или устарел. "
            "Выполните update-rates, проверьте сеть и API-ключ."
        )

    return {
        "from_currency": source,
        "to_currency": target,
        "rate": float(quote["rate"]),
        "updated_at": quote["updated_at"],
        "source": quote["source"],
    }


def get_portfolio(user_id: int) -> Portfolio:
    """Return a user's portfolio model."""
    return _portfolio_for_user(user_id)


def get_portfolio_view(user_id: int, base_currency: str = "USD") -> dict:
    """Build display-ready wallet values and total for one base currency."""
    try:
        base = normalize_currency_code(base_currency)
    except CurrencyNotFoundError as error:
        raise ValueError(f"Неизвестная базовая валюта '{base_currency}'") from error

    portfolio = _portfolio_for_user(user_id)
    rows = []
    total = 0.0
    for code, wallet in sorted(portfolio.wallets.items()):
        quote = get_rate(code, base)
        value = wallet.balance * float(quote["rate"])
        total += value
        rows.append(
            {
                "currency_code": code,
                "balance": wallet.balance,
                "base_value": round(value, 2),
                "rate": float(quote["rate"]),
                "updated_at": quote["updated_at"],
            }
        )

    return {
        "user": portfolio.user,
        "base_currency": base,
        "rows": rows,
        "total": round(total, 2),
    }
