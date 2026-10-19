"""Decorators for tracing domain operations."""

import inspect
import logging
from functools import wraps

ACTION_LOGGER = logging.getLogger("valutatrade_hub.actions")


def _username_for_user_id(user_id):
    """Return a username for a log record without exposing credentials."""
    if user_id is None:
        return "anonymous"

    try:
        from valutatrade_hub.infra.database import DatabaseManager

        users = DatabaseManager().load_users()
        for user in users:
            if user.get("user_id") == user_id:
                return str(user.get("username", user_id))
    except (OSError, ValueError, KeyError):
        pass
    return str(user_id)


def log_action(func=None, *, action=None, verbose=False):
    """Log result and context while never swallowing operation exceptions."""

    def decorate(target):
        operation = action or target.__name__.upper()
        signature = inspect.signature(target)

        @wraps(target)
        def wrapper(*args, **kwargs):
            bound = signature.bind_partial(*args, **kwargs)
            values = bound.arguments
            user_id = values.get("user_id")
            currency = values.get("currency_code", "-")
            amount = values.get("amount", "-")
            username = "anonymous"
            rate = "-"
            base = "USD"
            context = ""

            try:
                result = target(*args, **kwargs)
                if isinstance(result, dict):
                    username = result.get("username") or _username_for_user_id(
                        result.get("user_id", user_id)
                    )
                    rate = result.get("rate", "-")
                    base = result.get("base", "USD")
                    if verbose:
                        context = result.get("context", "")
                else:
                    username = _username_for_user_id(user_id)

                message = (
                    f"{operation} user='{username}' currency='{currency}' "
                    f"amount={amount} rate={rate} base='{base}' result=OK"
                )
                if verbose and context:
                    message += f" context='{context}'"
                ACTION_LOGGER.info(message)
                return result
            except Exception as error:
                username = _username_for_user_id(user_id)
                ACTION_LOGGER.info(
                    f"{operation} user='{username}' currency='{currency}' "
                    f"amount={amount} rate={rate} base='{base}' result=ERROR "
                    f"error_type={type(error).__name__} "
                    f"error_message={str(error)!r}"
                )
                raise

        return wrapper

    if func is not None:
        return decorate(func)
    return decorate
