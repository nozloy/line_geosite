"""One domain source for Xray GeoSite and sing-box rule-sets."""

import json
import re
from pathlib import Path

SRS_VERSION = 2  # Supported since sing-box 1.10.0.
DOMAIN_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z")


def read_domains(source: Path) -> list[str]:
    domains: set[str] = set()
    for number, raw in enumerate(source.read_text(encoding="utf-8").splitlines(), 1):
        rule = raw.split("#", 1)[0].strip()
        if not rule:
            continue
        prefix, separator, domain = rule.partition(":")
        labels = domain.split(".")
        if (
            prefix != "domain"
            or not separator
            or len(domain) > 253
            or len(labels) < 2
            or labels[-1].isdigit()
            or any(not DOMAIN_LABEL.fullmatch(label) for label in labels)
        ):
            raise ValueError(f"{source}:{number}: expected domain:lowercase.example")
        if domain in domains:
            raise ValueError(f"{source}:{number}: duplicate domain {domain}")
        domains.add(domain)
    if not domains:
        raise ValueError(f"{source}: the domain list must not be empty")
    for domain in domains:
        labels = domain.split(".")
        if any(".".join(labels[index:]) in domains for index in range(1, len(labels))):
            raise ValueError(f"{source}: {domain} is already covered by its parent domain")
    return sorted(domains)


def source_rules(domains: list[str]) -> dict:
    return {"version": SRS_VERSION, "rules": [{"domain_suffix": domains}]}


def verify_dat_dump(path: Path, domains: list[str]) -> None:
    # Read only the documented, fixed output of the pinned upstream datdump.
    # Requiring the complete header also rejects additional categories.
    lines = path.read_text(encoding="utf-8").splitlines()
    expected_header = [
        "lists:", '  - name: "line"', f"    length: {len(domains)}", "    rules:"
    ]
    if lines[:4] != expected_header:
        raise ValueError("DAT must contain exactly the non-empty category line")
    prefix = "      - "
    if any(not line.startswith(prefix) for line in lines[4:]):
        raise ValueError("DAT contains unexpected categories or rules")
    actual = sorted(json.loads(line[len(prefix):]) for line in lines[4:])
    if actual != [f"domain:{domain}" for domain in domains]:
        raise ValueError("DAT domain rules differ from the source list")


def verify_srs_dump(path: Path, domains: list[str]) -> None:
    actual = json.loads(path.read_text(encoding="utf-8"))
    if actual.get("version") != SRS_VERSION or len(actual.get("rules", [])) != 1:
        raise ValueError("SRS must contain one rule in format version 2")
    rule = actual["rules"][0]
    if set(rule) != {"domain_suffix"} or sorted(rule["domain_suffix"]) != domains:
        raise ValueError("SRS domain_suffix rules differ from the source list")
