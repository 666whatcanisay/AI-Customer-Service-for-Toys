from __future__ import annotations

import json
from pathlib import Path

from app.gateway.contract import gateway_contract_schema


ROOT = Path(__file__).resolve().parents[2]
TARGET = ROOT / "contracts" / "schemas" / "channel-engine-gateway-server.v1.schema.json"


def main() -> None:
    TARGET.write_text(
        json.dumps(gateway_contract_schema(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
