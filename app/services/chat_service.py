from __future__ import annotations

import logging
import re

from app.config import Settings, get_settings
from app.models.booking import EnquiryStatus, EnquiryType
from app.models.chat import ChatResponse, Source
from app.prompts.system_prompt import RAG_USER_PROMPT_TEMPLATE, SYSTEM_PROMPT
from app.services.gemini_client import GeminiClient, get_gemini_client
from app.services.booking_service import BookingService
from app.services.conversation_store import ConversationStore, get_conversation_store
from app.services.grounding import GroundingService
from app.services.rag_service import RagService
from app.services.retrieval_service import RetrievalService, UNAVAILABLE_ANSWER

logger = logging.getLogger(__name__)

_CODE_CUT_MARKERS = (
    "Summary: {",
    "Collected details: {",
    "{'airport':",
    '{"airport":',
    "{'pickup_location':",
)


def strip_code_from_reply(text: str) -> str:
    """Remove Python/JSON dumps so customers never see raw objects."""
    if not text:
        return text
    cleaned = text
    for marker in _CODE_CUT_MARKERS:
        index = cleaned.find(marker)
        if index != -1:
            cleaned = cleaned[:index]
    cleaned = re.sub(r"```[\s\S]*?```", "", cleaned)
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()


class ChatService:
    def __init__(
        self,
        settings: Settings | None = None,
        conversation_store: ConversationStore | None = None,
        rag_service: RagService | None = None,
        retrieval_service: RetrievalService | None = None,
        booking_service: BookingService | None = None,
        grounding_service: GroundingService | None = None,
        ai_client: GeminiClient | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.conversation_store = conversation_store or get_conversation_store()
        self.rag_service = rag_service or RagService()
        self.retrieval_service = retrieval_service or RetrievalService()
        self.booking_service = booking_service or BookingService()
        self.grounding_service = grounding_service or GroundingService()
        self._gemini_client = ai_client

    @property
    def gemini_client(self) -> GeminiClient:
        if self._gemini_client is None:
            self._gemini_client = get_gemini_client(self.settings)
        return self._gemini_client

    def chat(self, message: str, conversation_id: str | None = None) -> ChatResponse:
        conversation_id, record = self.conversation_store.get_or_create(conversation_id)
        enquiry_state = record.enquiry_state

        detected_intent = self.booking_service.detect_intent(message)
        contact_only = self.grounding_service.detect_contact_only_service(message)
        # Do not start a VIP/transfer enquiry when the user asked for a contact-only service.
        if contact_only:
            detected_intent = EnquiryType.NONE
        if detected_intent != EnquiryType.NONE and enquiry_state.enquiry_type == EnquiryType.NONE:
            enquiry_state = self.booking_service.start_enquiry(enquiry_state, detected_intent)

        if enquiry_state.enquiry_type != EnquiryType.NONE:
            # Prefer current message, then earlier user turns, so slots already
            # mentioned (e.g. Heathrow) are retained and not re-asked.
            for prior in record.messages:
                if prior.get("role") == "user" and prior.get("content"):
                    enquiry_state = self.booking_service.update_from_message(
                        enquiry_state,
                        prior["content"],
                    )
            enquiry_state = self.booking_service.update_from_message(enquiry_state, message)
            enquiry_state = self.booking_service.mark_complete_if_ready(enquiry_state)
            self.conversation_store.set_enquiry_state(conversation_id, enquiry_state)

        retrieval_query = self._build_retrieval_query(message, record.messages)
        retrieval_query = self.grounding_service.boost_retrieval_query(retrieval_query)
        use_rag = self.retrieval_service.needs_retrieval(
            message,
            enquiry_active=enquiry_state.enquiry_type != EnquiryType.NONE,
        )

        context = ""
        sources: list[Source] = []
        relevant_chunks: list = []
        if use_rag:
            context, relevant_chunks = self.rag_service.retrieve_context(retrieval_query)
            sources = self.retrieval_service.to_sources(relevant_chunks)

        enquiry_context = self.booking_service.build_enquiry_context(enquiry_state)
        history = self._format_history(record.messages)
        grounding_directives = self.grounding_service.build_grounding_directives(message)
        if grounding_directives:
            enquiry_context = f"{grounding_directives}\n\n{enquiry_context}".strip()
        is_urgent = self.booking_service.detect_urgent_travel(message)
        if is_urgent:
            urgent_note = (
                "URGENT TRAVEL DETECTED: Travel appears to be within 24–48 hours. "
                "Lead with WhatsApp/phone operations contact +44 7414 246103 for real-time "
                "confirmation. Do not treat this as a normal wait-for-email enquiry."
            )
            enquiry_context = f"{urgent_note}\n\n{enquiry_context}".strip()

        # No sufficiently relevant KB context → do not invent from weak/cross-topic matches.
        if use_rag and not relevant_chunks and not contact_only:
            # Still allow grounding post-checks for pricing / coverage style questions
            # that have deterministic fallbacks, via a short unavailable stub.
            answer = UNAVAILABLE_ANSWER
            if self.grounding_service.asks_about_pricing(message) or self.grounding_service.find_unconfirmed_airports(message) or self.grounding_service.asks_about_terminal(message):
                answer = self.grounding_service.ensure_answer_covers_grounding(message, answer)
            elif is_urgent:
                answer = f"{self.booking_service.urgent_contact_message()}\n\n{answer}"
            else:
                answer = self.grounding_service.ensure_answer_covers_grounding(message, answer)

            if self.booking_service.is_informational_question(message) and enquiry_state.status != EnquiryStatus.COMPLETE:
                closing = self.booking_service.informational_closing()
                if closing.lower() not in answer.lower():
                    answer = f"{answer.rstrip()}\n\n{closing}"

            answer = self.booking_service.strip_redundant_closings(answer)
            answer = strip_code_from_reply(answer)
            self.conversation_store.append_message(conversation_id, "user", message)
            self.conversation_store.append_message(conversation_id, "assistant", answer)
            return ChatResponse(
                answer=answer,
                conversation_id=conversation_id,
                sources=sources,
            )

        answer = self._generate_response(
            message=message,
            context=context,
            history=history,
            enquiry_context=enquiry_context,
        )

        if not self.booking_service.has_team_contact(enquiry_state):
            if self.booking_service.wants_team_handover(message):
                # Only force the contact CTA when the user explicitly asks to send/pass enquiry.
                if self.booking_service.already_asked_for_contact(record.messages):
                    answer = self.booking_service.contact_reminder_message(enquiry_state)
                else:
                    answer = self.booking_service.contact_needed_message(enquiry_state)
            elif self.booking_service.claims_team_handover(answer):
                # Model invented a handover — strip that claim; do not spam the CTA.
                answer = self.booking_service.sanitize_false_handover(answer)
                if not answer.strip():
                    answer = (
                        "I can help with your enquiry. "
                        "When you are ready to send it to the team, I will need your full name "
                        "and an email or phone number."
                    )

        if self.booking_service.is_contact_repeat_complaint(message):
            answer = self.booking_service.contact_repeat_apology(enquiry_state)

        if is_urgent:
            urgent = self.booking_service.urgent_contact_message()
            if "+44 7414 246103" not in answer:
                answer = f"{urgent}\n\n{answer}"

        if self.booking_service.is_informational_question(message) and enquiry_state.status != EnquiryStatus.COMPLETE:
            answer = self.booking_service.strip_enquiry_upsell(answer)
            closing = self.booking_service.informational_closing()
            if "add this to your" not in answer.lower() and closing.lower() not in answer.lower():
                answer = f"{answer.rstrip()}\n\n{closing}"

        if enquiry_state.status == EnquiryStatus.COMPLETE:
            # One clean handover: structured summary only (no stacked closings).
            answer = self.booking_service.unified_handover_message(enquiry_state)
        else:
            # Enforce KB grounding for high-risk factual / capability questions.
            answer = self.grounding_service.ensure_answer_covers_grounding(message, answer)

        answer = self.booking_service.strip_redundant_closings(answer)
        answer = strip_code_from_reply(answer)

        self.conversation_store.append_message(conversation_id, "user", message)
        self.conversation_store.append_message(conversation_id, "assistant", answer)

        return ChatResponse(
            answer=answer,
            conversation_id=conversation_id,
            sources=sources,
        )

    def _generate_response(
        self,
        message: str,
        context: str,
        history: str,
        enquiry_context: str,
    ) -> str:
        user_prompt = RAG_USER_PROMPT_TEMPLATE.format(
            context=context or "No relevant knowledge base context retrieved.",
            history=history or "No previous messages.",
            message=message,
        )
        if enquiry_context:
            user_prompt += f"\n\nENQUIRY STATE:\n{enquiry_context}"

        return self.gemini_client.generate(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=0.2,
        )

    def _build_retrieval_query(
        self,
        message: str,
        history: list[dict[str, str]],
    ) -> str:
        recent = history[-4:]
        previous_user_messages = [
            item["content"] for item in recent if item["role"] == "user"
        ]
        if not previous_user_messages:
            return message
        return " ".join(previous_user_messages[-2:] + [message])

    def _format_history(self, history: list[dict[str, str]]) -> str:
        trimmed = history[-self.settings.max_history_messages :]
        lines = [f"{item['role'].title()}: {item['content']}" for item in trimmed]
        return "\n".join(lines)

    def get_conversation(self, conversation_id: str) -> list[dict[str, str]]:
        return self.conversation_store.get_messages(conversation_id)
