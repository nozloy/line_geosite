"""Download official CLI archives with pinned versions and SHA-256 digests."""

import hashlib
import json
import platform
import shutil
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLCHAINS = json.loads((ROOT / "toolchains.json").read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def download_tool(name: str) -> Path:
    tool = TOOLCHAINS[name]
    host = f"{platform.system()}-{platform.machine()}"
    if host not in tool["assets"]:
        raise ValueError(f"Unsupported build host {host}; use Linux x86_64 or macOS arm64")
    asset = tool["assets"][host]
    cache = ROOT / ".cache" / "tools" / name / tool["version"] / host
    cache.mkdir(parents=True, exist_ok=True)
    archive = cache / asset["name"]
    if not archive.exists():
        url = (
            f"https://github.com/{tool['repository']}/releases/download/"
            f"v{tool['version']}/{asset['name']}"
        )
        print(f"Downloading {name} {tool['version']} for {host}", file=sys.stderr)
        pending = archive.with_suffix(archive.suffix + ".part")
        try:
            with urllib.request.urlopen(url, timeout=60) as response, pending.open("wb") as target:
                shutil.copyfileobj(response, target)
            if sha256(pending) != asset["sha256"]:
                raise ValueError(f"SHA-256 mismatch for {asset['name']}")
            pending.replace(archive)
        finally:
            pending.unlink(missing_ok=True)
    if sha256(archive) != asset["sha256"]:
        raise ValueError(f"Cached archive checksum mismatch: remove {archive} and retry")

    # Extract only the executable; archive paths never become destination paths.
    executable = cache / tool["binary"]
    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as bundle:
            members = [entry for entry in bundle.infolist() if Path(entry.filename).name == tool["binary"]]
            if len(members) != 1 or members[0].is_dir():
                raise ValueError(f"Unexpected executable in {archive}")
            executable.write_bytes(bundle.read(members[0]))
    else:
        with tarfile.open(archive) as bundle:
            members = [entry for entry in bundle.getmembers() if Path(entry.name).name == tool["binary"]]
            if len(members) != 1 or not members[0].isfile():
                raise ValueError(f"Unexpected executable in {archive}")
            with bundle.extractfile(members[0]) as source, executable.open("wb") as target:
                shutil.copyfileobj(source, target)
    executable.chmod(0o755)
    return executable
