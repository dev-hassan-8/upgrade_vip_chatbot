from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from app.ingestion.loader import LoadedDocument

SECTION_HEADER = re.compile(r"^=+\s*(.+?)\s*=+$", re.MULTILINE)
TRIGGER_PREFIX = "This section answers:"
URL_PATTERN = re.compile(r"https?://[^\s)]+")


@dataclass
class TextChunk:
    text: str
    source: str
    section: str
    chunk_index: int
    document_type: str
    metadata: dict


def chunk_document(
    document: LoadedDocument,
    chunk_size: int,
    chunk_overlap: int,
) -> list[TextChunk]:
    sections = _split_sections(document.text)
    chunks: list[TextChunk] = []
    chunk_index = 0

    for section_title, section_body in sections:
        section_text = _format_section(section_title, section_body)
        section_chunks = _split_with_overlap(
            section_text,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

        for part in section_chunks:
            chunks.append(
                TextChunk(
                    text=part,
                    source=document.source,
                    section=section_title,
                    chunk_index=chunk_index,
                    document_type=document.document_type,
                    metadata={
                        "source": document.source,
                        "section": section_title,
                        "chunk_index": chunk_index,
                        "document_type": document.document_type,
                        "reference_url": _extract_reference_url(section_body),
                        "service_category": _infer_service_category(section_title),
                    },
                )
            )
            chunk_index += 1

    return chunks


def _split_sections(text: str) -> list[tuple[str, str]]:
    matches = list(SECTION_HEADER.finditer(text))
    if not matches:
        return [("General", text.strip())]

    sections: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        title = match.group(1).strip()
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        sections.append((title, text[start:end].strip()))
    return sections


def _format_section(title: str, body: str) -> str:
    return f"=== {title} ===\n{body}".strip()


def _split_with_overlap(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    if len(text) <= chunk_size:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = max(end - chunk_overlap, start + 1)
    return chunks


def _extract_reference_url(section_body: str) -> str:
    match = URL_PATTERN.search(section_body)
    return match.group(0) if match else ""


def _infer_service_category(section_title: str) -> str:
    title = section_title.lower()
    if "bot capabilities" in title or "booking information" in title:
        return "booking_capabilities"
    if "global availability" in title or "featured airports" in title:
        return "airport_coverage"
    if "travel delight" in title or "terms & conditions" in title or "terms and conditions" in title:
        return "travel_delight_guarantee"
    if "mission" in title and "guarantee" in title:
        return "mission_guarantee"
    if "airport vip" in title or "meet & greet" in title or "who uses" in title:
        return "airport_vip"
    if "transfer" in title or "chauffeur" in title or "transportation" in title:
        return "airport_transfer"
    if "contact" in title or "reach us" in title:
        return "contact"
    if "privacy" in title or "gdpr" in title or "copyright" in title:
        return "legal"
    if "service" in title:
        return "services"
    if "about upgradevip" in title or "brand" in title or "partnership" in title:
        return "company"
    return "general"


def stable_chunk_id(source: str, chunk_index: int) -> str:
    stem = Path(source).stem
    safe_stem = re.sub(r"[^a-zA-Z0-9_-]+", "_", stem).strip("_").lower()
    return f"{safe_stem}_chunk_{chunk_index:03d}"
