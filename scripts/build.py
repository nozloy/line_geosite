#!/usr/bin/env python3
"""Build and verify all formats before exposing any release artifacts."""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from domain_rules import read_domains, source_rules, verify_dat_dump, verify_srs_dump, verify_mrs_dump
from pinned_tools import ROOT, TOOLCHAINS, download_tool, sha256


def build(source: Path, output: Path) -> None:
    domains = read_domains(source)
    go_version = (ROOT / ".go-version").read_text().strip()
    environment = {**os.environ, "GOTOOLCHAIN": "local"}
    actual_go = subprocess.check_output(["go", "env", "GOVERSION"], env=environment, text=True).strip()
    if actual_go != f"go{go_version}":
        raise ValueError(f"Use Go {go_version}; found {actual_go}")

    cache = ROOT / ".cache"
    cache.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="build-", dir=cache) as directory:
        work = Path(directory)
        input_dir = work / "data"
        input_dir.mkdir()
        # A validated snapshot guarantees that all formats use identical input.
        (input_dir / "line").write_text("".join(f"domain:{d}\n" for d in domains))
        rules_json = work / "line.json"
        rules_json.write_text(json.dumps(source_rules(domains), indent=2) + "\n")
        revision = TOOLCHAINS["domain_list_commit"]
        module = "github.com/v2fly/domain-list-community"
        subprocess.run(
            ["go", "run", f"{module}@{revision}", f"--datapath={input_dir}",
             f"--outputdir={work}", "--outputname=geosite_line.dat"],
            env=environment, check=True,
        )
        subprocess.run(
            ["go", "run", f"{module}/cmd/datdump@{revision}",
             f"--inputdata={work / 'geosite_line.dat'}", f"--outputdir={work}"],
            env=environment, check=True,
        )
        verify_dat_dump(work / "geosite_line.dat_plain.yml", domains)

        sing_box = str(download_tool("sing-box"))
        srs = work / "geosite_line.srs"
        subprocess.run([sing_box, "rule-set", "compile", "--output", str(srs), str(rules_json)], check=True)
        if srs.read_bytes()[:4] != b"SRS\x02":
            raise ValueError("Compiler did not produce SRS version 2")
        decoded = work / "decoded.json"
        subprocess.run([sing_box, "rule-set", "decompile", "--output", str(decoded), str(srs)], check=True)
        verify_srs_dump(decoded, domains)

        mihomo = str(download_tool("mihomo"))
        domain_text = work / "line.txt"
        domain_text.write_text("".join(f"+.{domain}\n" for domain in domains))
        mrs = work / "geosite_line.mrs"
        subprocess.run([mihomo, "convert-ruleset", "domain", "text", str(domain_text), str(mrs)], check=True)
        decoded_mrs = work / "decoded-mrs.txt"
        subprocess.run([mihomo, "convert-ruleset", "domain", "mrs", str(mrs), str(decoded_mrs)], check=True)
        verify_mrs_dump(decoded_mrs, domains)

        for extension in ("dat", "srs", "mrs"):
            artifact = work / f"geosite_line.{extension}"
            if not artifact.stat().st_size:
                raise ValueError(f"Empty artifact: {artifact.name}")
            (work / f"{artifact.name}.sha256sum").write_text(f"{sha256(artifact)}  {artifact.name}\n")
        output.mkdir(parents=True, exist_ok=True)
        for extension in ("dat", "srs", "mrs"):
            for suffix in ("", ".sha256sum"):
                name = f"geosite_line.{extension}{suffix}"
                shutil.copyfile(work / name, output / name)
    print(f"Verified {len(domains)} domains in DAT, SRS and MRS: {output}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "data" / "line")
    parser.add_argument("--output", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    try:
        build(args.source.resolve(), args.output.resolve())
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"Build failed: {error}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
