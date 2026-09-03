from app.ingestion.chunker import chunk_document
from app.ingestion.loader import LoadedDocument, clean_text


def test_clean_text_normalises_blank_lines() -> None:
    text = clean_text("Hello\n\n\n\nWorld")
    assert text == "Hello\n\nWorld"


def test_chunk_document_preserves_sections() -> None:
    document = LoadedDocument(
        source="upgradevip_details.txt",
        text=(
            "=== Airport VIP Services ===\n"
            "This section answers: airport vip, vip service\n"
            "Premium airport experience including meet and greet."
        ),
        document_type="txt",
        metadata={"filename": "upgradevip_details.txt"},
    )

    chunks = chunk_document(document, chunk_size=800, chunk_overlap=100)
    assert len(chunks) >= 1
    assert chunks[0].section == "Airport VIP Services"
    assert "Premium airport experience" in chunks[0].text
