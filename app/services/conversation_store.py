from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field

from app.models.booking import EnquiryState

logger = logging.getLogger(__name__)


@dataclass
class ConversationRecord:
    messages: list[dict[str, str]] = field(default_factory=list)
    enquiry_state: EnquiryState = field(default_factory=EnquiryState)


class ConversationStore:
    def __init__(self) -> None:
        self._conversations: dict[str, ConversationRecord] = {}

    def get_or_create(self, conversation_id: str | None) -> tuple[str, ConversationRecord]:
        if conversation_id and conversation_id in self._conversations:
            return conversation_id, self._conversations[conversation_id]

        new_id = conversation_id or str(uuid.uuid4())
        record = ConversationRecord()
        self._conversations[new_id] = record
        return new_id, record

    def append_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
    ) -> None:
        record = self._conversations[conversation_id]
        record.messages.append({"role": role, "content": content})

    def get_messages(self, conversation_id: str) -> list[dict[str, str]]:
        return self._conversations.get(conversation_id, ConversationRecord()).messages

    def get_enquiry_state(self, conversation_id: str) -> EnquiryState:
        return self._conversations.get(
            conversation_id,
            ConversationRecord(),
        ).enquiry_state

    def set_enquiry_state(self, conversation_id: str, state: EnquiryState) -> None:
        self._conversations[conversation_id].enquiry_state = state


_store: ConversationStore | None = None


def get_conversation_store() -> ConversationStore:
    global _store
    if _store is None:
        _store = ConversationStore()
    return _store
