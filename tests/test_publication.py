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
    obsolete = mode == "obsolete" or (mode == "new-push" and "release download" in before)
    print("b" * 40 if obsolete else os.environ["GITHUB_SHA"])
elif args[:2] == ["release", "create"] and mode == "upload-error":
    sys.exit(1)
elif args[:2] == ["release", "download"]:
    if mode == "download-error":
        sys.exit(1)
    destination = pathlib.Path(args[args.index("--dir") + 1])
    destination.mkdir(parents=True)
    for source in pathlib.Path.cwd().glob("geosite_line.*"):
        shutil.copyfile(source, destination / source.name)
    if mode == "corrupt-upload":
        (destination / "geosite_line.dat").write_bytes(b"broken")
'''


class PublicationTest(unittest.TestCase):
    def test_only_complete_current_builds_become_latest(self):
        scenarios = {
            "success": (0, True), "obsolete": (0, False), "new-push": (0, False),
            "api-error": (1, False), "late-api-error": (1, False),
            "upload-error": (1, False), "download-error": (1, False),
            "corrupt-upload": (1, False),
        }
        for mode, (expected_code, publishes) in scenarios.items():
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
                for extension in ("dat", "srs"):
                    name = f"geosite_line.{extension}"
                    payload = extension.encode()
                    (root / "dist" / name).write_bytes(payload)
                    (root / "dist" / f"{name}.sha256sum").write_text(
                        f"{hashlib.sha256(payload).hexdigest()}  {name}\n"
                    )
                log = root / "gh.log"
                result = subprocess.run(
                    ["bash", str(root / "scripts" / "publish.sh")],
                    env={**os.environ, "PATH": f"{root}:{os.environ['PATH']}",
                         "GITHUB_REPOSITORY": "example/test", "GITHUB_SHA": "a" * 40,
                         "GITHUB_REF": "refs/heads/main", "GITHUB_EVENT_NAME": "push",
                         "GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "1",
                         "GH_TOKEN": "test-stub-only", "FAKE_MODE": mode, "FAKE_LOG": str(log),
                         "GITHUB_STEP_SUMMARY": str(root / "summary")},
                    capture_output=True, text=True,
                )
                self.assertEqual(result.returncode, expected_code, result.stdout + result.stderr)
                self.assertEqual("release edit" in log.read_text(), publishes)


if __name__ == "__main__":
    unittest.main()
