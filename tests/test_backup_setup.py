import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


PROJECT_DIR = Path(__file__).resolve().parent.parent
SCRIPT = PROJECT_DIR / "scripts" / "setup_backup.sh"


class BackupSetupTests(unittest.TestCase):
    def test_rejects_placeholders_before_running_sudo(self):
        for target, directory in (
            ("backup@your-server", "/backups"),
            ("backup@nas.local", "/absolute/backup/path"),
            ("backup@nas.local", "/absolute/backup/directory")
        ):
            with self.subTest(target=target, directory=directory):
                result = subprocess.run(
                    ["bash", str(SCRIPT), target, directory, "14"],
                    capture_output=True, text=True, check=False
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("example values", result.stderr)
                self.assertNotIn("Testing the first", result.stdout)

    def test_failed_first_backup_prints_diagnostics_without_enabling_timer(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "scripts").mkdir()
            script = root / "scripts" / "setup_backup.sh"
            shutil.copyfile(SCRIPT, script)
            (root / ".venv" / "bin").mkdir(parents=True)
            (root / ".venv" / "bin" / "python").symlink_to(sys.executable)
            sudo = Path(temporary) / "sudo"
            sudo.write_text(
                "#!/bin/sh\n"
                'case "$1" in\n'
                '  install) exit 0 ;;\n'
                '  tee) cat > /dev/null ;;\n'
                '  systemctl)\n'
                '    echo "systemctl $2"\n'
                '    case "$2" in\n'
                '      start) exit 1 ;;\n'
                '      status) echo "service status diagnostic"; exit 3 ;;\n'
                '    esac ;;\n'
                '  journalctl) echo "SSH authentication failed diagnostic" ;;\n'
                '  *) exit 1 ;;\n'
                'esac\n'
            )
            sudo.chmod(0o700)
            result = subprocess.run(
                ["bash", str(script), "backup@nas.local", "/backups", "14"],
                env={
                    **os.environ,
                    "PATH": temporary + os.pathsep + os.environ["PATH"],
                    "PYTHONPATH": str(PROJECT_DIR)
                },
                capture_output=True, text=True, check=False
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("first backup failed", result.stderr)
            self.assertIn("service status diagnostic", result.stdout)
            self.assertIn("SSH authentication failed diagnostic", result.stdout)
            self.assertNotIn("systemctl enable", result.stdout)
            self.assertNotIn("Daily backups enabled", result.stdout)


if __name__ == "__main__":
    unittest.main()
