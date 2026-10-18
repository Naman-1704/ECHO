from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db.session import init_db
from app.auth.routes import router as auth_router
from app.api.routes_ingestion import router as ingestion_router
from app.api.routes_chat import router as chat_router
from app.api.routes_dashboard import router as dashboard_router
from app.api.routes_graph import router as graph_router
from app.api.routes_reports import router as reports_router

app = FastAPI(title="Echo API — Employee Context & Handoff Orchestrator")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(ingestion_router)
app.include_router(chat_router)
app.include_router(dashboard_router)
app.include_router(graph_router)
app.include_router(reports_router)


@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/health")
def health():
    return {"status": "ok"}
