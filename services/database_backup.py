"""Consistent SQLite snapshots transferred to a separate host over SFTP."""

import argparse
from contextlib import closing
from datetime import datetime, timezone
import fcntl
import hashlib
import logging
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import tempfile
import uuid

from services.database import DB_FILE


BACKUP_PATTERN = r"climatecube-\d{8}T\d{12}Z-[0-9a-f]{32}\.db"


def validate_destination(target, directory, keep):
    if not re.fullmatch(r"(?:[a-zA-Z0-9_][a-zA-Z0-9_.-]*@)?[a-zA-Z0-9][a-zA-Z0-9.-]*", target):
        raise ValueError("SFTP target must be hostname or user@hostname")
    if (
        not re.fullmatch(r"/[a-zA-Z0-9_./-]+", directory)
        or not directory.strip("/")
        or Path(directory) == Path("/")
        or ".." in Path(directory).parts
    ):
        raise ValueError("Remote directory must be an absolute non-root path without spaces or '..'")
    if keep < 1:
        raise ValueError("Retention must be at least one backup")


def create_snapshot(database, output):
    database = Path(database).resolve()
    with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as source:
        if not source.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchone():
            raise sqlite3.DatabaseError("Source database has no tables")
        with closing(sqlite3.connect(output)) as destination:
            source.backup(destination, pages=256, sleep=0.1)
            destination.execute("PRAGMA journal_mode=DELETE")
            if destination.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
                raise sqlite3.DatabaseError("Database snapshot failed integrity check")


def sftp_quote(path):
    path = str(path)
    if "\n" in path or "\r" in path:
        raise ValueError("SFTP paths must not contain newlines")
    return '"' + path.replace("\\", "\\\\").replace('"', '\\"') + '"'


def run_sftp(target, commands):
    result = subprocess.run(
        [
            "sftp", "-q", "-b", "-",
            "-o", "BatchMode=yes",
            "-o", "StrictHostKeyChecking=yes",
            "-o", "ConnectTimeout=20",
            "-o", "ServerAliveInterval=30",
            "-o", "ServerAliveCountMax=3",
            target
        ],
        input="\n".join(commands) + "\n",
        text=True,
        capture_output=True,
        check=True,
        timeout=1800
    )
    return result.stdout


def file_digest(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.digest()


def transfer_snapshot(snapshot, target, directory, keep):
    directory = directory.rstrip("/")
    name = snapshot.name
    staging = directory + "/." + name + ".tmp"
    destination = directory + "/" + name
    verification = snapshot.with_suffix(".verify")
    try:
        run_sftp(target, [
            "put {} {}".format(sftp_quote(snapshot), sftp_quote(staging)),
            "chmod 600 " + sftp_quote(staging),
            "get {} {}".format(sftp_quote(staging), sftp_quote(verification))
        ])
        if file_digest(snapshot) != file_digest(verification):
            raise RuntimeError("Uploaded backup failed read-back verification")
        listing = run_sftp(target, [
            "rename {} {}".format(sftp_quote(staging), sftp_quote(destination)),
            "ls -1 " + sftp_quote(directory)
        ])
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
        try:
            run_sftp(target, ["rm " + sftp_quote(staging)])
        except (OSError, subprocess.SubprocessError) as cleanup_error:
            logging.warning("Could not remove staged backup %s: %s", staging, cleanup_error)
        raise

    pattern = re.compile(r"^(?:" + re.escape(directory) + r"/)?(" + BACKUP_PATTERN + r")$")
    names = {
        match.group(1)
        for line in listing.splitlines()
        if (match := pattern.fullmatch(line.strip())) is not None
    }
    if name not in names:
        raise RuntimeError("SFTP listing did not confirm the published backup; retention not applied")
    old_names = sorted(names)[:-keep]
    if old_names:
        run_sftp(target, ["rm " + sftp_quote(directory + "/" + old) for old in old_names])


def backup_database(database, target, directory, keep=14):
    validate_destination(target, directory, keep)
    name = "climatecube-{}-{}.db".format(
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"),
        uuid.uuid4().hex
    )
    lock_file = Path(database).resolve().with_suffix(".backup.lock")
    with lock_file.open("a") as lock, tempfile.TemporaryDirectory(prefix="climatecube-backup-") as temporary:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        snapshot = Path(temporary) / name
        create_snapshot(database, snapshot)
        transfer_snapshot(snapshot, target, directory, keep)
    return name


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=DB_FILE)
    parser.add_argument(
        "--sftp-target", "--ssh-target", dest="sftp_target",
        default=os.environ.get("CLIMATECUBE_BACKUP_SFTP_TARGET")
        or os.environ.get("CLIMATECUBE_BACKUP_SSH_TARGET")
    )
    parser.add_argument("--remote-dir", default=os.environ.get("CLIMATECUBE_BACKUP_REMOTE_DIR"))
    parser.add_argument("--keep", type=int, default=os.environ.get("CLIMATECUBE_BACKUP_KEEP", "14"))
    args = parser.parse_args()
    if not args.sftp_target or not args.remote_dir:
        parser.error("--sftp-target and --remote-dir (or their environment variables) are required")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        name = backup_database(args.database, args.sftp_target, args.remote_dir, args.keep)
    except (OSError, ValueError, RuntimeError, sqlite3.Error, subprocess.SubprocessError) as error:
        logging.error("Database backup failed: %s", error)
        if isinstance(error, subprocess.CalledProcessError) and error.stderr:
            logging.error("SFTP: %s", error.stderr.strip())
        return 1
    logging.info("Database backup completed: %s", name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
