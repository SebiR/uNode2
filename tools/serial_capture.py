from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from serial import Serial
from serial.tools import list_ports


def _list_ports() -> None:
    for port in list_ports.comports():
        details = []
        if port.description:
            details.append(port.description)
        if port.vid is not None and port.pid is not None:
            details.append(f"VID:PID={port.vid:04X}:{port.pid:04X}")
        if port.serial_number:
            details.append(f"SN={port.serial_number}")
        suffix = f" ({', '.join(details)})" if details else ""
        print(f"{port.device}{suffix}")


def _timestamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Capture uNode serial debug output with host timestamps."
    )
    parser.add_argument(
        "--port",
        help="Serial port, for example COM8 or /dev/ttyUSB0.",
    )
    parser.add_argument(
        "--baud",
        type=int,
        default=115200,
        help="Serial baud rate. Default: 115200.",
    )
    parser.add_argument(
        "--output",
        default="logs/unode-serial.log",
        help="Log file path. Default: logs/unode-serial.log.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available serial ports and exit.",
    )

    args = parser.parse_args()

    if args.list:
        _list_ports()
        return 0

    if not args.port:
        parser.error("--port is required unless --list is used")

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(
        f"Capturing {args.port} at {args.baud} baud -> {output_path}",
        flush=True,
    )
    print("Press Ctrl+C to stop.", flush=True)

    with Serial(args.port, args.baud, timeout=0.5) as serial_port:
        with output_path.open("a", encoding="utf-8", newline="") as logfile:
            logfile.write(f"\n--- capture started {_timestamp()} ---\n")
            logfile.flush()

            while True:
                raw = serial_port.readline()
                if not raw:
                    continue

                text = raw.decode("utf-8", errors="replace").rstrip("\r\n")
                line = f"{_timestamp()} {text}"
                print(line, flush=True)
                logfile.write(line + "\n")
                logfile.flush()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nCapture stopped.", file=sys.stderr)
        raise SystemExit(130)
