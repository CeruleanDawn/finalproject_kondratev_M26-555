"""Unit tests for core domain models."""

import unittest

from valutatrade_hub.core.currencies import (
    CryptoCurrency,
    FiatCurrency,
    get_currency,
)
from valutatrade_hub.core.exceptions import (
    CurrencyNotFoundError,
    InsufficientFundsError,
)
from valutatrade_hub.core.models import Portfolio, User, Wallet


class CurrencyTests(unittest.TestCase):
    def test_display_info(self):
        fiat = FiatCurrency("US Dollar", "USD", "United States")
        self.assertEqual(
            fiat.get_display_info(),
            "[FIAT] USD — US Dollar (Issuing: United States)",
        )
        crypto = CryptoCurrency("Bitcoin", "BTC", "SHA-256", 1.12e12)
        self.assertEqual(
            crypto.get_display_info(),
            "[CRYPTO] BTC — Bitcoin (Algo: SHA-256, MCAP: 1.12e12)",
        )

    def test_registry_unknown_currency(self):
        self.assertEqual(get_currency("btc").code, "BTC")
        with self.assertRaises(CurrencyNotFoundError):
            get_currency("ABC")


class UserTests(unittest.TestCase):
    def test_password_is_salted_and_not_public(self):
        user = User(1, "alice", password="1234")
        self.assertTrue(user.verify_password("1234"))
        self.assertFalse(user.verify_password("wrong"))
        self.assertNotEqual(user.salt, "")
        self.assertNotIn("hashed_password", user.get_user_info())
        self.assertNotIn("salt", user.get_user_info())

    def test_short_password_rejected(self):
        with self.assertRaisesRegex(ValueError, "не короче 4"):
            User(1, "alice", password="123")


class WalletTests(unittest.TestCase):
    def test_deposit_withdraw_and_balance_validation(self):
        wallet = Wallet("USD", 10)
        wallet.deposit(5)
        self.assertEqual(wallet.balance, 15)
        wallet.withdraw(3)
        self.assertEqual(wallet.balance, 12)
        with self.assertRaises(ValueError):
            wallet.balance = -1

    def test_insufficient_funds(self):
        wallet = Wallet("BTC", 0.05)
        with self.assertRaises(InsufficientFundsError):
            wallet.withdraw(0.1)

    def test_portfolio_wallet_copy(self):
        user = User(1, "alice", password="1234")
        portfolio = Portfolio(user)
        portfolio.add_currency("USD")
        copy = portfolio.wallets
        copy.clear()
        self.assertIn("USD", portfolio.wallets)


if __name__ == "__main__":
    unittest.main()
