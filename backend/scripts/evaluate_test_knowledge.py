from __future__ import annotations

import argparse
import json
import sys
import tempfile
from dataclasses import replace
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.config.settings import Settings  # noqa: E402
from app.service.evaluation import (  # noqa: E402
    parse_evaluations,
    render_markdown,
    report_json,
    run_evaluations,
)
from app.service.rag_service import RAGService  # noqa: E402
from app.service.test_knowledge import (  # noqa: E402
    parse_test_knowledge_package,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the frozen V0.3.1 C-to-A RAG evaluation set."
    )
    parser.add_argument("package_id")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--fixture-dir",
        type=Path,
        help="Synthetic development only; never count as live C integration.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    settings = Settings.from_env()
    temporary: tempfile.TemporaryDirectory[str] | None = None
    if args.fixture_dir:
        temporary = tempfile.TemporaryDirectory(prefix="a-t03-fixture-")
        temp_root = Path(temporary.name)
        settings = replace(
            settings,
            backend_root=temp_root,
            project_root=temp_root,
            knowledge_base_path=temp_root / "knowledge_base",
            vector_db_path=temp_root / "vector_db",
            log_dir=temp_root / "logs",
        )

    service = RAGService(settings)
    try:
        if args.fixture_dir:
            package_payload = json.loads(
                (args.fixture_dir / "test_knowledge_v031.json").read_text(
                    encoding="utf-8"
                )
            )
            evaluations_payload = json.loads(
                (args.fixture_dir / "evaluations_v031.json").read_text(
                    encoding="utf-8"
                )
            )
            package = parse_test_knowledge_package(
                package_payload, expected_package_id=args.package_id
            )
            service.test_knowledge_index.sync(package)
            evidence_mode = "synthetic_fixture"
        else:
            service.sync_test_knowledge(args.package_id)
            evaluations_payload = service.platform_client.fetch_evaluations(
                args.package_id
            )
            evidence_mode = "live_c_api"

        cases = parse_evaluations(evaluations_payload, args.package_id)
        report = run_evaluations(cases, service.query)
        report.update(
            {
                "package_id": args.package_id,
                "schema_version": "V0.3.1",
                "evidence_mode": evidence_mode,
                "production_usable": False,
            }
        )
        args.output_dir.mkdir(parents=True, exist_ok=True)
        (args.output_dir / "a-t03-evaluation.json").write_text(
            report_json(report), encoding="utf-8"
        )
        (args.output_dir / "a-t03-evaluation.md").write_text(
            render_markdown(report), encoding="utf-8"
        )
        print(
            f"evaluation complete: {report['passed']}/{report['total']} "
            f"mode={evidence_mode}"
        )
        return 0 if report["failed"] == 0 else 1
    finally:
        service.close()
        if temporary is not None:
            temporary.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
