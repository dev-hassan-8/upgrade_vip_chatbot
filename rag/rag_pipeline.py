from __future__ import annotations

import os
from dataclasses import dataclass

from rag.config import CONTACT_FALLBACK, TOP_K
from rag.indexer import KnowledgeIndexer
from rag.prompts import NO_CONTEXT_RESPONSE, SYSTEM_PROMPT, USER_PROMPT_TEMPLATE
from rag.retriever import KnowledgeRetriever


@dataclass
class RAGResponse:
    answer: str
    sources: list[dict]
    grounded: bool


class RAGPipeline:
    def __init__(
        self,
        retriever: KnowledgeRetriever | None = None,
        top_k: int = TOP_K,
    ) -> None:
        self.retriever = retriever or KnowledgeRetriever(KnowledgeIndexer())
        self.top_k = top_k

    def ask(self, question: str) -> RAGResponse:
        chunks = self.retriever.retrieve(question, top_k=self.top_k)
        context = self.retriever.format_context(chunks)

        if not context.strip():
            return RAGResponse(
                answer=NO_CONTEXT_RESPONSE,
                sources=[],
                grounded=False,
            )

        answer = self._generate_answer(question, context)
        return RAGResponse(answer=answer, sources=chunks, grounded=True)

    def _generate_answer(self, question: str, context: str) -> str:
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
            return self._generate_with_openai(question, context, api_key)

        return self._generate_context_only(context)

    def _generate_with_openai(
        self,
        question: str,
        context: str,
        api_key: str,
    ) -> str:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError(
                "openai package is required when OPENAI_API_KEY is set."
            ) from exc

        client = OpenAI(api_key=api_key)
        user_prompt = USER_PROMPT_TEMPLATE.format(context=context, question=question)

        response = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0,
        )
        return response.choices[0].message.content.strip()

    @staticmethod
    def _generate_context_only(context: str) -> str:
        return (
            "Based on the UpgradeVIP knowledge base:\n\n"
            f"{context}\n\n"
            f"{CONTACT_FALLBACK}"
        )
