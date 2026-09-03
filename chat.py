#!/usr/bin/env python3
"""Interactive CLI for the UpgradeVIP RAG chatbot."""

import argparse

from rag.rag_pipeline import RAGPipeline


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ask questions against the UpgradeVIP knowledge base."
    )
    parser.add_argument("question", nargs="?", help="Single question to ask")
    parser.add_argument(
        "--show-sources",
        action="store_true",
        help="Print retrieved knowledge sections",
    )
    args = parser.parse_args()

    pipeline = RAGPipeline()

    if args.question:
        _handle_question(pipeline, args.question, args.show_sources)
        return

    print("UpgradeVIP RAG chatbot")
    print("Type 'exit' or 'quit' to stop.\n")

    while True:
        try:
            question = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            break

        if not question:
            continue
        if question.lower() in {"exit", "quit"}:
            print("Goodbye.")
            break

        _handle_question(pipeline, question, args.show_sources)
        print()


def _handle_question(pipeline: RAGPipeline, question: str, show_sources: bool) -> None:
    response = pipeline.ask(question)
    print(f"\nAssistant: {response.answer}")

    if show_sources and response.sources:
        print("\nSources:")
        for source in response.sources:
            title = source.get("title", "Unknown")
            print(f"- {title}")


if __name__ == "__main__":
    main()
