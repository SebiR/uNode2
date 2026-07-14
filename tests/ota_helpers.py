"""HTTP OTA helpers shared by safe and destructive uNode tests."""

from __future__ import annotations

import hashlib
import http.client
import json
import os
import secrets
import socket
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import urlencode, urlsplit


@dataclass(frozen=True)
class OtaResponse:
    """Result returned by one completed multipart OTA request."""

    status: int
    body: bytes
    content_type: str


@dataclass(frozen=True)
class ReleaseArtifacts:
    """Verified firmware/LittleFS pair selected from a release manifest."""

    version: str
    profile: str
    firmware: Path
    littlefs: Path
    firmware_sha256: str
    littlefs_sha256: str


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(64 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def resolve_release_artifacts(
    version: str,
    *,
    profile: str | None = None,
    artifacts_dir: str | os.PathLike[str] | None = None,
) -> ReleaseArtifacts:
    """Resolve and verify one release pair before OTA or serial flashing."""

    selected_profile = (
        profile or os.environ.get("UNODE_OTA_PROFILE", "normal")
    ).strip().lower()
    if selected_profile not in {"normal", "legacy"}:
        raise AssertionError(
            "UNODE_OTA_PROFILE must be either 'normal' or 'legacy'"
        )

    root = Path(
        artifacts_dir
        or os.environ.get("UNODE_OTA_ARTIFACTS_DIR", "artifacts/release")
    ).resolve()
    manifest_path = root / f"uNode-{version}-manifest.json"
    if not manifest_path.is_file():
        raise AssertionError(f"Release manifest is missing: {manifest_path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    if str(manifest.get("version", "")) != version:
        raise AssertionError(
            f"Release manifest version does not match running firmware {version}"
        )

    profile_data = manifest.get("profiles", {}).get(selected_profile)
    if not isinstance(profile_data, dict):
        raise AssertionError(
            f"Release manifest has no {selected_profile!r} profile"
        )

    firmware_data = profile_data.get("firmware", {})
    littlefs_data = profile_data.get("littleFs", {})
    firmware = root / str(firmware_data.get("file", ""))
    littlefs = root / str(littlefs_data.get("file", ""))

    for label, path, metadata in (
        ("firmware", firmware, firmware_data),
        ("LittleFS", littlefs, littlefs_data),
    ):
        if not path.is_file():
            raise AssertionError(f"Release {label} artifact is missing: {path}")
        expected_size = int(metadata.get("size", -1))
        if path.stat().st_size != expected_size:
            raise AssertionError(
                f"Release {label} size mismatch: "
                f"{path.stat().st_size} != {expected_size}"
            )
        expected_hash = str(metadata.get("sha256", "")).upper()
        actual_hash = _sha256(path)
        if not expected_hash or actual_hash != expected_hash:
            raise AssertionError(
                f"Release {label} SHA-256 mismatch: "
                f"{actual_hash} != {expected_hash}"
            )

    return ReleaseArtifacts(
        version=version,
        profile=selected_profile,
        firmware=firmware,
        littlefs=littlefs,
        firmware_sha256=str(firmware_data["sha256"]).upper(),
        littlefs_sha256=str(littlefs_data["sha256"]).upper(),
    )


def build_multipart_body(
    payload: bytes,
    *,
    filename: str,
    boundary: str,
) -> bytes:
    """Build the same single-file multipart body used by the recovery page."""

    prefix = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        "Content-Type: application/octet-stream\r\n\r\n"
    ).encode("ascii")
    suffix = f"\r\n--{boundary}--\r\n".encode("ascii")
    return prefix + payload + suffix


def _connection(
    base_url: str,
    timeout: float,
) -> tuple[http.client.HTTPConnection, str]:
    parsed = urlsplit(base_url.rstrip("/"))
    if parsed.scheme != "http" or not parsed.hostname:
        raise AssertionError(f"OTA tests require a plain HTTP base URL: {base_url}")
    connection = http.client.HTTPConnection(
        parsed.hostname,
        parsed.port or 80,
        timeout=timeout,
    )
    return connection, parsed.path.rstrip("/")


def upload_bytes(
    base_url: str,
    endpoint: str,
    payload: bytes,
    *,
    declared_size: int | str | None,
    filename: str = "test.bin",
    token: str = "",
    timeout: float = 30.0,
) -> OtaResponse:
    """Complete one multipart upload and return its HTTP result."""

    boundary = "----uNodeTest" + secrets.token_hex(12)
    prefix_body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        "Content-Type: application/octet-stream\r\n\r\n"
    ).encode("ascii")
    suffix_body = f"\r\n--{boundary}--\r\n".encode("ascii")
    content_length = len(prefix_body) + len(payload) + len(suffix_body)
    query = ""
    if declared_size is not None:
        query = "?" + urlencode({"size": declared_size})

    connection, prefix = _connection(base_url, timeout)
    try:
        connection.putrequest("POST", prefix + endpoint + query)
        connection.putheader(
            "Content-Type",
            f"multipart/form-data; boundary={boundary}",
        )
        connection.putheader("Content-Length", str(content_length))
        connection.putheader("Connection", "close")
        if token:
            connection.putheader("X-uNode-Auth", token)
        connection.endheaders()

        # ESP8266 flash writes periodically close the receive window. Sending
        # one megabyte through a single socket.sendall() can therefore hit the
        # host timeout even though the updater is making progress. Small sends
        # follow the same back-pressure-friendly behaviour as curl/browser
        # multipart uploads.
        connection.send(prefix_body)
        for offset in range(0, len(payload), 4096):
            connection.send(payload[offset : offset + 4096])
        connection.send(suffix_body)

        response = connection.getresponse()
        return OtaResponse(
            status=response.status,
            body=response.read(),
            content_type=response.getheader("Content-Type", ""),
        )
    finally:
        connection.close()


