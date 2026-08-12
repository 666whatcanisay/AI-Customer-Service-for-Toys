from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterable
from pathlib import Path

from channel_engine.provider import NormalizedChannelObservation
from channel_engine.provider import ChannelMessageProvider, ProviderIngress

from .control_v2 import AgentObservationSubmission


class ProviderUnavailable(RuntimeError):
    pass


class SyntheticPDDProvider:
    """Deterministic one-shot provider used by mandatory offline black-box tests."""

    def __init__(
        self,
        observations: Iterable[NormalizedChannelObservation],
        *,
        provider_id: str = "synthetic-pdd",
    ) -> None:
        self.provider_id = provider_id
        self._pending = list(observations)
        if any(item.provider_kind != "SYNTHETIC_PDD" for item in self._pending):
            raise ValueError("SyntheticPDDProvider accepts synthetic observations only")

    def poll(self, *, limit: int = 100) -> tuple[NormalizedChannelObservation, ...]:
        bounded = max(1, min(limit, 100))
        result = tuple(self._pending[:bounded])
        del self._pending[:bounded]
        return result


class RecordedReplayProvider:
    """Reads a bounded, immutable JSON replay through the same Provider port."""

    def __init__(self, fixture: str | Path, *, provider_id: str = "recorded-replay") -> None:
        self.provider_id = provider_id
        raw = json.loads(Path(fixture).read_text(encoding="utf-8"))
        rows = raw.get("observations") if isinstance(raw, dict) else raw
        if not isinstance(rows, list) or len(rows) > 10_000:
            raise ValueError("recorded replay fixture is invalid or unbounded")
        self._pending: list[NormalizedChannelObservation] = []
        for row in rows:
            value = NormalizedChannelObservation.model_validate_json(
                json.dumps(row, ensure_ascii=False, separators=(",", ":"))
            )
            self._pending.append(
                value.model_copy(
                    update={
                        "provider_id": provider_id,
                        "provider_kind": "RECORDED_REPLAY",
                    }
                )
            )

    def poll(self, *, limit: int = 100) -> tuple[NormalizedChannelObservation, ...]:
        bounded = max(1, min(limit, 100))
        result = tuple(self._pending[:bounded])
        del self._pending[:bounded]
        return result


class RealPDDProvider:
    """Bounded REAL_PDD Provider backed by the evidence-only read adapter.

    The callback may only return already normalized read results.  Durable
    Spool persistence and ACK-controlled Cursor advancement remain outside
    this Provider and are owned by the existing formal Agent composition.
    """

    def __init__(
        self,
        read: Callable[[int], Iterable[NormalizedChannelObservation]],
        *,
        provider_id: str = "real-pdd-readonly",
    ) -> None:
        self.provider_id = provider_id
        self._read = read

    def poll(self, *, limit: int = 100) -> tuple[NormalizedChannelObservation, ...]:
        bounded = max(1, min(limit, 100))
        try:
            observations = tuple(self._read(bounded))
        except Exception as exc:
            raise ProviderUnavailable("REAL_PDD read adapter is unavailable") from exc
        if len(observations) > bounded:
            raise ProviderUnavailable("REAL_PDD read adapter exceeded the bounded poll")
        normalized: list[NormalizedChannelObservation] = []
        for item in observations:
            if item.provider_kind != "REAL_PDD":
                raise ProviderUnavailable("REAL_PDD Provider received a non-real item")
            normalized.append(item.model_copy(update={"provider_id": self.provider_id}))
        return tuple(normalized)


class ChannelAgentProviderIngress:
    """ChannelAgent-side adapter from the Provider port to the durable Host ACK."""

    def __init__(
        self,
        provider: ChannelMessageProvider,
        *,
        agent_id: str,
        device_id: str,
        submit: Callable[[AgentObservationSubmission], object],
        provider_read_trace: Callable[[str], None] | None = None,
    ) -> None:
        self._agent_id = agent_id
        self._device_id = device_id
        self._submit = submit
        self._trace = provider_read_trace or (lambda _trace_id: None)
        self._ingress = ProviderIngress(provider, self._accept)

    def scan_once(self, *, limit: int = 100) -> int:
        return self._ingress.run_once(limit=limit)

    def _accept(self, value: NormalizedChannelObservation) -> object:
        self._trace(value.trace_id)
        payload = value.pdd_payload()
        canonical = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return self._submit(
            AgentObservationSubmission(
                observation_id=provider_observation_id(value),
                agent_id=self._agent_id,
                device_id=self._device_id,
                store_id=value.store_id,
                conversation_id=value.conversation_id,
                external_message_id=value.external_message_id,
                source_cursor=value.source_cursor,
                source_sequence=value.source_sequence,
                payload_digest="sha256:" + hashlib.sha256(canonical).hexdigest(),
                payload=payload,
                captured_at=value.captured_at,
            )
        )


def provider_observation_id(value: NormalizedChannelObservation) -> str:
    material = f"{value.provider_id}\0{value.store_id}\0{value.external_message_id}"
    return "provider-observation:" + hashlib.sha256(material.encode("utf-8")).hexdigest()


__all__ = [
    "ProviderUnavailable",
    "ChannelAgentProviderIngress",
    "RealPDDProvider",
    "RecordedReplayProvider",
    "SyntheticPDDProvider",
    "provider_observation_id",
]
