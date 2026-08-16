from __future__ import annotations

import argparse
import json
from pathlib import Path

from pydantic import ValidationError

from channel_engine.pdd_adapter import (
    PDDActivationEvidenceBuilder,
    PDDProductionActivationDecision,
    PDDProductionGateController,
    PDDProductionGovernanceInput,
    PDDProductionSyntheticDrill,
    PDDOfflineGovernanceSnapshotFactory,
)
from channel_engine.models.entities import utc_now


def _emit(payload: dict[str, object], output: Path | None) -> None:
    serialized = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    if output is None:
        print(serialized)
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(serialized + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "离线评估 PDD Production Activation Governance；"
            "不会连接平台、启动浏览器、读取消息、执行或签发授权。"
        )
    )
    parser.add_argument("--input", type=Path, help="Governance evidence JSON")
    parser.add_argument("--output", type=Path, help="Evidence Bundle 输出路径")
    parser.add_argument(
        "--schema",
        action="store_true",
        help="输出输入 JSON Schema，不执行评估",
    )
    parser.add_argument(
        "--drill",
        action="store_true",
        help="在同一合成基线上运行六场景离线演练",
    )
    parser.add_argument(
        "--offline-snapshot",
        action="store_true",
        help="生成当前 dormant preparation 快照，不探测外部环境",
    )
    parser.add_argument("--source-commit", help="40 位源码 commit SHA")
    parser.add_argument("--system-version", default="channel-engine-rc-v1")
    parser.add_argument("--runtime-version", default="runtime-v1")
    parser.add_argument("--regression-total", type=int, default=0)
    parser.add_argument("--regression-passed", type=int, default=0)
    parser.add_argument("--regression-warnings", type=int, default=0)
    parser.add_argument("--source-tree-clean", action="store_true")
    args = parser.parse_args()

    if args.schema:
        _emit(PDDProductionGovernanceInput.model_json_schema(), args.output)
        return 0
    if not args.offline_snapshot and args.input is None:
        parser.error("--input or --offline-snapshot is required unless --schema is used")
    if args.offline_snapshot and args.source_commit is None:
        parser.error("--source-commit is required with --offline-snapshot")
    if args.offline_snapshot and args.drill:
        parser.error("--drill requires an explicit all-pass synthetic input")

    try:
        evidence = (
            PDDOfflineGovernanceSnapshotFactory.build(
                system_version=args.system_version,
                runtime_version=args.runtime_version,
                source_commit_sha=args.source_commit,
                source_tree_clean=args.source_tree_clean,
                regression_total=args.regression_total,
                regression_passed=args.regression_passed,
                regression_warnings=args.regression_warnings,
                checked_at=utc_now(),
            )
            if args.offline_snapshot
            else PDDProductionGovernanceInput.model_validate_json(
                args.input.read_text(encoding="utf-8")
            )
        )
        controller = PDDProductionGateController()
        decision = controller.evaluate(evidence)
        bundle = PDDActivationEvidenceBuilder.build(
            evidence,
            decision,
            generated_at=evidence.checked_at,
        )
        drill = (
            PDDProductionSyntheticDrill(controller).run(
                evidence,
                generated_at=evidence.checked_at,
            )
            if args.drill
            else None
        )
    except (OSError, json.JSONDecodeError, ValidationError, ValueError, RuntimeError) as exc:
        _emit(
            {
                "governance_status": "INVALID_INPUT",
                "decision": "BLOCKED",
                "real_platform_activation_allowed": False,
                "activation_grant_issued": False,
                "real_send_enabled": False,
                "error_code": "PDD_GOVERNANCE_INPUT_INVALID",
                "message": f"治理证据无效：{exc}",
            },
            args.output,
        )
        return 1

    _emit(
        {
            "decision": decision.model_dump(mode="json"),
            "evidence_bundle": bundle.model_dump(mode="json"),
            "synthetic_drill": drill.model_dump(mode="json") if drill else None,
        },
        args.output,
    )
    return 2 if decision.decision is PDDProductionActivationDecision.BLOCKED else 0


if __name__ == "__main__":
    raise SystemExit(main())
