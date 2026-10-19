"""Interactive CLI for ValutaTrade Hub."""

import logging
import shlex

from prettytable import PrettyTable

from valutatrade_hub.core.currencies import (
    CryptoCurrency,
    get_currency,
    list_supported_codes,
)
from valutatrade_hub.core.exceptions import (
    ApiRequestError,
    CurrencyNotFoundError,
    InsufficientFundsError,
)
from valutatrade_hub.core.usecases import (
    buy,
    deposit,
    get_portfolio_view,
    get_rate,
    login,
    register,
    sell,
)
from valutatrade_hub.infra.database import DatabaseManager
from valutatrade_hub.logging_config import configure_logging
from valutatrade_hub.parser_service.updater import RatesUpdater


def _parse_options(tokens: list[str]) -> dict[str, str]:
    """Parse pairs of --option value without shelling out to an OS command."""
    if len(tokens) % 2:
        raise ValueError("Каждая опция должна иметь значение")
    options = {}
    for index in range(0, len(tokens), 2):
        key, value = tokens[index], tokens[index + 1]
        if not key.startswith("--") or len(key) <= 2:
            raise ValueError(f"Некорректная опция: {key}")
        normalized = key[2:].replace("-", "_")
        if normalized in options:
            raise ValueError(f"Опция {key} указана несколько раз")
        options[normalized] = value
    return options


def _required(options: dict, key: str) -> str:
    """Return required option or raise a friendly validation error."""
    value = options.get(key)
    if value is None or not str(value).strip():
        raise ValueError(f"Не указана обязательная опция --{key.replace('_', '-')}")
    return str(value)


def _amount(options: dict) -> float:
    """Parse the --amount option."""
    raw = _required(options, "amount")
    try:
        value = float(raw)
    except ValueError as error:
        raise ValueError("'amount' должен быть положительным числом") from error
    if value <= 0:
        raise ValueError("'amount' должен быть положительным числом")
    return value


def print_help():
    """Print all commands and argument patterns."""
    print(
        """
ValutaTrade Hub — команды

register --username <имя> --password <пароль>
login --username <имя> --password <пароль>
logout
show-portfolio [--base USD]
deposit --currency USD --amount 10000
buy --currency BTC --amount 0.05
sell --currency BTC --amount 0.01
get-rate --from USD --to BTC

update-rates [--source coingecko|exchangerate]
show-rates [--currency BTC] [--top 2] [--base USD]

help
exit

Валюта должна быть зарегистрирована в currencies.py.
Все суммы должны быть положительными. Новый портфель пустой;
для симуляции сделок сначала пополните USD-кошелёк командой deposit.
"""
    )


def _require_login(current_user):
    """Require a logged-in user."""
    if current_user is None:
        raise ValueError("Сначала выполните login")
    return current_user


