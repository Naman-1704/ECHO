# Backend — Setup & Run Guide (M1 + M2 scope)

This covers everything up through Week 3-5 of the project timeline: auth, ingestion,
embeddings, extraction, and a working RAG chat endpoint. Graph DB / query routing
(Week 4-5 "advanced" layer) is noted as a next step at the bottom — this version
uses vector-only retrieval, which is a fully valid MVP on its own.

## 0. Prerequisites
- Python 3.11+ (no Docker, no database server needed — SQLite + ChromaDB are both just local files/folders)
- A Google Cloud project with Gmail API + Drive API enabled, OAuth credentials created
  (see the step-by-step card in chat, or Google's OAuth docs) with redirect URI
  `http://localhost:8000/auth/callback`
- [Ollama](https://ollama.com) installed locally, with the model pulled:
  ```bash
  ollama pull qwen2.5:7b-instruct
  ```
  (use `phi3.5` instead if your machine has under ~8GB free RAM)
- Before running the app, sanity-check the local model works:
  ```bash
  cd backend && python scripts/test_local_llm.py
  ```

## 1. Set up your Python environment
```bash
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## 2. Configure environment variables
```bash
cp .env.example .env
```
Fill in `.env` with your real `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, and a random
`SECRET_KEY` (e.g. `python3 -c "import secrets; print(secrets.token_hex(32))"`).
`DATABASE_URL`, `OLLAMA_BASE_URL`, and `OLLAMA_MODEL` already default correctly if you
followed the prerequisites above — only change them if you used a different model name.

## 3. Run the API
```bash
uvicorn app.main:app --reload --port 8000
```
On first run this creates `kt_dashboard.db` (a SQLite file, for chunk text/metadata)
and a `chroma_db/` folder (ChromaDB's persisted vector index) in the `backend/` folder
— nothing to install or start separately. Visit
` http://localhost:8000/health ` — you should see `{"status": "ok"}`.
Visit `http://localhost:8000/docs` for interactive API docs (FastAPI auto-generates this).

## 4. Test the OAuth login flow
Open `http://localhost:8000/auth/login` in a browser. You'll be sent through Google's
consent screen (make sure you're added as a test user on the OAuth consent screen if
the app is still in "Testing" mode) and redirected back with a session token appended
to the frontend URL. Copy that token — you'll use it as a Bearer token for the next steps.

## 5. Trigger a test ingestion sync
```bash
curl -X POST http://localhost:8000/ingestion/sync \
  -H "Authorization: Bearer YOUR_SESSION_TOKEN" \
  -H "Content-Type: application/json"
```
This pulls your 50 most recent Gmail messages, filters out anything matching the
redaction rules, chunks + embeds + extracts facts from the rest, and stores everything.
Expect this to take a few minutes the first time — one local model call per chunk for
extraction, which is the slowest step (see the local-model notes further down).

Check it worked:
```bash
sqlite3 kt_dashboard.db "SELECT count(*) FROM chunks;"
```
(if `sqlite3` isn't installed as a CLI tool, just open `kt_dashboard.db` with a GUI
tool like DB Browser for SQLite instead)

## 6. Ask a question
```bash
curl -X POST http://localhost:8000/chat/ask \
  -H "Authorization: Bearer YOUR_SESSION_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"question": "What projects am I taking over?"}'
```
You should get back an `answer` grounded in your actual inbox, plus a `sources` list
pointing at the raw items it pulled from.

## 7. Where to go next (matches Week 4-7 of the timeline)
- **Drive connector**: same pattern as `gmail_connector.py` — use `googleapiclient` with
  the Drive API's `files.list` / `files.export` (for Google Docs) or `files.get` (for
  binary files), then feed results through the same chunking/embedding/extraction path.
- **Graph layer + query router**: add a `graph/` module, extract relationships from
  `extracted` JSON already stored on each `Chunk`, and write a `query_router.py` that
  decides "who worked on X"-style questions should hit the graph instead of vector search.
- **Handover report export**: aggregate `Chunk.extracted` JSON per user into a PDF/doc —
  this can reuse everything already stored, no new ingestion needed.
- **Move ingestion to Celery**: once you're testing with real full-size mailboxes instead
  of `max_results=50`, synchronous ingestion will hit request timeouts — swap
  `run_gmail_ingestion` to a Celery task and add a status-polling endpoint.
- **Testing**: `scripts/seed_test_data.py` and `tests/` are scaffolded but empty — Week 3
  is a good time for M4 to start writing extraction/chat accuracy tests against this.

## Notes on running a local model instead of a hosted API
- Extraction and chat both go through `app/ai/llm_client.py`, which calls Ollama's local
  API — nothing leaves your machine, and there's no per-call cost, which matters since
  extraction runs once per chunk across potentially thousands of emails.
- `force_json=True` in `extraction.py` uses Ollama's JSON-constrained generation mode.
  This matters more for local 7B-class models than it would for a large hosted model —
  without it, expect noticeably more parse failures (stray prose around the JSON).
- Expect extraction to be slower than a hosted API, especially on CPU-only machines
  (roughly 5-15 tokens/sec for a 7B model). For a full ingestion run of hundreds of
  emails, budget real time for this — it's a good candidate to move to a background
  job (see Celery note below) even before you hit production mailbox volumes.
- If a teammate has a GPU (even a modest one, 6GB+ VRAM), running Ollama on their
  machine and pointing `OLLAMA_BASE_URL` at it over the local network will be
  dramatically faster than CPU-only — worth doing before your Week 6 evaluation runs.

## Notes on what's intentionally simplified for MVP speed
- Extraction runs synchronously, one model call per chunk — fine at `max_results=50`,
  will need batching/async for full mailbox volume.
- No Alembic migrations yet — `Base.metadata.create_all()` is fine until your schema
  stabilizes, then switch to Alembic before the schema changes get risky to manage by hand.
- Session tokens are passed via URL query param after OAuth for simplicity — switch to
  an httpOnly cookie before this touches any real data.
- Chunk text/metadata lives in SQLite; embeddings live in ChromaDB — two datastores
  linked by chunk id. `ingestion/jobs.py` has a comment on the specific failure mode
  this creates (a crash mid-ingestion could leave a vector in Chroma with no matching
  SQLite row) and what to do about it if it ever matters at your scale.
