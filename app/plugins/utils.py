from __future__ import annotations

import re
import ipaddress
import socket
from pathlib import Path
from urllib.parse import urlparse

from config import DATA_DIR

ARTIFACTS_DIR = DATA_DIR / "artifacts"
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)


def safe_filename(value: str, default: str, extension: str) -> str:
    name = Path(value or default).name
    stem = Path(name).stem
    stem = re.sub(r"[^A-Za-z0-9._ -]+", "_", stem).strip(" ._") or Path(default).stem
    return f"{stem[:100]}.{extension.lstrip('.')}"


def artifact_path(value: str, default: str, extension: str) -> Path:
    path = (ARTIFACTS_DIR / safe_filename(value, default, extension)).resolve()
    if ARTIFACTS_DIR.resolve() not in path.parents:
        raise ValueError("Invalid artifact path")
    return path


def approved_path(value: str) -> Path:
    path = Path(value).expanduser().resolve()
    roots = [DATA_DIR.resolve(), ARTIFACTS_DIR.resolve()]
    if not any(path == root or root in path.parents for root in roots):
        raise ValueError("File access is restricted to the assistant data directory")
    return path


def validate_public_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Only public HTTP(S) URLs are allowed")
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))}
    except socket.gaierror as exc:
        raise ValueError("The URL hostname could not be resolved") from exc
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if not ip.is_global:
            raise ValueError("Local and private network addresses are not allowed")
    return value
