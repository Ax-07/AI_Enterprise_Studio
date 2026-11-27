"""Connection lifecycle contracts, using only temporary SQLite fixtures."""
import sqlite3
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import serveur as s
from infrastructure.database import transaction, read_snapshot


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / 'fixture # ?.sqlite3'
        # Windows does not permit '?' in file names.
        import os
        if os.name == 'nt':
            self.path = Path(directory.name) / 'fixture # %.sqlite3'
        with transaction(self.path) as db:
            db.execute('CREATE TABLE records(id INTEGER PRIMARY KEY, value TEXT)')
            db.execute("INSERT INTO records(value) VALUES ('initial')")

    def test_commit_rows_and_close(self):
        with transaction(self.path) as db:
            db.execute("INSERT INTO records(value) VALUES ('committed')")
            self.assertEqual(db.execute('SELECT value FROM records WHERE id=1').fetchone()['value'], 'initial')
        with self.assertRaises(sqlite3.ProgrammingError):
            db.execute('SELECT 1')
        with transaction(self.path) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM records').fetchone()[0], 2)

    def test_rollback_and_close(self):
        with self.assertRaisesRegex(RuntimeError, 'fixture failure'):
            with transaction(self.path) as db:
                db.execute("INSERT INTO records(value) VALUES ('discarded')")
                raise RuntimeError('fixture failure')
        with self.assertRaises(sqlite3.ProgrammingError):
            db.execute('SELECT 1')
        with transaction(self.path) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM records').fetchone()[0], 1)

    def test_read_snapshot_is_read_only_and_closed(self):
        before = self.path.read_bytes()
        with read_snapshot(self.path) as db:
            self.assertTrue(db.in_transaction)
            self.assertEqual(db.execute('PRAGMA query_only').fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT value FROM records').fetchone()['value'], 'initial')
            with self.assertRaises(sqlite3.OperationalError):
                db.execute("INSERT INTO records(value) VALUES ('forbidden')")
        with self.assertRaises(sqlite3.ProgrammingError):
            db.execute('SELECT 1')
        self.assertEqual(self.path.read_bytes(), before)

    def test_missing_read_snapshot_does_not_create_database(self):
        missing = self.path.parent/'missing.sqlite3'
        with self.assertRaises(sqlite3.OperationalError):
            with read_snapshot(missing):
                self.fail('Missing database opened')
        self.assertFalse(missing.exists())

    def test_server_facade_resolves_db_at_call_time(self):
        other = self.path.parent/'other.sqlite3'
        with patch.object(s, 'DB', self.path):
            with s.db() as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM records').fetchone()[0], 1)
        with patch.object(s, 'DB', other):
            with s.db() as db:
                db.execute('CREATE TABLE other(id INTEGER)')
            self.assertTrue(other.exists())
        with transaction(self.path) as db:
            self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name='other'").fetchone())


if __name__ == '__main__':
    unittest.main()
