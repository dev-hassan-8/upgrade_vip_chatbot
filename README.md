# UpgradeVIP Chatbot

Customer-service chatbot for [UpgradeVIP](https://upgradevip.com) airport VIP and transfer enquiries. It answers from the company knowledge base (RAG) and can collect booking details in conversation.

## Features

- Chat UI at `/`
- Gemini-powered replies grounded in `knowledge_base/`
- Airport VIP and transfer enquiry flow
- Health check at `/health`

## Tech stack

| Layer | Language / tech |
|---|---|
| Backend | **Python** (FastAPI, Uvicorn, Pydantic) |
| AI | **Google Gemini** (`google-genai`) |
| RAG / knowledge | In-memory retrieval (optional **ChromaDB** for local) |
| Frontend | **HTML**, **CSS**, **JavaScript** (vanilla, no React) |
| Config | `.env` via `pydantic-settings` / `python-dotenv` |
| Tests | **pytest** |
| Docs / deploy | Markdown README; Render / Uvicorn hosting |

**Languages used in this project:** Python, HTML, CSS, JavaScript.

## Requirements

- Python 3.12+ (3.14 works locally)
- A Gemini API key (`GEMINI_API_KEY`)

## Local setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and set `GEMINI_API_KEY`.

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000).

For local RAG without ChromaDB (recommended on hosts without SQLite):

```bash
set VECTOR_STORE_BACKEND=memory
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Optional local extras (Chroma + tests):

```bash
pip install -r requirements-dev.txt
pytest
```

## Environment variables

| Variable | Required | Notes |
|---|---|---|
| `GEMINI_API_KEY` | Yes | Never commit this. Set it in `.env` or the host dashboard. |
| `GEMINI_CHAT_MODEL` | No | Default `gemini-3.5-flash-lite` |
| `GEMINI_FALLBACK_CHAT_MODEL` | No | Used if the primary model fails |
| `VECTOR_STORE_BACKEND` | No | `auto`, `memory`, or `chroma`. Use `memory` on Render/Vercel. |

See `.env.example` for the full list.

## API

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Chat UI |
| `GET` | `/health` | `{"status":"ok"}` |
| `POST` | `/chat` | `{ "message": "...", "conversation_id": null }` |
| `GET` | `/conversations/{id}` | Conversation history |
| `POST` | `/documents/upload` | Ingest a `.txt`, `.pdf`, or `.docx` file |

## Deploy on Render (recommended)

Vercel serverless is a poor fit: Chroma/SQLite and long-running Python crash there. Use a normal web service.

1. Push this repo to GitHub.
2. Render → **New Web Service** → connect the repo.
3. Settings:
   - **Build command:** `pip install -r requirements.txt`
   - **Start command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
4. Add `GEMINI_API_KEY` (and optionally `VECTOR_STORE_BACKEND=memory`) as environment variables.
5. Deploy. Share the `https://….onrender.com` URL for testing.

Temporary tunnels (Cloudflare / Serveo) only work while your laptop is on. Use Render for a link your team can keep.

## Project layout

```
app/                 FastAPI app, RAG, Gemini, booking flow
frontend/            Chat UI
knowledge_base/      UpgradeVIP source text
public/              Static copy of the UI for CDN hosts
tests/
```

## Knowledge base

Edit files under `knowledge_base/` (section headers like `=== TITLE ===`). Restart the app after changes when using the memory store.
