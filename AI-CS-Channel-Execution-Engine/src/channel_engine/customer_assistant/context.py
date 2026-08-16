from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from typing import Protocol, runtime_checkable

from pydantic import AwareDatetime

from .models import (
    BufferedCustomerMessage,
    ConversationHistoryEntry,
    ConversationTurn,
    CustomerContext,
    PageContext,
    TransactionContext,
)
from .history import VISIBLE_HISTORY_LIMIT


@runtime_checkable
class PageContextProvider(Protocol):
    def capture_page_context(
        self, *, store_id: str, conversation_id: str
    ) -> PageContext: ...


@runtime_checkable
class TransactionContextProvider(Protocol):
    def capture_transaction_context(
        self, *, store_id: str, conversation_id: str
    ) -> TransactionContext: ...


@runtime_checkable
class ConversationHistoryProvider(Protocol):
    def load_history(
        self, *, store_id: str, conversation_id: str, limit: int
    ) -> tuple[BufferedCustomerMessage, ...]: ...


@runtime_checkable
class VisibleConversationHistoryProvider(Protocol):
    def load_visible_history(
        self, *, store_id: str, conversation_id: str, limit: int
    ) -> tuple[ConversationHistoryEntry, ...]: ...


@runtime_checkable
class KnowledgeScopeProvider(Protocol):
    def scopes_for(
        self, *, store_id: str, conversation_id: str
    ) -> tuple[str, ...]: ...


class CustomerContextCollector:
    """Combines already-sanitized context ports without browser writes."""

    def __init__(
        self,
        page_provider: PageContextProvider,
        transaction_provider: TransactionContextProvider,
        history_provider: ConversationHistoryProvider,
        knowledge_provider: KnowledgeScopeProvider,
        *,
        clock: Callable[[], AwareDatetime],
        history_limit: int = 50,
        visible_history_limit: int = VISIBLE_HISTORY_LIMIT,
        visible_history_provider: VisibleConversationHistoryProvider | None = None,
    ) -> None:
        if not 1 <= history_limit <= 50:
            raise ValueError("assistant history limit must be between 1 and 50")
        if not 1 <= visible_history_limit <= VISIBLE_HISTORY_LIMIT:
            raise ValueError("visible conversation history limit must be between 1 and 20")
        self._page = page_provider
        self._transaction = transaction_provider
        self._history = history_provider
        self._knowledge = knowledge_provider
        self._visible_history = visible_history_provider
        self._clock = clock
        self._history_limit = history_limit
        self._visible_history_limit = visible_history_limit

    def collect(self, turn: ConversationTurn) -> CustomerContext:
        page = self._page.capture_page_context(
            store_id=turn.store_id,
            conversation_id=turn.conversation_id,
        )
        transaction = self._transaction.capture_transaction_context(
            store_id=turn.store_id,
            conversation_id=turn.conversation_id,
        )
        history = self._history.load_history(
            store_id=turn.store_id,
            conversation_id=turn.conversation_id,
            limit=self._history_limit,
        )
        by_identity = {
            item.external_message_id: item for item in (*history, *turn.messages)
        }
        merged = tuple(
            sorted(
                by_identity.values(),
                key=lambda item: (item.timestamp, item.external_message_id),
            )[-self._history_limit :]
        )
        visible_history: tuple[ConversationHistoryEntry, ...] = ()
        if self._visible_history is not None:
            turn_loader = getattr(
                self._visible_history, "load_visible_history_for_turn", None
            )
            if callable(turn_loader):
                visible_history = turn_loader(
                    store_id=turn.store_id,
                    conversation_id=turn.conversation_id,
                    limit=self._visible_history_limit,
                    excluded_external_message_ids=tuple(
                        item.external_message_id for item in turn.messages
                    ),
                )
            else:
                visible_history = self._visible_history.load_visible_history(
                    store_id=turn.store_id,
                    conversation_id=turn.conversation_id,
                    limit=self._visible_history_limit,
                )
        material = json.dumps(
            [
                turn.turn_id,
                page.model_dump(mode="json"),
                transaction.model_dump(mode="json"),
                [item.content_digest for item in merged],
                [item.content_digest for item in visible_history],
            ],
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        return CustomerContext(
            context_id="customer-context:"
            + hashlib.sha256(material.encode("utf-8")).hexdigest(),
            turn_id=turn.turn_id,
            store_id=turn.store_id,
            conversation_id=turn.conversation_id,
            customer_reference=turn.customer_reference,
            page=page,
            transaction=transaction,
            conversation_history=merged,
            visible_conversation_history=visible_history,
            current_turn_message_ids=tuple(
                item.external_message_id for item in turn.messages
            ),
            current_question=turn.combined_question,
            knowledge_scopes=self._knowledge.scopes_for(
                store_id=turn.store_id,
                conversation_id=turn.conversation_id,
            ),
            assembled_at=self._clock(),
        )


__all__ = [
    "ConversationHistoryProvider",
    "CustomerContextCollector",
    "KnowledgeScopeProvider",
    "PageContextProvider",
    "TransactionContextProvider",
    "VisibleConversationHistoryProvider",
]
