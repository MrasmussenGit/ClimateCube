from contextlib import closing
import fcntl
from pathlib import Path
import shlex
import shutil
import sqlite3
import subprocess
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from services.database_backup import DB_FILE, backup_database, main, run_sftp, validate_destination


class DatabaseBackupTests(unittest.TestCase):
    def test_validates_destination_and_retention_before_transfer(self):
        validate_destination("backup@nas.local", "/home/backup/climatecube", 14)
        for target, directory, keep in (
            ("-oProxyCommand=bad", "/backups", 14),
            ("user@host;command", "/backups", 14),
            ("host", "/", 14),
            ("host", "//", 14),
            ("host", "/backups/../other", 14),
            ("host", "/backups\nBAD=value", 14),
            ("host", "/backups", 0)
        ):
            with self.subTest(target=target, directory=directory, keep=keep):
                with self.assertRaises(ValueError):
                    validate_destination(target, directory, keep)

    def test_transfers_snapshot_over_verified_noninteractive_sftp(self):
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "source.db"
            with closing(sqlite3.connect(database)) as conn, conn:
                conn.execute("CREATE TABLE readings (value REAL)")
                conn.execute("INSERT INTO readings VALUES (22.0)")
            transferred = []

            def receive(command, input, text, capture_output, check, timeout):
                self.assertEqual(command[0], "sftp")
                self.assertIn("BatchMode=yes", command)
                self.assertIn("StrictHostKeyChecking=yes", command)
                self.assertTrue(check)
                self.assertTrue(text)
                self.assertTrue(capture_output)
                self.assertEqual(timeout, 1800)
                self.assertEqual(command[-1], "backup@nas")
                commands = input.splitlines()
                if commands[0].startswith("put "):
                    source = Path(shlex.split(commands[0])[1])
                    verification = Path(shlex.split(commands[2])[2])
                    transferred.append(source)
                    self.assertTrue(source.read_bytes().startswith(b"SQLite format 3"))
                    shutil.copyfile(source, verification)
                    return SimpleNamespace(stdout="")
                self.assertTrue(commands[0].startswith("rename "))
                destination = shlex.split(commands[0])[2]
                return SimpleNamespace(stdout="sftp> ls -1 /backups\n" + destination + "\n")

            with patch("services.database_backup.subprocess.run", side_effect=receive):
                name = backup_database(database, "backup@nas", "/backups")
            self.assertRegex(name, r"^climatecube-\d{8}T\d{12}Z-[0-9a-f]{32}\.db$")
            self.assertFalse(transferred[0].exists())

    def test_transfer_failure_is_propagated_and_snapshot_is_cleaned(self):
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "source.db"
            with closing(sqlite3.connect(database)) as conn, conn:
                conn.execute("CREATE TABLE readings (value REAL)")
            snapshots = []

            def fail(command, input, **kwargs):
                if input.startswith("put "):
                    snapshots.append(Path(shlex.split(input.splitlines()[0])[1]))
                raise subprocess.CalledProcessError(255, command)

            with patch("services.database_backup.subprocess.run", side_effect=fail):
                with self.assertLogs(level="WARNING"):
                    with self.assertRaises(subprocess.CalledProcessError):
                        backup_database(database, "nas", "/backups")
            self.assertFalse(snapshots[0].exists())

    def test_sftp_authentication_error_is_not_treated_as_success(self):
        error = subprocess.CalledProcessError(255, ["sftp"], stderr="Permission denied")
        with patch("services.database_backup.subprocess.run", side_effect=error):
            with self.assertRaises(subprocess.CalledProcessError):
                run_sftp("nas", ["ls -1 /backups"])

    def test_overlapping_backup_is_rejected_before_transfer(self):
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "source.db"
            with database.with_suffix(".backup.lock").open("a") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                with patch("services.database_backup.run_sftp") as transfer:
                    with self.assertRaises(BlockingIOError):
                        backup_database(database, "nas", "/backups")
                    transfer.assert_not_called()

    def test_existing_ssh_environment_configuration_remains_supported(self):
        with patch.dict("os.environ", {
            "CLIMATECUBE_BACKUP_SSH_TARGET": "backup@nas",
            "CLIMATECUBE_BACKUP_REMOTE_DIR": "/backups",
            "CLIMATECUBE_BACKUP_KEEP": "14"
        }, clear=True), patch("sys.argv", ["database_backup"]):
            with patch("services.database_backup.backup_database", return_value="backup.db") as backup:
                with self.assertLogs(level="INFO"):
                    self.assertEqual(main(), 0)
                backup.assert_called_once_with(DB_FILE, "backup@nas", "/backups", 14)


if __name__ == "__main__":
    unittest.main()
