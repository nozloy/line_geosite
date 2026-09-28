"""Exercise release control flow with an isolated gh stub; no GitHub writes."""

import hashlib
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GH_STUB = '''#!/usr/bin/env python3
import os, pathlib, shutil, sys
args = sys.argv[1:]
mode = os.environ["FAKE_MODE"]
log = pathlib.Path(os.environ["FAKE_LOG"])
before = log.read_text() if log.exists() else ""
with log.open("a") as target:
    target.write(" ".join(args) + "\\n")
if args[0] == "api":
    if mode == "api-error" or (mode == "late-api-error" and "release download" in before):
        sys.exit(1)
    obsolete = mode == "obsolete" or (
        mode in ("new-push", "new-push-after-retry") and "release download" in before
    )
    print("b" * 40 if obsolete else os.environ["GITHUB_SHA"])
elif args[:2] == ["release", "create"] and mode == "upload-error":
    sys.exit(1)
elif args[:2] == ["release", "download"]:
    if mode == "download-error":
        print("HTTP 500: temporary GitHub asset failure", file=sys.stderr)
        sys.exit(1)
    if mode in ("transient-download", "new-push-after-retry") and "release download" not in before:
        print("HTTP 500: temporary GitHub asset failure", file=sys.stderr)
        sys.exit(1)
    destination = pathlib.Path(args[args.index("--dir") + 1])
    destination.mkdir(parents=True, exist_ok=True)
    if mode == "partial-download" and "release download" not in before:
        (destination / "geosite_line.dat").write_bytes(b"partial download")
        print("HTTP 500: interrupted asset download", file=sys.stderr)
        sys.exit(1)
    for source in pathlib.Path.cwd().glob("geosite_line.*"):
        if (destination / source.name).exists() and "--clobber" not in args:
            print("asset already exists; use --clobber", file=sys.stderr)
            sys.exit(1)
        shutil.copyfile(source, destination / source.name)
    if mode == "corrupt-upload":
        (destination / "geosite_line.dat").write_bytes(b"broken")
'''


class PublicationTest(unittest.TestCase):
    def test_only_complete_current_builds_become_latest(self):
        scenarios = {
            "success": (0, True, 1), "obsolete": (0, False, 0), "new-push": (0, False, 1),
            "api-error": (1, False, 0), "late-api-error": (1, False, 1),
            "upload-error": (1, False, 0), "download-error": (1, False, 4),
            "corrupt-upload": (1, False, 1), "transient-download": (0, True, 2),
            "partial-download": (0, True, 2), "new-push-after-retry": (0, False, 2),
        }
        for mode, (expected_code, publishes, downloads) in scenarios.items():
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "scripts").mkdir()
                (root / "dist").mkdir()
                shutil.copyfile(ROOT / "scripts" / "publish.sh", root / "scripts" / "publish.sh")
                # macOS has shasum; the production runner has sha256sum.
                checksum = root / "sha256sum"
                checksum.write_text('#!/bin/sh\nexec shasum -a 256 "$@"\n')
                checksum.chmod(0o755)
                (root / "gh").write_text(GH_STUB)
                (root / "gh").chmod(0o755)
                (root / "sleep").write_text('#!/bin/sh\nprintf "%s\\n" "$1" >> "$FAKE_SLEEP_LOG"\n')
                (root / "sleep").chmod(0o755)
                for extension in ("dat", "srs"):
                    name = f"geosite_line.{extension}"
                    payload = extension.encode()
                    (root / "dist" / name).write_bytes(payload)
                    (root / "dist" / f"{name}.sha256sum").write_text(
                        f"{hashlib.sha256(payload).hexdigest()}  {name}\n"
                    )
                log = root / "gh.log"
                sleep_log = root / "sleep.log"
                result = subprocess.run(
                    ["bash", str(root / "scripts" / "publish.sh")],
                    env={**os.environ, "PATH": f"{root}:{os.environ['PATH']}",
                         "GITHUB_REPOSITORY": "example/test", "GITHUB_SHA": "a" * 40,
                         "GITHUB_REF": "refs/heads/main", "GITHUB_EVENT_NAME": "push",
                         "GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "1",
                         "GH_TOKEN": "test-stub-only", "FAKE_MODE": mode, "FAKE_LOG": str(log),
                         "FAKE_SLEEP_LOG": str(sleep_log),
                         "GITHUB_STEP_SUMMARY": str(root / "summary")},
                    capture_output=True, text=True, timeout=20,
                )
                self.assertEqual(result.returncode, expected_code, result.stdout + result.stderr)
                self.assertEqual("release edit" in log.read_text(), publishes)
                self.assertEqual(log.read_text().count("release download "), downloads)
                delays = sleep_log.read_text().splitlines() if sleep_log.exists() else []
                self.assertEqual(delays, [str(2 ** attempt) for attempt in range(1, downloads)])


if __name__ == "__main__":
    unittest.main()
