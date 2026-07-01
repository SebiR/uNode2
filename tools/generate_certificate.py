from __future__ import annotations

import argparse
import base64
import json
import shutil
import subprocess
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from jinja2 import Template


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT_DIR = PROJECT_ROOT / "artifacts" / "test_reports"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "artifacts" / "certificates"
LOGO_PATH = PROJECT_ROOT / "firmware" / "uNode_2" / "data" / "images" / "logo.png"


HTML_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>uNode Production Test Certificate {{ certificate_id }}</title>
  <style>
    @page {
      size: A4;
      margin: 16mm 14mm;
    }

    :root {
      --ink: #172033;
      --muted: #667085;
      --line: #d8dee9;
      --panel: #f7f9fc;
      --blue: #195b8f;
      --green: #12805c;
      --red: #c62828;
      --amber: #a86400;
    }

    * {
      box-sizing: border-box;
    }

    body {
      margin: 0;
      color: var(--ink);
      font: 11px/1.42 "Segoe UI", Arial, sans-serif;
      background: white;
    }

    .hero {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 18px;
      align-items: start;
      padding-bottom: 15px;
      border-bottom: 2px solid var(--blue);
    }

    .brand {
      display: flex;
      gap: 14px;
      align-items: center;
    }

    .logo-box {
      width: 54px;
      height: 54px;
      display: grid;
      place-items: center;
      border-radius: 14px;
      background: linear-gradient(135deg, #0d2946, #195b8f);
      overflow: hidden;
    }

    .logo-box img {
      max-width: 46px;
      max-height: 46px;
    }

    h1 {
      margin: 0;
      font-size: 24px;
      letter-spacing: -0.4px;
    }

    .subtitle {
      margin-top: 2px;
      color: var(--muted);
      font-size: 12px;
    }

    .result {
      min-width: 112px;
      padding: 12px 15px;
      border-radius: 14px;
      text-align: center;
      color: white;
      background: {{ result_color }};
      box-shadow: 0 8px 20px rgb(0 0 0 / 12%);
    }

    .result .label {
      font-size: 10px;
      opacity: 0.85;
      text-transform: uppercase;
      letter-spacing: 1px;
    }

    .result .value {
      margin-top: 2px;
      font-size: 28px;
      font-weight: 800;
      letter-spacing: 1px;
    }

    .grid {
      display: grid;
      grid-template-columns: 1.25fr 1fr;
      gap: 12px;
      margin-top: 14px;
    }

    .card {
      border: 1px solid var(--line);
      border-radius: 12px;
      background: var(--panel);
      padding: 12px;
      break-inside: avoid;
    }

    .card h2,
    .section h2 {
      margin: 0 0 9px;
      font-size: 13px;
      color: var(--blue);
      text-transform: uppercase;
      letter-spacing: 0.7px;
    }

    .kv {
      display: grid;
      grid-template-columns: 112px 1fr;
      gap: 4px 10px;
    }

    .kv .key {
      color: var(--muted);
    }

    .kv .value {
      font-weight: 600;
      overflow-wrap: anywhere;
    }

    .summary {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 8px;
    }

    .metric {
      padding: 9px;
      border-radius: 10px;
      background: white;
      border: 1px solid var(--line);
      text-align: center;
    }

    .metric .number {
      font-size: 19px;
      font-weight: 800;
    }

    .metric .caption {
      color: var(--muted);
      text-transform: uppercase;
      font-size: 9px;
      letter-spacing: 0.6px;
    }

    .section {
      margin-top: 14px;
    }

    .group {
      margin-top: 10px;
      border: 1px solid var(--line);
      border-radius: 12px;
      overflow: hidden;
      break-inside: avoid;
    }

    .group-head {
      display: grid;
      grid-template-columns: 1fr auto;
      align-items: center;
      padding: 9px 11px;
      background: #edf3f9;
      border-bottom: 1px solid var(--line);
    }

    .group-title {
      font-weight: 800;
      font-size: 12px;
      color: #123a5c;
    }

    .group-count {
      color: var(--muted);
      font-size: 10px;
    }

    table {
      width: 100%;
      border-collapse: collapse;
      background: white;
    }

    th,
    td {
      padding: 6px 8px;
      border-bottom: 1px solid #edf0f5;
      vertical-align: top;
    }

    th {
      color: var(--muted);
      font-weight: 700;
      text-align: left;
      font-size: 9px;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }

    tr:last-child td {
      border-bottom: 0;
    }

    .status {
      display: inline-block;
      min-width: 50px;
      padding: 2px 6px;
      border-radius: 999px;
      color: white;
      text-align: center;
      font-size: 9px;
      font-weight: 800;
      letter-spacing: 0.4px;
    }

    .status.PASSED {
      background: var(--green);
    }

    .status.FAILED {
      background: var(--red);
    }

    .status.SKIPPED {
      background: var(--amber);
    }

    .desc {
      color: var(--muted);
      margin-top: 1px;
      font-size: 10px;
    }

    .measurements {
      margin-top: 6px;
      border: 1px solid #e6ebf2;
      border-radius: 8px;
      overflow: hidden;
      background: #fbfcfe;
    }

    .measurements table {
      background: transparent;
    }

    .measurements th,
    .measurements td {
      padding: 4px 6px;
      font-size: 9px;
    }

    .measurements .measurement-name {
      font-weight: 700;
      color: #26374f;
    }

    .duration {
      white-space: nowrap;
      color: var(--muted);
      text-align: right;
    }

    .footer {
      margin-top: 18px;
      padding-top: 9px;
      border-top: 1px solid var(--line);
      color: var(--muted);
      font-size: 9px;
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 8px;
    }
  </style>
</head>
<body>
  <div class="hero">
    <div class="brand">
      <div class="logo-box">
        {% if logo_data_uri %}
        <img src="{{ logo_data_uri }}" alt="uNode">
        {% else %}
        <strong>µN</strong>
        {% endif %}
      </div>
      <div>
        <h1>uNode Production Test Certificate</h1>
        <div class="subtitle">Generated from automated regression and hardware-in-the-loop test data</div>
      </div>
    </div>
    <div class="result">
      <div class="label">Result</div>
      <div class="value">{{ summary.result }}</div>
    </div>
  </div>

  <div class="grid">
    <div class="card">
      <h2>Device</h2>
      <div class="kv">
        <div class="key">Node Name</div><div class="value">{{ node.name or "N/A" }}</div>
        <div class="key">Chip ID</div><div class="value">{{ node.chipId or "N/A" }}</div>
        <div class="key">MAC</div><div class="value">{{ node.mac or "N/A" }}</div>
        <div class="key">Firmware</div><div class="value">{{ node.firmware or "N/A" }}</div>
        <div class="key">IP</div><div class="value">{{ node.ip or "N/A" }}</div>
        <div class="key">Boot Count</div><div class="value">{{ node.bootCount if node.bootCount is not none else "N/A" }}</div>
        <div class="key">Reset Reason</div><div class="value">{{ node.resetReason or "N/A" }}</div>
      </div>
    </div>

    <div class="card">
      <h2>Test Run</h2>
      <div class="kv">
        <div class="key">Certificate ID</div><div class="value">{{ certificate_id }}</div>
        <div class="key">Started</div><div class="value">{{ started_local }}</div>
        <div class="key">Finished</div><div class="value">{{ finished_local }}</div>
        <div class="key">Duration</div><div class="value">{{ duration_text }}</div>
        <div class="key">RP2040</div><div class="value">{{ environment.rp2040Port or "N/A" }}</div>
        <div class="key">Base URL</div><div class="value">{{ environment.baseUrl or "N/A" }}</div>
      </div>
    </div>
  </div>

  <div class="card" style="margin-top: 12px;">
    <h2>Summary</h2>
    <div class="summary">
      <div class="metric"><div class="number">{{ summary.total }}</div><div class="caption">Total</div></div>
      <div class="metric"><div class="number">{{ summary.passed }}</div><div class="caption">Passed</div></div>
      <div class="metric"><div class="number">{{ summary.failed }}</div><div class="caption">Failed</div></div>
      <div class="metric"><div class="number">{{ summary.skipped }}</div><div class="caption">Skipped</div></div>
    </div>
  </div>

  <div class="section">
    <h2>Test Results</h2>
    {% for group_name, group_tests in grouped_tests %}
    <div class="group">
      <div class="group-head">
        <div class="group-title">{{ group_name }}</div>
        <div class="group-count">{{ group_tests|length }} test{{ "" if group_tests|length == 1 else "s" }}</div>
      </div>
      <table>
        <thead>
          <tr>
            <th style="width: 68px;">Status</th>
            <th>Check</th>
            <th style="width: 70px; text-align: right;">Duration</th>
          </tr>
        </thead>
        <tbody>
          {% for test in group_tests %}
          <tr>
            <td><span class="status {{ test.status }}">{{ test.status }}</span></td>
            <td>
              <strong>{{ test.title }}</strong>
              {% if test.description %}<div class="desc">{{ test.description }}</div>{% endif %}
              {% if test.measurements %}
              <div class="measurements">
                <table>
                  <thead>
                    <tr>
                      <th>Measurement</th>
                      <th>Min</th>
                      <th>Avg / Actual</th>
                      <th>Max</th>
                      <th>Allowed / Nominal</th>
                    </tr>
                  </thead>
                  <tbody>
                    {% for measurement in test.measurements %}
                    <tr>
                      <td class="measurement-name">{{ measurement.name }}</td>
                      <td>{{ measurement.min }}</td>
                      <td>{{ measurement.avg }}</td>
                      <td>{{ measurement.max }}</td>
                      <td>{{ measurement.target }}</td>
                    </tr>
                    {% endfor %}
                  </tbody>
                </table>
              </div>
              {% endif %}
            </td>
            <td class="duration">{{ "%.2f"|format(test.durationSeconds) }} s</td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
    {% endfor %}
  </div>

  <div class="footer">
    <div>Generated by uNode test tooling from JSON report {{ source_name }}.</div>
    <div>{{ generated_at }}</div>
  </div>
</body>
</html>
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate an HTML/PDF uNode production certificate from a JSON test report."
    )
    parser.add_argument(
        "report",
        nargs="?",
        type=Path,
        help="Path to a uNode JSON test report. Defaults to the newest report.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for generated certificate files.",
    )
    parser.add_argument(
        "--html-only",
        action="store_true",
        help="Generate only HTML and skip PDF rendering.",
    )
    parser.add_argument(
        "--browser",
        type=Path,
        default=None,
        help="Path to Chrome/Edge executable for PDF rendering.",
    )
    return parser.parse_args()