def upload_file(
    base_url: str,
    endpoint: str,
    path: Path,
    *,
    token: str = "",
    timeout: float = 90.0,
) -> OtaResponse:
    """Upload one complete, already-verified release artifact."""

    payload = path.read_bytes()
    return upload_bytes(
        base_url,
        endpoint,
        payload,
        declared_size=len(payload),
        filename=path.name,
        token=token,
        timeout=timeout,
    )


def interrupt_upload(
    base_url: str,
    endpoint: str,
    payload: bytes,
    *,
    declared_size: int,
    interrupt_after: int,
    interrupt: Callable[[], None],
    filename: str,
    token: str = "",
    chunk_size: int = 4096,
    chunk_delay: float = 0.025,
) -> int:
    """Reset the target after a controlled amount of a throttled upload.

    The request advertises the complete multipart Content-Length but closes
    immediately after invoking ``interrupt``. Throttling keeps the host TCP
    buffers from racing far ahead of the ESP8266 flash writer.
    """

    if interrupt_after <= 0 or interrupt_after >= len(payload):
        raise ValueError("interrupt_after must be inside the payload")

    boundary = "----uNodeInterrupt" + secrets.token_hex(12)
    prefix = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        "Content-Type: application/octet-stream\r\n\r\n"
    ).encode("ascii")
    suffix = f"\r\n--{boundary}--\r\n".encode("ascii")
    content_length = len(prefix) + len(payload) + len(suffix)

    connection, path_prefix = _connection(base_url, 10.0)
    request_path = (
        path_prefix
        + endpoint
        + "?"
        + urlencode({"size": declared_size})
    )

    sent = 0
    reset_invoked = False
    try:
        connection.putrequest("POST", request_path)
        connection.putheader(
            "Content-Type",
            f"multipart/form-data; boundary={boundary}",
        )
        connection.putheader("Content-Length", str(content_length))
        connection.putheader("Connection", "close")
        if token:
            connection.putheader("X-uNode-Auth", token)
        connection.endheaders()
        connection.send(prefix)

        while sent < interrupt_after:
            end = min(sent + chunk_size, interrupt_after)
            connection.send(payload[sent:end])
            sent = end
            time.sleep(chunk_delay)

        # Give the final TCP chunk a chance to reach Update.write() before the
        # external reset line is asserted.
        time.sleep(0.1)
        interrupt()
        reset_invoked = True
    except (
        BrokenPipeError,
        ConnectionResetError,
        http.client.HTTPException,
        socket.timeout,
    ):
        # A transport failure is expected around an interrupted request. The
        # finally block still guarantees the external reset if it occurred
        # before the planned callback point.
        pass
    finally:
        if not reset_invoked:
            interrupt()
        connection.close()

    return sent