def _handle_show_rates(tokens):
    """Display cached rates with optional currency/top/base filters."""
    options = _parse_options(tokens)
    allowed = {"currency", "top", "base"}
    unknown = set(options) - allowed
    if unknown:
        raise ValueError(f"Неизвестная опция --{sorted(unknown)[0].replace('_', '-')}")
    database = DatabaseManager()
    database.ensure_initialized()
    snapshot = database.load_rates()
    pairs = snapshot.get("pairs", {})
    if not pairs:
        print(
            "Локальный кеш курсов пуст. Выполните 'update-rates', "
            "чтобы загрузить данные."
        )
        return

    currency_filter = options.get("currency")
    if currency_filter:
        currency_filter = get_currency(currency_filter).code

    base = get_currency(options.get("base", "USD")).code
    top = None
    if "top" in options:
        try:
            top = int(options["top"])
        except ValueError as error:
            raise ValueError("--top должен быть целым числом") from error
        if top < 1:
            raise ValueError("--top должен быть положительным числом")

    rows = []
    from_codes = {pair.split("_", maxsplit=1)[0] for pair in pairs if "_" in pair}
    if base != "USD":
        from_codes.add("USD")
    for code in sorted(from_codes):
        try:
            currency = get_currency(code)
        except CurrencyNotFoundError:
            continue
        if (
            currency_filter
            and currency_filter not in code
            and not any(
                currency_filter in pair for pair in pairs if pair.startswith(f"{code}_")
            )
        ):
            continue
        if top is not None and not isinstance(currency, CryptoCurrency):
            continue

        try:
            quote = get_rate(code, base)
        except ApiRequestError:
            # show-rates is a cache-view command; do not stop displaying other records.
            cached = pairs.get(f"{code}_{base}")
            if not cached:
                continue
            quote = cached
        rows.append(
            {
                "pair": f"{code}_{base}",
                "rate": float(quote["rate"]),
                "updated_at": quote.get("updated_at", "unknown"),
                "source": quote.get("source", "cache"),
                "is_crypto": isinstance(currency, CryptoCurrency),
            }
        )

    rows.sort(key=lambda item: item["rate"], reverse=top is not None)
    if top is not None:
        rows = rows[:top]
    if not rows:
        if currency_filter:
            print(f"Курс для '{currency_filter}' не найден в кеше.")
        else:
            print("В кеше нет подходящих курсов.")
        return

    print(f"Rates from cache (updated at {snapshot.get('last_refresh', 'unknown')}):")
    table = PrettyTable()
    table.field_names = ["Pair", "Rate", "Updated at", "Source"]
    for row in rows:
        table.add_row(
            [
                row["pair"],
                f"{row['rate']:.8g}",
                row["updated_at"],
                row["source"],
            ]
        )
    print(table)


