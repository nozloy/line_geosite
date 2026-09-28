#!/usr/bin/env python3
"""Integration checks using real compilers, Xray and loopback-only Mihomo."""

import json
import os
import subprocess
import tempfile
from pathlib import Path

from build import build
from domain_rules import read_domains
from mihomo_check import verify_mrs_matching
from pinned_tools import ROOT, download_tool, sha256


def verify_srs_matching(output: Path) -> None:
    sing_box = download_tool("sing-box")
    cases = {}
    for domain in read_domains(ROOT / "data" / "line"):
        cases[domain] = True
        cases[f"www.{domain}"] = True
        cases[f"not{domain}"] = False
        cases[f"{domain}.example"] = False
    for domain, expected in cases.items():
        result = subprocess.run(
            [str(sing_box), "--disable-color", "rule-set", "match", "--format", "binary",
             str(output / "geosite_line.srs"), domain], capture_output=True, text=True, check=True,
        )
        matched = "match rules." in result.stdout + result.stderr
        if matched != expected:
            raise ValueError(f"Incorrect SRS domain boundary match for {domain}")


def main() -> None:
    subprocess.run(["python3", "-m", "unittest", "discover", "-s", "tests", "-v"], cwd=ROOT, check=True)
    subprocess.run(["bash", "-n", str(ROOT / "scripts" / "publish.sh")], check=True)
    output = ROOT / "dist"
    build(ROOT / "data" / "line", output)
    verify_srs_matching(output)
    verify_mrs_matching(output, read_domains(ROOT / "data" / "line"))
    with tempfile.TemporaryDirectory(prefix="verify-", dir=ROOT / ".cache") as directory:
        work = Path(directory)
        repeated = work / "repeated"
        build(ROOT / "data" / "line", repeated)
        for original in output.iterdir():
            if sha256(original) != sha256(repeated / original.name):
                raise ValueError(f"Non-reproducible artifact: {original.name}")

        # Invalid input must fail before creating or overwriting release files.
        for label, content in (("empty", "# comment only\n"), ("invalid", "domain:https://asos.com\n")):
            source = work / label
            source.write_text(content)
            rejected_output = work / f"{label}-output"
            result = subprocess.run(
                ["python3", str(ROOT / "scripts" / "build.py"), "--source", str(source),
                 "--output", str(rejected_output)], capture_output=True, text=True,
            )
            if result.returncode == 0 or rejected_output.exists() or "Build failed:" not in result.stderr:
                raise ValueError(f"Build accepted {label} input")

        xray = download_tool("xray")
        config = {
            "log": {"loglevel": "warning"},
            "outbounds": [{"protocol": "freedom", "tag": "direct"}],
            "routing": {"rules": [{"type": "field", "domain": ["ext:geosite_line.dat:line"],
                                   "outboundTag": "direct"}]},
        }
        config_path = work / "xray.json"
        config_path.write_text(json.dumps(config))
        environment = {**os.environ, "XRAY_LOCATION_ASSET": str(output)}
        command = [str(xray), "run", "-test", "-config", str(config_path)]
        subprocess.run(command, env=environment, check=True)
        config["routing"]["rules"][0]["domain"] = ["ext:geosite_line.dat:missing-category"]
        config_path.write_text(json.dumps(config))
        if subprocess.run(command, env=environment, capture_output=True).returncode == 0:
            raise ValueError("Xray accepted a missing category; the smoke test is ineffective")
    print("Integration checks passed: reproducibility, domain boundaries, invalid inputs, Xray and Mihomo")


if __name__ == "__main__":
    main()
