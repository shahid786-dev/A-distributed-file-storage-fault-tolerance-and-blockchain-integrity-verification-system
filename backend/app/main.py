"""
BlockStore-5 coordinator backend (FastAPI).

Run locally:   uvicorn app.main:app --port 8000      (from the backend/ folder)
API docs:      http://localhost:8000/docs
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import auth, blockchain, dashboard, files, nodes, simulation
from .config import CORS_ORIGINS, ENABLE_MONITOR
from .database import db
from .services import health_monitor

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    db.log_event("info", "node", "Coordinator started")
    if ENABLE_MONITOR:
        health_monitor.start()
    yield
    health_monitor.stop()


app = FastAPI(
    title="BlockStore-5 Coordinator API",
    version="1.0",
    description="Distributed file storage across five nodes with SHA-256 integrity checks and an "
                "educational majority-vote ledger. Simulation endpoints are TEST operations.",
    lifespan=lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"],
                   expose_headers=["X-BlockStore-Source-Node", "X-BlockStore-Verified-SHA256",
                                   "X-BlockStore-Skipped"])

for router in (auth.router, dashboard.public_router, dashboard.router, files.router, nodes.router,
               blockchain.router, simulation.router):
    app.include_router(router)
