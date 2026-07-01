"""USB-serial client for the RP2040 DMX tool JSONL protocol."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

import serial


@dataclass
class Rp2040DmxTool:
    port: str
    baudrate: int = 115200
    timeout: float = 1.0

    def __post_init__(self) -> None:
        self.serial = serial.Serial(
            self.port,
            self.baudrate,
            timeout=self.timeout,
            write_timeout=self.timeout,
        )
        # Give USB serial a short moment to settle, then discard stale terminal
        # output from previous manual sessions.
        time.sleep(0.2)
        self.serial.reset_input_buffer()

    def close(self) -> None:
        if self.serial.is_open:
            self.serial.close()

    def __enter__(self) -> "Rp2040DmxTool":
        return self

    def __exit__(self, *_args: object) -> None:
        try:
            self.idle()
        finally:
            self.close()

    def command(
        self,
        payload: dict[str, Any],
        *,
        timeout: float = 2.0,
    ) -> dict[str, Any]:
        line = json.dumps(payload, separators=(",", ":")).encode("utf-8") + b"\n"
        self.serial.write(line)
        self.serial.flush()
        return self._read_json_response(timeout=timeout)

    def send_command_no_wait(self, payload: dict[str, Any]) -> None:
        line = json.dumps(payload, separators=(",", ":")).encode("utf-8") + b"\n"
        self.serial.write(line)
        self.serial.flush()

    def read_response(self, *, timeout: float = 2.0) -> dict[str, Any]:
        return self._read_json_response(timeout=timeout)

    def _read_json_response(self, *, timeout: float) -> dict[str, Any]:
        deadline = time.time() + timeout
        last_line = b""

        while time.time() < deadline:
            line = self.serial.readline()
            if not line:
                continue

            last_line = line.strip()
            if not last_line.startswith(b"{"):
                continue

            try:
                decoded = json.loads(last_line.decode("utf-8"))
            except json.JSONDecodeError:
                continue

            if decoded.get("event") == "ready":
                continue

            if decoded.get("ok") is False:
                raise AssertionError(f"RP2040 command failed: {decoded}")

            return decoded

        raise AssertionError(f"Timed out waiting for RP2040 JSON response; last={last_line!r}")

    def ping(self) -> dict[str, Any]:
        return self.command({"cmd": "ping"})

    def help(self) -> dict[str, Any]:
        return self.command({"cmd": "help"})

    def gpio_read(self, pin: int) -> dict[str, Any]:
        return self.command({"cmd": "gpio", "action": "read", "pin": pin})

    def gpio_input(self, pin: int, *, pullup: bool = False) -> dict[str, Any]:
        return self.command(
            {
                "cmd": "gpio",
                "action": "input",
                "pin": pin,
                "pullup": pullup,
            }
        )

    def gpio_write(self, pin: int, value: int | bool) -> dict[str, Any]:
        return self.command(
            {
                "cmd": "gpio",
                "action": "write",
                "pin": pin,
                "value": 1 if bool(value) else 0,
            }
        )

    def gpio_pulse(
        self,
        pin: int,
        *,
        value: int | bool,
        duration_ms: int = 250,
        release: bool = True,
    ) -> dict[str, Any]:
        return self.command(
            {
                "cmd": "gpio",
                "action": "pulse",
                "pin": pin,
                "value": 1 if bool(value) else 0,
                "durationMs": duration_ms,
                "release": release,
            },
            timeout=max(2.0, duration_ms / 1000.0 + 1.0),
        )

    def gpio_release(self, pin: int) -> dict[str, Any]:
        return self.command({"cmd": "gpio", "action": "release", "pin": pin})

    def mode(self, value: str) -> dict[str, Any]:
        return self.command({"cmd": "mode", "value": value})

    def idle(self) -> dict[str, Any]:
        return self.mode("idle")

    def clear_stats(self) -> dict[str, Any]:
        return self.command({"cmd": "clear", "target": "stats"})

    def get_stats(self) -> dict[str, Any]:
        return self.command({"cmd": "get", "target": "stats"})

    def get_frame(self, *, start: int = 1, count: int = 16) -> dict[str, Any]:
        return self.command(
            {
                "cmd": "get",
                "target": "frame",
                "start": start,
                "count": count,
            }
        )

    def set_frame(self, values: list[int], *, slots: int | None = None) -> dict[str, Any]:
        return self.command(
            {
                "cmd": "set",
                "target": "frame",
                "slots": len(values) if slots is None else slots,
                "values": values,
            }
        )

    def wait_frame(
        self,
        values: list[int],
        *,
        start: int = 1,
        timeout_ms: int = 1500,
    ) -> dict[str, Any]:
        return self.command(
            {
                "cmd": "wait",
                "target": "frame",
                "start": start,
                "count": len(values),
                "values": values,
                "timeoutMs": timeout_ms,
            },
            timeout=max(2.0, timeout_ms / 1000.0 + 1.0),
        )

    def begin_wait_frame(
        self,
        values: list[int],
        *,
        start: int = 1,
        timeout_ms: int = 1500,
    ) -> None:
        self.send_command_no_wait(
            {
                "cmd": "wait",
                "target": "frame",
                "start": start,
                "count": len(values),
                "values": values,
                "timeoutMs": timeout_ms,
            }
        )

    def finish_wait_frame(self, *, timeout_ms: int = 1500) -> dict[str, Any]:
        return self.read_response(timeout=max(2.0, timeout_ms / 1000.0 + 1.0))

    def set_timing(
        self,
        *,
        break_us: int = 176,
        mab_us: int = 16,
        fps: int = 40,
        inter_slot_us: int = 0,
        mbb_us: int = 0,
        baud: int = 250000,
    ) -> dict[str, Any]:
        return self.command(
            {
                "cmd": "set",
                "target": "timing",
                "breakUs": break_us,
                "mabUs": mab_us,
                "fps": fps,
                "interSlotUs": inter_slot_us,
                "mbbUs": mbb_us,
                "baud": baud,
            }
        )

    def tx(self, action: str) -> dict[str, Any]:
        return self.command({"cmd": "tx", "action": action})

    def noise(
        self,
        *,
        duration_ms: int = 100,
        min_pulse_us: int = 2,
        max_pulse_us: int = 200,
    ) -> dict[str, Any]:
        return self.command(
            {
                "cmd": "noise",
                "durationMs": duration_ms,
                "minPulseUs": min_pulse_us,
                "maxPulseUs": max_pulse_us,
            },
            timeout=max(2.0, duration_ms / 1000.0 + 1.0),
        )
