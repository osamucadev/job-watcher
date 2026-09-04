from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.database import SEED_COMPANIES, connection, initialize_database


class DatabaseTests(unittest.TestCase):
    def test_initialize_database_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.db"
            initialize_database(path)
            initialize_database(path)

            with connection(path) as database:
                companies = database.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
                settings = database.execute("SELECT COUNT(*) FROM settings").fetchone()[0]

            self.assertEqual(companies, len(SEED_COMPANIES))
            self.assertEqual(settings, 1)


if __name__ == "__main__":
    unittest.main()
