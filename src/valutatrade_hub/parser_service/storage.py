"""Atomic storage for latest rates and historical rate measurements."""

from datetime import datetime, timezone

from valutatrade_hub.infra.database import DatabaseManager, utc_now_iso


class RatesStorage:
    """Store a latest snapshot in rates.json and append history records."""

    def __init__(self, database: DatabaseManager | None = None):
        self.database = database or DatabaseManager()

    def read_snapshot(self) -> dict:
        """Read current rates snapshot."""
        self.database.ensure_initialized()
        return self.database.load_rates()

    def save_updates(self, rates: dict[str, dict], timestamp: str | None = None):
        """Merge newer quotes and atomically write snapshot plus history."""
        updated_at = timestamp or utc_now_iso()
        with self.database.transaction():
            snapshot = self.database.load_rates()
            pairs = dict(snapshot.get("pairs", {}))
            history = self.database.load_history()
            known_ids = {item.get("id") for item in history}

            for pair, quote in rates.items():
                current = pairs.get(pair)
                if current and current.get("updated_at", "") > updated_at:
                    continue
                rate = float(quote["rate"])
                source = str(quote["source"])
                pairs[pair] = {
                    "rate": rate,
                    "updated_at": updated_at,
                    "source": source,
                }
                record_id = f"{pair}_{updated_at}"
                if record_id not in known_ids:
                    history.append(
                        {
                            "id": record_id,
                            "from_currency": pair.split("_", maxsplit=1)[0],
                            "to_currency": pair.split("_", maxsplit=1)[1],
                            "rate": rate,
                            "timestamp": updated_at,
                            "source": source,
                            "meta": {"status_code": 200},
                        }
                    )
                    known_ids.add(record_id)

            snapshot["pairs"] = pairs
            snapshot["last_refresh"] = updated_at
            self.database.save_rates(snapshot)
            self.database.save_history(history)

    @staticmethod
    def timestamp_now():
        """Expose a testable UTC timestamp factory."""
        return (
            datetime.now(timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z")
        )