def newest_report() -> Path:
    reports = sorted(
        DEFAULT_REPORT_DIR.glob("*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not reports:
        raise FileNotFoundError(f"No JSON reports found in {DEFAULT_REPORT_DIR}")
    return reports[0]


def read_report(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def file_data_uri(path: Path) -> str:
    if not path.exists():
        return ""
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def safe_filename_part(value: object) -> str:
    text = str(value or "").strip()
    safe = "".join(char if char.isalnum() or char in "._-" else "-" for char in text)
    return safe.strip("-._")


def format_duration(seconds: float) -> str:
    seconds = max(0, float(seconds or 0))
    minutes, remainder = divmod(round(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes}m {remainder}s"
    if minutes:
        return f"{minutes}m {remainder}s"
    return f"{remainder}s"


def format_number(value: object, decimals: int = 1) -> str:
    if value is None:
        return "—"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    return f"{number:.{decimals}f}"


def format_with_unit(value: object, unit: str, decimals: int = 1) -> str:
    formatted = format_number(value, decimals)
    return formatted if formatted == "—" or not unit else f"{formatted} {unit}"


def format_target(metric: dict[str, Any]) -> str:
    unit = metric.get("unit", "")
    minimum = metric.get("minimum")
    maximum = metric.get("maximum")
    nominal = metric.get("nominal")
    parts: list[str] = []

    if minimum is not None and maximum is not None:
        parts.append(
            f"{format_with_unit(minimum, unit, 0)}.."
            f"{format_with_unit(maximum, unit, 0)}"
        )
    elif minimum is not None:
        parts.append(f">= {format_with_unit(minimum, unit, 0)}")
    elif maximum is not None:
        parts.append(f"<= {format_with_unit(maximum, unit, 0)}")

    if nominal is not None:
        parts.append(f"nom. {format_with_unit(nominal, unit, 0)}")

    return "; ".join(parts) if parts else "—"


def timing_measurement(name: str, metric: dict[str, Any]) -> dict[str, str]:
    unit = metric.get("unit", "")
    return {
        "name": name,
        "min": format_with_unit(metric.get("min"), unit),
        "avg": format_with_unit(metric.get("avg"), unit),
        "max": format_with_unit(metric.get("max"), unit),
        "target": format_target(metric),
    }


def test_measurements(test: dict[str, Any]) -> list[dict[str, str]]:
    metrics = test.get("metrics") or {}
    timing = metrics.get("dmxTiming")
    if not isinstance(timing, dict):
        return []

    measurements = [
        timing_measurement("Break", timing.get("break", {})),
        timing_measurement("MAB", timing.get("markAfterBreak", {})),
        timing_measurement("Data", timing.get("data", {})),
        timing_measurement("Frame period", timing.get("framePeriod", {})),
        timing_measurement("Slots", timing.get("slots", {})),
    ]

    baud = timing.get("baud", {})
    if isinstance(baud, dict):
        measurements.append(
            {
                "name": "Baud",
                "min": format_with_unit(baud.get("minimum"), baud.get("unit", ""), 0),
                "avg": format_with_unit(baud.get("actual"), baud.get("unit", ""), 0),
                "max": format_with_unit(baud.get("maximum"), baud.get("unit", ""), 0),
                "target": (
                    f"nom. {format_with_unit(baud.get('nominal'), baud.get('unit', ''), 0)}; "
                    f"dev. {format_number(baud.get('deviationPercent'), 2)}%"
                ),
            }
        )

    return measurements


def format_datetime(value: str) -> str:
    if not value:
        return "N/A"
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return value
    return parsed.astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")


def grouped_tests(report: dict[str, Any]) -> list[tuple[str, list[dict[str, Any]]]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for test in report.get("tests", []):
        test = dict(test)
        test["measurements"] = test_measurements(test)
        groups[test.get("group") or "Other"].append(test)
    return sorted(groups.items(), key=lambda item: item[0].lower())


def certificate_basename(report: dict[str, Any], report_path: Path) -> str:
    node = report.get("node", {})
    chip_id = safe_filename_part(node.get("chipId"))
    firmware = safe_filename_part(node.get("firmware"))
    started = safe_filename_part(str(report.get("startedAt", ""))[:19].replace(":", ""))
    result = safe_filename_part(report.get("summary", {}).get("result", "UNKNOWN"))
    parts = ["unode"]
    if chip_id:
        parts.append(chip_id)
    if firmware:
        parts.append(f"fw-{firmware}")
    if started:
        parts.append(started)
    parts.append(result.lower())
    fallback = safe_filename_part(report_path.stem) or "certificate"
    return "-".join(parts) if len(parts) > 1 else fallback


def render_html(report: dict[str, Any], report_path: Path) -> str:
    summary = report.get("summary", {})
    result = summary.get("result", "UNKNOWN")
    result_color = {
        "PASS": "#12805c",
        "FAIL": "#c62828",
    }.get(result, "#a86400")
    template = Template(HTML_TEMPLATE)
    return template.render(
        certificate_id=certificate_basename(report, report_path),
        source_name=report_path.name,
        logo_data_uri=file_data_uri(LOGO_PATH),
        node=report.get("node", {}),
        environment=report.get("environment", {}),
        summary=summary,
        grouped_tests=grouped_tests(report),
        started_local=format_datetime(report.get("startedAt", "")),
        finished_local=format_datetime(report.get("finishedAt", "")),
        duration_text=format_duration(float(report.get("durationSeconds", 0))),
        generated_at=datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z"),
        result_color=result_color,
    )


def find_browser(explicit: Path | None) -> Path | None:
    if explicit and explicit.exists():
        return explicit

    candidates = [
        shutil.which("chrome"),
        shutil.which("msedge"),
        shutil.which("chromium"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return Path(candidate)
    return None


def render_pdf(html_path: Path, pdf_path: Path, browser: Path) -> None:
    command = [
        str(browser),
        "--headless=new",
        "--disable-gpu",
        "--no-pdf-header-footer",
        f"--print-to-pdf={pdf_path}",
        html_path.resolve().as_uri(),
    ]
    subprocess.run(command, check=True)


def main() -> int:
    args = parse_args()
    report_path = args.report or newest_report()
    report_path = report_path.resolve()
    report = read_report(report_path)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    base = certificate_basename(report, report_path)
    html_path = args.output_dir / f"{base}.html"
    pdf_path = args.output_dir / f"{base}.pdf"

    html_path.write_text(render_html(report, report_path), encoding="utf-8")
    print(f"HTML certificate: {html_path}")

    if args.html_only:
        return 0

    browser = find_browser(args.browser)
    if browser is None:
        print("PDF certificate: skipped, Chrome/Edge executable not found", file=sys.stderr)
        return 0

    render_pdf(html_path, pdf_path, browser)
    print(f"PDF certificate : {pdf_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