def _run_command(tokens, current_user):
    """Dispatch a parsed command and return the possibly changed session user."""
    command = tokens[0].lower()
    arguments = tokens[1:]

    if command in {"help", "?"}:
        if arguments:
            raise ValueError("Команда help не принимает аргументы")
        print_help()
        return current_user

    if command == "exit":
        if arguments:
            raise ValueError("Команда exit не принимает аргументы")
        return "EXIT"

    if command == "register":
        options = _parse_options(arguments)
        user = register(
            _required(options, "username"),
            _required(options, "password"),
        )
        print(
            f"Пользователь '{user.username}' зарегистрирован (id={user.user_id}). "
            "Войдите: login --username "
            f"{user.username} --password ****"
        )
        return current_user

    if command == "login":
        options = _parse_options(arguments)
        user = login(
            _required(options, "username"),
            _required(options, "password"),
        )
        print(f"Вы вошли как '{user.username}'")
        return user

    if command == "logout":
        print("Вы вышли из системы.")
        return None

    if command == "deposit":
        user = _require_login(current_user)
        options = _parse_options(arguments)
        result = deposit(
            user.user_id,
            _required(options, "currency"),
            _amount(options),
        )
        print(
            f"Кошелёк {result['currency_code']} пополнен: "
            f"{result['previous_balance']:.4f} → {result['new_balance']:.4f} "
            f"{result['currency_code']}."
        )
        return user

    if command == "show-portfolio":
        user = _require_login(current_user)
        options = _parse_options(arguments)
        unknown = set(options) - {"base"}
        if unknown:
            raise ValueError(f"Неизвестная опция --{sorted(unknown)[0]}")
        view = get_portfolio_view(user.user_id, options.get("base", "USD"))
        print(
            f"Портфель пользователя '{user.username}' (база: {view['base_currency']}):"
        )
        if not view["rows"]:
            print("Портфель пуст. Пополните кошелёк командой deposit.")
            return user
        table = PrettyTable()
        table.field_names = ["Валюта", "Баланс", f"Стоимость ({view['base_currency']})"]
        for row in view["rows"]:
            precision = 4 if row["currency_code"] in {"BTC", "ETH", "SOL"} else 2
            table.add_row(
                [
                    row["currency_code"],
                    f"{row['balance']:.{precision}f}",
                    f"{row['base_value']:,.2f}",
                ]
            )
        print(table)
        print(f"ИТОГО: {view['total']:,.2f} {view['base_currency']}")
        return user

    if command == "buy":
        user = _require_login(current_user)
        options = _parse_options(arguments)
        result = buy(
            user.user_id,
            _required(options, "currency"),
            _amount(options),
        )
        code = result["currency_code"]
        print(
            f"Покупка выполнена: {result['amount']:.4f} {code} "
            f"по курсу {result['rate']:.2f} USD/{code}"
        )
        print("Изменения в портфеле:")
        print(
            f"- {code}: было {result['previous_balance']:.4f} "
            f"→ стало {result['new_balance']:.4f}"
        )
        print(
            f"- USD: было {result['usd_before']:.2f} → стало {result['usd_after']:.2f}"
        )
        print(f"Оценочная стоимость покупки: {result['cost_usd']:,.2f} USD")
        return user

    if command == "sell":
        user = _require_login(current_user)
        options = _parse_options(arguments)
        result = sell(
            user.user_id,
            _required(options, "currency"),
            _amount(options),
        )
        code = result["currency_code"]
        print(
            f"Продажа выполнена: {result['amount']:.4f} {code} "
            f"по курсу {result['rate']:.2f} USD/{code}"
        )
        print("Изменения в портфеле:")
        print(
            f"- {code}: было {result['previous_balance']:.4f} "
            f"→ стало {result['new_balance']:.4f}"
        )
        print(
            f"- USD: было {result['usd_before']:.2f} → стало {result['usd_after']:.2f}"
        )
        print(f"Оценочная выручка: {result['proceeds_usd']:,.2f} USD")
        return user

    if command == "get-rate":
        options = _parse_options(arguments)
        source = _required(options, "from")
        target = _required(options, "to")
        quote = get_rate(source, target)
        print(
            f"Курс {quote['from_currency']}→{quote['to_currency']}: "
            f"{quote['rate']:.8g} (обновлено: {quote['updated_at']}, "
            f"источник: {quote['source']})"
        )
        reverse = get_rate(target, source)
        print(f"Обратный курс {target}→{source}: {reverse['rate']:.8g}")
        return current_user

    if command == "update-rates":
        options = _parse_options(arguments)
        unknown = set(options) - {"source"}
        if unknown:
            raise ValueError(f"Неизвестная опция --{sorted(unknown)[0]}")
        summary = RatesUpdater().run_update(options.get("source"))
        print(
            f"Обновлено курсов: {summary['updated_count']}; "
            f"время: {summary['last_refresh']}"
        )
        if summary["errors"]:
            print(
                "Обновление завершено частично. Подробности: logs/parser.log. "
                "Проверьте API-ключ/сеть."
            )
        return current_user

    if command == "show-rates":
        _handle_show_rates(arguments)
        return current_user

    raise ValueError(f"Функции {command} нет. Попробуйте снова.")


def run_cli():
    """Run the interactive command loop."""
    DatabaseManager().ensure_initialized()
    current_user = None
    print("ValutaTrade Hub — симулятор валютного кошелька.")
    print("Введите help для просмотра команд; exit — выход.\n")

    while True:
        try:
            user_input = input("> ")
        except (EOFError, KeyboardInterrupt):
            print("\nВыход из программы.")
            break

        try:
            tokens = shlex.split(user_input)
            if not tokens:
                continue
            result = _run_command(tokens, current_user)
            if result == "EXIT":
                print("До свидания!")
                break
            current_user = result
        except InsufficientFundsError as error:
            print(str(error))
        except CurrencyNotFoundError as error:
            print(str(error))
            print(f"Поддерживаемые коды: {', '.join(list_supported_codes())}")
            print("Проверьте команду get-rate.")
        except ApiRequestError as error:
            print(str(error))
            print("Повторите позже, проверьте сеть и переменную EXCHANGERATE_API_KEY.")
        except (ValueError, KeyError) as error:
            print(str(error))
        except Exception as error:
            logging.getLogger("valutatrade_hub.actions").exception(
                "Unexpected CLI exception"
            )
            print(f"Непредвиденная ошибка: {error}")


def main():
    """Configure logging and run the CLI."""
    configure_logging()
    run_cli()


if __name__ == "__main__":
    main()
