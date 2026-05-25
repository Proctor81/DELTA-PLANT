from __future__ import annotations

from datetime import datetime

import data.database as dbmod


def test_database_prunes_and_reads_last_30_days(tmp_path, monkeypatch):
    monkeypatch.setitem(dbmod.DATABASE_CONFIG, "db_path", str(tmp_path / "delta_test.db"))

    database = dbmod.Database()
    try:
        with database._conn:
            database._conn.execute(
                "INSERT INTO diagnoses (timestamp, summary) VALUES (?, ?)",
                ("2026-04-10T10:00:00", "old"),
            )
            database._conn.execute(
                "INSERT INTO diagnoses (timestamp, summary) VALUES (?, ?)",
                ("2026-05-10T10:00:00", "recent"),
            )

        removed = database.prune_older_than_days(30, now=datetime(2026, 5, 25, 12, 0, 0))
        kept = database.get_records_since_days(30, now=datetime(2026, 5, 25, 12, 0, 0))

        assert removed == 1
        assert len(kept) == 1
        assert kept[0]["summary"] == "recent"
    finally:
        database.close()
