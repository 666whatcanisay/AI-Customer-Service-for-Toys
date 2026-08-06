from __future__ import annotations

import argparse
import json
from pathlib import Path

from channel_engine.browser import draft_pdd_merchant_chat_v1
from channel_engine.models.entities import utc_now
from channel_engine.pilot import (
    PilotEnvironmentService,
    PilotGatewayVerification,
    load_pilot_environment_config,
)

from verify_pilot_gateway import verify


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare the PDD Pilot node without login, message reads, or transport activation."
        )
    )
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--ai-backend", type=Path, required=True)
    parser.add_argument("--gateway-port", type=int, default=18021)
    args = parser.parse_args()

    config = load_pilot_environment_config(args.config)
    gateway_result = verify(
        args.ai_backend,
        port=args.gateway_port,
        client_id=config.gateway_client_id,
        key_id=config.gateway_key_id,
    )
    now = utc_now()
    verification = PilotGatewayVerification(
        endpoint=f"http://127.0.0.1:{args.gateway_port}",
        client_id=config.gateway_client_id,
        key_id=config.gateway_key_id,
        decision_route=bool(gateway_result["decision_route"]),
        health_route=bool(gateway_result["health_route"]),
        signed_health_verified=bool(gateway_result["signed_health_verified"]),
        health_status=str(gateway_result["health_status"]),  # type: ignore[arg-type]
        contract_version=str(gateway_result["contract_version"]),
        gateway_version=(
            str(gateway_result["gateway_version"])
            if gateway_result["gateway_version"] is not None
            else None
        ),
        capability_version=(
            str(gateway_result["capability_version"])
            if gateway_result["capability_version"] is not None
            else None
        ),
        real_ai_cs_connected=bool(gateway_result["real_ai_cs_connected"]),
        verified_at=now,
    )
    service = PilotEnvironmentService(config)
    service.provision_profile_directory()
    readiness = service.readiness(
        verification,
        draft_pdd_merchant_chat_v1(),
        generated_at=now,
    )
    print(
        json.dumps(
            {
                "gateway": gateway_result,
                "environment": readiness.model_dump(mode="json"),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if readiness.final_status.value == "PDD_PILOT_ENV_READY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
