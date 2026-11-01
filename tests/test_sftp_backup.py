from contextlib import closing
from pathlib import Path
import shlex
import shutil
import sqlite3
import stat
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from services.database_backup import backup_database


SFTP_SERVER = next((
    path for path in ("/usr/lib/openssh/sftp-server", "/usr/lib/ssh/sftp-server")
    if Path(path).is_file()
), None)
SUBPROCESS_RUN = subprocess.run


@unittest.skipUnless(SFTP_SERVER and shutil.which("sftp"), "OpenSSH SFTP client/server required")
class SFTPBackupTests(unittest.TestCase):
    def local_sftp(self, command, **kwargs):
        self.assertEqual(command[0], "sftp")
        return SUBPROCESS_RUN(["sftp", "-q", "-D", SFTP_SERVER, "-b", "-"], **kwargs)

    def create_database(self, path):
        with closing(sqlite3.connect(path)) as conn, conn:
            conn.execute("CREATE TABLE readings (value REAL)")
            conn.execute("INSERT INTO readings VALUES (21.5)")

    def test_real_sftp_upload_readback_publish_retention_and_restore(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.db"
            remote = root / "remote"
            self.create_database(source)
            remote.mkdir()
            unrelated = remote / "important.db"
            unrelated.write_text("preserve")
            names = []
            with patch("services.database_backup.subprocess.run", side_effect=self.local_sftp):
                for _ in range(16):
                    names.append(backup_database(source, "nas", str(remote)))
            self.assertEqual(sorted(path.name for path in remote.glob("climatecube-*.db")), names[2:])
            self.assertEqual(unrelated.read_text(), "preserve")
            with closing(sqlite3.connect(remote / names[-1])) as conn:
                self.assertEqual(conn.execute("SELECT * FROM readings").fetchall(), [(21.5,)])
                self.assertEqual(conn.execute("PRAGMA quick_check").fetchall(), [("ok",)])
            self.assertEqual(stat.S_IMODE((remote / names[-1]).stat().st_mode), 0o600)
            self.assertEqual(list(remote.glob("*.tmp")), [])

    def test_bad_readback_does_not_publish_or_prune_and_removes_staging(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.db"
            remote = root / "remote"
            self.create_database(source)
            remote.mkdir()
            existing = remote / f"climatecube-20261101T000000000000Z-{'a' * 32}.db"
            existing.write_bytes(b"existing backup")

            def corrupt_readback(command, **kwargs):
                result = self.local_sftp(command, **kwargs)
                commands = kwargs["input"].splitlines()
                if commands[0].startswith("put "):
                    verification = Path(shlex.split(commands[2])[2])
                    verification.write_bytes(b"corrupt data")
                return result

            with patch("services.database_backup.subprocess.run", side_effect=corrupt_readback):
                with self.assertRaisesRegex(RuntimeError, "read-back verification"):
                    backup_database(source, "nas", str(remote), keep=1)
            self.assertEqual(list(remote.iterdir()), [existing])
            self.assertEqual(existing.read_bytes(), b"existing backup")

    def test_missing_remote_directory_reports_failure_without_creating_it(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.db"
            remote = root / "missing"
            self.create_database(source)
            with patch("services.database_backup.subprocess.run", side_effect=self.local_sftp):
                with self.assertLogs(level="WARNING"):
                    with self.assertRaises(subprocess.CalledProcessError):
                        backup_database(source, "nas", str(remote))
            self.assertFalse(remote.exists())


if __name__ == "__main__":
    unittest.main()
