import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


PROJECT_DIR = Path(__file__).resolve().parent.parent
SCRIPT = PROJECT_DIR / "scripts" / "image_pico.sh"


class ImagePicoTests(unittest.TestCase):
    def run_imaging(self, failure=""):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            calls_file = root / "calls.jsonl"
            mpremote = root / "mpremote"
            mpremote.write_text(
                "#!" + sys.executable + "\n"
                "import json, os, pathlib, sys\n"
                "args = sys.argv[1:]\n"
                "with open(os.environ['TEST_IMAGING_CALLS'], 'a') as output:\n"
                "    output.write(json.dumps(args) + '\\n')\n"
                "failure = os.environ.get('TEST_IMAGING_FAILURE')\n"
                "if 'cp' in args:\n"
                "    source = pathlib.Path(args[args.index('cp') + 1])\n"
                "    if not source.is_file():\n"
                "        sys.exit(2)\n"
                "    if failure == 'sensor.py' and source.name == 'sensor.py':\n"
                "        sys.exit(1)\n"
                "if 'exec' in args:\n"
                "    code = args[args.index('exec') + 1]\n"
                "    if 'os.uname()' in code:\n"
                "        print('Raspberry Pi Pico W with RP2040')\n"
                "    else:\n"
                "        if failure == 'verification':\n"
                "            sys.exit(1)\n"
                "        print('Image verification passed')\n"
            )
            mpremote.chmod(0o700)
            getent = root / "getent"
            getent.write_text("#!/bin/sh\nprintf '192.0.2.1 STREAM climatecube.local\\n'\n")
            getent.chmod(0o700)
            config = root / "test-config.py"
            config.write_text(
                'SSID = "test-network"\nPASSWORD = "test-only"\n'
                'READING_INTERVAL_SEC = 300\n'
            )
            result = subprocess.run(
                ["bash", str(SCRIPT), "--port", "/dev/test-pico", "--config", str(config)],
                env={
                    **os.environ,
                    "PATH": temporary + os.pathsep + os.environ["PATH"],
                    "TEST_IMAGING_CALLS": str(calls_file),
                    "TEST_IMAGING_FAILURE": failure
                },
                capture_output=True, text=True, check=False
            )
            calls = [json.loads(line) for line in calls_file.read_text().splitlines()]
            return result, calls

    def test_uploads_all_current_modules_and_verifies_recovery_before_reset(self):
        result, calls = self.run_imaging()
        self.assertEqual(result.returncode, 0, result.stderr)
        uploads = [call for call in calls if "cp" in call]
        sources = {
            Path(call[call.index("cp") + 1]).name
            for call in uploads if call[-1] == ":"
        }
        expected = {
            path.name for path in (PROJECT_DIR / "pico").glob("*.py")
            if path.name not in ("config.py", "config_template.py")
        }
        self.assertEqual(sources, expected)
        self.assertTrue({"main.py", "sensor.py", "sensor_manager.py", "display.py"} <= sources)
        self.assertFalse(any("__pycache__" in str(call) for call in uploads))
        verification = next(
            call for call in calls if "exec" in call and "Sensor recovery API missing" in call[-1]
        )
        self.assertIn("callable(sensor.get_error)", verification[-1])
        self.assertIn("callable(sensor_manager.get_error)", verification[-1])
        self.assertGreater(calls.index(verification), max(calls.index(call) for call in uploads))
        self.assertEqual(calls[-1], ["connect", "/dev/test-pico", "reset"])
        self.assertIn("Pico W imaging complete", result.stdout)

    def test_failed_sensor_upload_stops_before_verification_or_reset(self):
        result, calls = self.run_imaging("sensor.py")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any("reset" in call for call in calls))
        self.assertFalse(any("Image verification passed" in call[-1] for call in calls))
        self.assertNotIn("Pico W imaging complete", result.stdout)

    def test_failed_verification_stops_before_reset(self):
        result, calls = self.run_imaging("verification")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any("reset" in call for call in calls))
        self.assertNotIn("Pico W imaging complete", result.stdout)


if __name__ == "__main__":
    unittest.main()
