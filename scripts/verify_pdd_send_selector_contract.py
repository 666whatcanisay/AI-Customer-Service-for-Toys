from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from channel_agent.binding import atomic_write_bytes
from channel_agent.browser import ChannelAgentBrowserManager
from channel_agent.config import load_agent_config
from channel_agent.logger import SafeAgentLogger
from channel_agent.pdd_login import EdgePDDTargetResolver
from channel_agent.pdd_workspace_send import PDDWorkspaceOutboundSelectorContract
from channel_engine.browser.cdp_readonly import WebSocketCDPEvaluator
from channel_engine.browser.selectors import (
    LocatorEngine,
    SelectorBinding,
    SelectorCapability,
    SelectorContract,
    SelectorContractState,
    SelectorEvidenceEnvironment,
    SelectorKey,
    SelectorVerificationEvidence,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify the one-message PDD send selectors without writing the page."
    )
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--operator-reference", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    data_root = Path(args.data_root).resolve()
    config = load_agent_config(data_root / "config" / "agent.json")
    manager = ChannelAgentBrowserManager(
        agent_id=config.agent_id,
        data_root=data_root,
        enabled=config.browser_enabled,
        logger=SafeAgentLogger(data_root / "logs" / "send-selector-verification.jsonl"),
    )
    state = manager.browser_status()
    manager.close_resources()
    if state.status.value != "READY" or state.pid is None:
        raise RuntimeError("Agent-owned PDD Edge is not READY")
    target = EdgePDDTargetResolver(timeout_seconds=2.0).resolve(
        Path(state.profile_path)
    )
    value = WebSocketCDPEvaluator(timeout_seconds=3.0).evaluate(
        target,
        r"""(()=>{const inputs=[...document.querySelectorAll('#replyTextarea')];const sends=[...document.querySelectorAll('.reply-footer .send-btn')];const scopes=[...document.querySelectorAll('[currentuid]')];return{url:String(location.href||''),input_count:inputs.length,send_count:sends.length,current_uid:scopes[0]?.getAttribute('currentuid')||'',input_length:inputs.length===1?String(inputs[0].value||'').length:null,send_texts:sends.map(x=>String(x.innerText||'').trim()),input_tags:inputs.map(x=>String(x.tagName||'')),send_tags:sends.map(x=>String(x.tagName||'')),conversation_tags:scopes.slice(0,1).map(x=>String(x.tagName||''))};})()""",
    )
    if not isinstance(value, dict):
        raise RuntimeError("PDD send selector probe returned an invalid payload")
    if (
        value.get("url")
        != "https://mms.pinduoduo.com/chat-merchant/index.html#/"
        or value.get("input_count") != 1
        or value.get("send_count") != 1
        or value.get("input_length") != 0
        or value.get("send_texts") != ["发送"]
        or not str(value.get("current_uid") or "").strip()
    ):
        raise RuntimeError("PDD send selectors are ambiguous or the input is not empty")
    signature = json.dumps(
        {
            "url": value["url"],
            "input_tags": value.get("input_tags"),
            "send_tags": value.get("send_tags"),
            "conversation_tags": value.get("conversation_tags"),
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    page_fingerprint = "sha256:" + hashlib.sha256(signature.encode()).hexdigest()
    capabilities = frozenset({SelectorCapability.SEND_MESSAGE})
    bindings = (
        SelectorBinding(
            key=SelectorKey.CONVERSATION_ITEM,
            engine=LocatorEngine.CSS,
            locator="[currentuid]",
        ),
        SelectorBinding(
            key=SelectorKey.COMPOSER,
            engine=LocatorEngine.CSS,
            locator="#replyTextarea",
        ),
        SelectorBinding(
            key=SelectorKey.SEND_CONTROL,
            engine=LocatorEngine.CSS,
            locator=".reply-footer .send-btn",
        ),
        SelectorBinding(
            key=SelectorKey.SEND_CONFIRMATION,
            engine=LocatorEngine.TEXT,
            locator="发送",
        ),
    )
    now = datetime.now(UTC)
    reference = (
        "evidence-ref://production/pdd/workspace-send/"
        + now.strftime("%Y%m%dT%H%M%SZ")
    )
    candidate = SelectorContract(
        platform="pdd",
        page="merchant_chat",
        version="production-send-v1",
        state=SelectorContractState.DISCOVERY,
        capabilities=capabilities,
        bindings=bindings,
        evidence_reference=reference,
    )
    evidence = SelectorVerificationEvidence.issue(
        reference=reference,
        environment=SelectorEvidenceEnvironment.PRODUCTION,
        page_fingerprint=page_fingerprint,
        applicable_page_version="pdd-merchant-chat-20260815",
        verified_by=args.operator_reference,
        verified_at=now,
        expires_at=now + timedelta(days=7),
        capability_boundary=capabilities,
        selector_set_hash=candidate.selector_set_hash(),
    )
    contract = PDDWorkspaceOutboundSelectorContract(
        selector_contract=SelectorContract(
            platform=candidate.platform,
            page=candidate.page,
            version=candidate.version,
            state=SelectorContractState.VERIFIED,
            capabilities=candidate.capabilities,
            bindings=candidate.bindings,
            evidence_reference=candidate.evidence_reference,
            verified_at=now,
            verification_evidence=evidence,
        ),
        runtime_environment=SelectorEvidenceEnvironment.PRODUCTION,
    )
    output = Path(args.output).resolve()
    atomic_write_bytes(
        output,
        contract.model_dump_json(indent=2).encode("utf-8"),
    )
    print(
        json.dumps(
            {
                "status": "VERIFIED",
                "output": str(output),
                "current_conversation_id": value["current_uid"],
                "page_fingerprint": contract.page_fingerprint,
                "evidence_hash": contract.evidence_hash,
                "expires_at": evidence.expires_at.isoformat(),
                "page_write_operations": 0,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
