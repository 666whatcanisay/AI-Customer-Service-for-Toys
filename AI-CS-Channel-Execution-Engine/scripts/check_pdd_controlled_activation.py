from __future__ import annotations

import argparse
import json
from pathlib import Path

from pydantic import ValidationError

from channel_engine.pdd_adapter import (
    PDDControlledActivationCheckInput,
    PDDControlledActivationPreflight,
)


def _write_output(payload: dict[str, object], output: Path | None) -> None:
    serialized = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    if output is None:
        print(serialized)
        return
    output.write_text(serialized + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "离线检查 PDD 首次受控观察激活材料；不会启动浏览器、连接平台或签发激活授权。"
        )
    )
    parser.add_argument("--input", type=Path, help="受控激活检查 JSON")
    parser.add_argument("--output", type=Path, help="可选的检查结果 JSON")
    parser.add_argument(
        "--schema",
        action="store_true",
        help="输出检查输入 JSON Schema，不执行检查",
    )
    args = parser.parse_args()

    if args.schema:
        _write_output(
            PDDControlledActivationCheckInput.model_json_schema(),
            args.output,
        )
        return 0
    if args.input is None:
        parser.error("--input is required unless --schema is used")

    try:
        payload = args.input.read_text(encoding="utf-8")
        check = PDDControlledActivationCheckInput.model_validate_json(payload)
        result = PDDControlledActivationPreflight().evaluate(check)
    except (OSError, json.JSONDecodeError, ValidationError, ValueError) as exc:
        _write_output(
            {
                "preparation_status": "INVALID_INPUT",
                "activation_authorized": False,
                "error_code": "PDD_ACTIVATION_CHECK_INPUT_INVALID",
                "message": f"激活检查材料无效：{exc}",
            },
            args.output,
        )
        return 1

    _write_output(result.model_dump(mode="json"), args.output)
    return 0 if result.ready_for_separate_activation_authorization else 2


if __name__ == "__main__":
    raise SystemExit(main())
