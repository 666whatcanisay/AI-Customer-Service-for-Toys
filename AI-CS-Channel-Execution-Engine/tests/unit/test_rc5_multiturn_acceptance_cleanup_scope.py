from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "run_rc5_multiturn_acceptance",
    ROOT / "scripts" / "run_rc5_multiturn_acceptance.py",
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def _payload(conversation_id: str, provider_id: str, provider_kind: str) -> str:
    return json.dumps(
        {
            "conversation_id": conversation_id,
            "provider_id": provider_id,
            "provider_kind": provider_kind,
        }
    )


def test_cleanup_targets_only_known_synthetic_scopes(tmp_path: Path) -> None:
    database = tmp_path / "host.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE channel_agent_observations "
            "(conversation_id TEXT NOT NULL, payload TEXT NOT NULL)"
        )
        connection.executemany(
            "INSERT INTO channel_agent_observations VALUES(?,?)",
            (
                (
                    MODULE.CONVERSATION_ID,
                    _payload(
                        MODULE.CONVERSATION_ID,
                        MODULE.PROVIDER_ID,
                        "SYNTHETIC_PDD",
                    ),
                ),
                (
                    "rc5-ui-old-test",
                    _payload("rc5-ui-old-test", "legacy-test", "RECORDED_REPLAY"),
                ),
                (
                    MODULE.CONVERSATION_ID,
                    _payload(MODULE.CONVERSATION_ID, "untrusted-provider", "SYNTHETIC_PDD"),
                ),
                (
                    "real-customer-conversation",
                    _payload("real-customer-conversation", "pdd", "REAL_PDD"),
                ),
            ),
        )

    assert MODULE._target_conversations(database) == [
        MODULE.CONVERSATION_ID,
        "rc5-ui-old-test",
    ]
