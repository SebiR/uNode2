from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from ota_helpers import build_multipart_body, resolve_release_artifacts


def test_build_multipart_body_contains_one_named_file() -> None:
    body = build_multipart_body(
        b"\x01\x02\x03",
        filename="firmware.bin",
        boundary="test-boundary",
    )

    assert body.startswith(b"--test-boundary\r\n")
    assert b'name="file"; filename="firmware.bin"' in body
    assert b"Content-Type: application/octet-stream\r\n\r\n\x01\x02\x03" in body
    assert body.endswith(b"\r\n--test-boundary--\r\n")


def test_resolve_release_artifacts_verifies_manifest_hashes(tmp_path: Path) -> None:
    firmware = tmp_path / "uNode-1.2.3-firmware.bin"
    littlefs = tmp_path / "uNode-1.2.3-littlefs.bin"
    firmware.write_bytes(b"firmware")
    littlefs.write_bytes(b"littlefs")

    def digest(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest().upper()

    manifest = {
        "version": "1.2.3",
        "profiles": {
            "normal": {
                "firmware": {
                    "file": firmware.name,
                    "size": firmware.stat().st_size,
                    "sha256": digest(firmware),
                },
                "littleFs": {
                    "file": littlefs.name,
                    "size": littlefs.stat().st_size,
                    "sha256": digest(littlefs),
                },
            },
            "gpio_fix": {
                "firmware": {
                    "file": firmware.name,
                    "size": firmware.stat().st_size,
                    "sha256": digest(firmware),
                },
                "littleFs": {
                    "file": littlefs.name,
                    "size": littlefs.stat().st_size,
                    "sha256": digest(littlefs),
                },
            },
        },
    }
    (tmp_path / "uNode-1.2.3-manifest.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )

    artifacts = resolve_release_artifacts(
        "1.2.3",
        artifacts_dir=tmp_path,
    )

    assert artifacts.firmware == firmware
    assert artifacts.littlefs == littlefs
    assert artifacts.profile == "normal"

    gpio_fix_artifacts = resolve_release_artifacts(
        "1.2.3",
        profile="gpio_fix",
        artifacts_dir=tmp_path,
    )

    assert gpio_fix_artifacts.firmware == firmware
    assert gpio_fix_artifacts.littlefs == littlefs
    assert gpio_fix_artifacts.profile == "gpio_fix"


def test_resolve_release_artifacts_rejects_modified_binary(tmp_path: Path) -> None:
    firmware = tmp_path / "fw.bin"
    littlefs = tmp_path / "fs.bin"
    firmware.write_bytes(b"modified")
    littlefs.write_bytes(b"fs")
    manifest = {
        "version": "1.0.0",
        "profiles": {
            "normal": {
                "firmware": {
                    "file": firmware.name,
                    "size": firmware.stat().st_size,
                    "sha256": "00" * 32,
                },
                "littleFs": {
                    "file": littlefs.name,
                    "size": littlefs.stat().st_size,
                    "sha256": hashlib.sha256(littlefs.read_bytes()).hexdigest(),
                },
            }
        },
    }
    (tmp_path / "uNode-1.0.0-manifest.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )

    with pytest.raises(AssertionError, match="SHA-256 mismatch"):
        resolve_release_artifacts("1.0.0", artifacts_dir=tmp_path)
