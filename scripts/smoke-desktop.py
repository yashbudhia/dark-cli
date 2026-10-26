"""Exercise only the disposable Dark Desktop Fixture; no model calls."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    executable = root / ".venv" / "Scripts" / "dark.exe"
    scenarios = root / "examples" / "desktop"
    checks = [
        ("doctor", ["desktop", "doctor"], 0),
        ("positive", ["desktop", "exercise", str(scenarios / "positive.json"), "--apply"], 0),
        ("negative", ["desktop", "exercise", str(scenarios / "negative.json"), "--apply"], 1),
        (
            "negative-replay",
            ["desktop", "exercise", str(scenarios / "negative.json"), "--apply"],
            1,
        ),
        (
            "capture",
            [
                "desktop",
                "probe",
                "--title",
                "Dark Desktop Fixture",
                "--expect",
                "Saved quantity: -2",
                "--screenshot",
            ],
            0,
        ),
    ]
    summary = []
    for name, arguments, expected_exit in checks:
        result = subprocess.run(
            [str(executable), *arguments],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=45,
        )
        try:
            report = json.loads(result.stdout)
        except ValueError as exc:
            raise RuntimeError(
                f"{name}: invalid JSON output: {result.stdout}\n{result.stderr}"
            ) from exc
        if result.returncode != expected_exit:
            raise RuntimeError(
                f"{name}: exit {result.returncode}, expected {expected_exit}: {report}"
            )
        if name in {"negative", "negative-replay"}:
            if not (
                report["status"] == "failed"
                and report["assertions"][0]["passed"] is True
                and report["assertions"][-1]["observed"]["text"] == "Saved quantity: -2"
            ):
                raise RuntimeError(f"{name}: the fixture bug was not reproduced: {report}")
        if name == "capture":
            screenshot = Path(report["evidence_dir"]) / "screenshot.png"
            if not screenshot.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"):
                raise RuntimeError("The screenshot is not a PNG")
        summary.append(
            {
                "check": name,
                "exit_code": result.returncode,
                "status": report["status"],
                "evidence_dir": report.get("evidence_dir"),
            }
        )
    output = json.dumps({"status": "passed", "checks": summary}, indent=2)
    (root / ".dark" / "smoke-latest.json").write_text(output + "\n", encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
