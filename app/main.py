import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes_health import router as health_router
from app.config import get_settings

settings = get_settings()
logging.basicConfig(level=getattr(logging, str(settings.log_level).upper(), logging.INFO))
logger = logging.getLogger(__name__)

app = FastAPI(
    title="UpgradeVIP Chatbot API",
    description="Production-ready UpgradeVIP customer service chatbot with RAG.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)


def _include_router(label: str, import_name: str) -> None:
    try:
        module = __import__(import_name, fromlist=["router"])
        app.include_router(module.router)
    except Exception:
        logger.exception("Failed to load %s routes", label)


_include_router("chat", "app.api.routes_chat")
_include_router("documents", "app.api.routes_documents")
_include_router("conversations", "app.api.routes_conversations")

frontend_dir = settings.project_root / "frontend"
if frontend_dir.exists():
    app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")


@app.get("/", response_model=None)
def serve_frontend():
    index_path = frontend_dir / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return HTMLResponse("<h1>UpgradeVIP Chatbot</h1><p>Frontend files were not bundled.</p>")
