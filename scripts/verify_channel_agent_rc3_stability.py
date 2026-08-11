from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the RC3 Windows Runtime gate repeatedly.")
    parser.add_argument("--rounds", type=int, default=50)
    parser.add_argument("--timeout-seconds", type=float, default=20.0)
    parser.add_argument("--evidence", required=True, type=Path)
    args = parser.parse_args()
    if args.rounds < 1 or args.rounds > 200:
        raise SystemExit("rounds must be between 1 and 200")

    started = time.monotonic()
    results: list[dict[str, object]] = []
    command = [
        sys.executable,
        "-m",
        "pytest",
        "tests/windows_agent/test_channel_agent_windows_client_v1.py",
        "-q",
        "--disable-warnings",
    ]
    for round_number in range(1, args.rounds + 1):
        round_started = time.monotonic()
        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=args.timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            results.append(
                {
                    "round": round_number,
                    "status": "TIMEOUT",
                    "duration_seconds": round(time.monotonic() - round_started, 3),
                }
            )
            failure = f"round {round_number} timed out: {exc}"
            break
        status = "PASSED" if completed.returncode == 0 else "FAILED"
        results.append(
            {
                "round": round_number,
                "status": status,
                "return_code": completed.returncode,
                "duration_seconds": round(time.monotonic() - round_started, 3),
                "output_tail": (completed.stdout + completed.stderr)[-500:],
            }
        )
        if completed.returncode != 0:
            failure = f"round {round_number} failed"
            break
    else:
        failure = None

    evidence = {
        "schema_version": "1.0",
        "rounds_requested": args.rounds,
        "rounds_completed": len(results),
        "passed": failure is None,
        "failure": failure,
        "duration_seconds": round(time.monotonic() - started, 3),
        "results": results,
    }
    args.evidence.parent.mkdir(parents=True, exist_ok=True)
    args.evidence.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(f"rounds_completed={len(results)}")
    print(f"passed={str(failure is None).lower()}")
    print(f"evidence={args.evidence}")
    return 0 if failure is None else 1


if __name__ == "__main__":
    raise SystemExit(main())
