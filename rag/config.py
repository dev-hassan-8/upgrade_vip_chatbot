from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
KNOWLEDGE_SOURCE = PROJECT_ROOT / "upgradevip_details.txt"
CHROMA_DIR = PROJECT_ROOT / "data" / "chroma"
COLLECTION_NAME = "upgradevip_knowledge"

EMBEDDING_MODEL = "all-MiniLM-L6-v2"
TOP_K = 4

CONTACT_FALLBACK = (
    "For questions not covered in our knowledge base, contact "
    "avip@upgradevip.com or WhatsApp +44 7414 246103."
)
