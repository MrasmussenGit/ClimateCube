from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest

from services.database_backup import create_snapshot


class DatabaseSnapshotTests(unittest.TestCase):
    def test_snapshot_includes_committed_wal_data_and_restores_all_tables(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            source = directory / "source.db"
            snapshot = directory / "snapshot.db"
            restored = directory / "restored.db"
            with closing(sqlite3.connect(source)) as writer, writer:
                writer.execute("PRAGMA journal_mode=WAL")
                writer.execute("CREATE TABLE sensor_reading (value REAL)")
                writer.execute("CREATE TABLE app_setting (value TEXT)")
                writer.execute("INSERT INTO sensor_reading VALUES (23.5)")
                writer.execute("INSERT INTO app_setting VALUES ('12345')")
                writer.commit()
                create_snapshot(source, snapshot)
                writer.execute("INSERT INTO sensor_reading VALUES (24.0)")
                writer.commit()
                create_snapshot(snapshot, restored)
            with closing(sqlite3.connect(restored)) as conn:
                self.assertEqual(conn.execute("PRAGMA quick_check").fetchall(), [("ok",)])
                self.assertEqual(conn.execute("SELECT * FROM sensor_reading").fetchall(), [(23.5,)])
                self.assertEqual(conn.execute("SELECT * FROM app_setting").fetchall(), [("12345",)])
            self.assertFalse(Path(str(snapshot) + "-wal").exists())

    def test_missing_source_is_not_created(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "missing.db"
            with self.assertRaises(sqlite3.OperationalError):
                create_snapshot(source, Path(temporary) / "backup.db")
            self.assertFalse(source.exists())

    def test_corrupt_or_empty_source_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "source.db"
            for contents in (b"not a database", b""):
                source.write_bytes(contents)
                with self.assertRaises(sqlite3.DatabaseError):
                    create_snapshot(source, Path(temporary) / "backup.db")


if __name__ == "__main__":
    unittest.main()
