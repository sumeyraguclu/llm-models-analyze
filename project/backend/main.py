import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from database import Base, engine
import models  # noqa: F401 — ORM tablolarını metadata'ya kaydet (AnalysisJob dahil)
from routers import agent, analyze, datasets, ingest, jobs, plans, preview, profile


Base.metadata.create_all(bind=engine)


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    engine.dispose()


app = FastAPI(title="AutoML Agent API", version="0.1.0", lifespan=lifespan)

_cors_raw = os.getenv("CORS_ORIGINS", "http://localhost:5173")
_cors_origins = [o.strip() for o in _cors_raw.split(",") if o.strip()] or ["http://localhost:5173"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ingest.router, tags=["ingest"])
app.include_router(plans.router, tags=["plans"])
app.include_router(profile.router, tags=["profile"])
app.include_router(preview.router, tags=["preview"])
app.include_router(agent.router, tags=["agent"])
app.include_router(analyze.router, tags=["analyze"])
app.include_router(datasets.router, tags=["datasets"])
app.include_router(jobs.router, tags=["jobs"])


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ready")
def ready():
    """Veritabanına TCP bağlantısı + basit sorgu (orchestrator / k8s readiness)."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(status_code=503, detail={"status": "not_ready", "message": str(exc)}) from exc
    return {"status": "ready"}
