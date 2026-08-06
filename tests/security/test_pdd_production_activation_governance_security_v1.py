from __future__ import annotations

import inspect

from channel_engine.pdd_adapter import (
    PDDActivationEvidenceBuilder,
    PDDProductionGateController,
    PDDProductionSyntheticDrill,
    PDDRollbackGovernance,
)


def test_governance_services_expose_only_offline_decision_methods() -> None:
    expected = {
        PDDProductionGateController: {"evaluate"},
        PDDActivationEvidenceBuilder: {"build", "contract_hash"},
        PDDProductionSyntheticDrill: {"run"},
        PDDRollbackGovernance: {"simulate"},
    }
    for service, allowed in expected.items():
        public = {
            name
            for name, value in inspect.getmembers(service, predicate=inspect.isfunction)
            if not name.startswith("_")
        }
        assert public == allowed
        assert not public.intersection(
            {
                "connect",
                "login",
                "receive",
                "send",
                "execute",
                "activate",
                "issue_grant",
                "delete_history",
            }
        )


def test_governance_module_does_not_import_network_or_browser_automation() -> None:
    source = inspect.getsource(inspect.getmodule(PDDProductionGateController))
    for prohibited_import in (
        "import httpx",
        "import requests",
        "import urllib",
        "import websocket",
        "import playwright",
        "import selenium",
    ):
        assert prohibited_import not in source.casefold()
