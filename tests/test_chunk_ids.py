from app.ingestion.chunker import stable_chunk_id


def test_stable_chunk_id_format() -> None:
    assert stable_chunk_id("upgradevip_details.txt", 0) == "upgradevip_details_chunk_000"
    assert stable_chunk_id("upgradevip_details.txt", 12) == "upgradevip_details_chunk_012"
