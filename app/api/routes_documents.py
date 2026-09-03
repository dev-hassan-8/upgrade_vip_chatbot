import logging
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.config import get_settings
from app.ingestion.loader import SUPPORTED_EXTENSIONS
from app.ingestion.processor import DocumentProcessor

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/upload")
async def upload_document(file: UploadFile = File(...)) -> dict[str, int | str]:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required.")

    suffix = Path(file.filename).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file format. Supported formats: {', '.join(sorted(SUPPORTED_EXTENSIONS))}",
        )

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    try:
        processor = DocumentProcessor()
        chunk_count = processor.ingest_upload(file.filename, content)
        return {"filename": file.filename, "chunks_ingested": chunk_count}
    except RuntimeError as exc:
        logger.exception("Configuration error during document upload")
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Document upload failed")
        raise HTTPException(
            status_code=500,
            detail="Sorry, the document could not be processed.",
        ) from exc
