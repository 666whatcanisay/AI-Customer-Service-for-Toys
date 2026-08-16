from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from channel_engine.pilot import (
    PilotBrowserDiscoveryLaunchConfig,
    build_selector_discovery_browser_session,
    load_pilot_environment_config,
)


def _public_status(session) -> dict[str, object]:  # type: ignore[no-untyped-def]
    page = session.page_context
    return {
        "mode": "PDD_OBSERVE_ONLY",
        "session_state": session.state.value,
        "login_state": session.login_state.value,
        "human_login_required": session.human_takeover_required,
        "generation": session.generation,
        "page_available": page is not None,
        "selector_contract_version": (
            page.selector_contract_version if page is not None else None
        ),
        "profile_id": session.profile.profile_id,
        "automatic_login": False,
        "customer_message_read_enabled": False,
        "outbound_transport_enabled": False,
        "page_write_operations": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Start the dedicated PDD Observe browser and wait for human login. "
            "This command never enters credentials, reads messages, or sends data."
        )
    )
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    parser.add_argument(
        "--once",
        action="store_true",
        help="Start, emit one sanitized snapshot, then stop Chrome.",
    )
    args = parser.parse_args()
    if not 0.25 <= args.poll_seconds <= 60:
        raise ValueError("poll interval must be between 0.25 and 60 seconds")

    config = load_pilot_environment_config(args.config)
    launch = PilotBrowserDiscoveryLaunchConfig(
        merchant_chat_url=config.merchant_chat_url,
        node_id=config.agent.node_id,
        profile_id=config.browser_profile_id,
        selector_contract_version=config.selector_contract_id,
    )
    manager = build_selector_discovery_browser_session(
        launch,
        chrome_path=Path(config.agent.browser.chrome_path),
        profile_root=Path(config.agent.browser.profile_root),
    )

    try:
        session = manager.start()
        last_status = _public_status(session)
        print(json.dumps(last_status, ensure_ascii=False, sort_keys=True), flush=True)
        if args.once:
            return 0
        while True:
            time.sleep(args.poll_seconds)
            session = manager.heartbeat()
            current = _public_status(session)
            if current != last_status:
                print(json.dumps(current, ensure_ascii=False, sort_keys=True), flush=True)
                last_status = current
    except KeyboardInterrupt:
        return 0
    finally:
        try:
            manager.stop()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
