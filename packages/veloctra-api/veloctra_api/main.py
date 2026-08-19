"""
veloctra_api/main.py
===================
FastAPI main application entry point for Veloctra Data Platform.
"""

from __future__ import annotations

import logging
import sys
import traceback
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from veloctra_core.settings import get_settings
from veloctra_security.security import sanitize_config
from veloctra_api import (
    routes_auth, routes_config, routes_pipelines, routes_projects, routes_rbac, routes_observability, routes_data_crud, websocket
)




settings = get_settings()

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("veloctra_api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("[Startup] Initialising Veloctra Engine…")
    try:
        await routes_pipelines.init_pipeline_resources()
    except Exception as exc:
        logger.warning("[Startup] Pipeline resources init warning: %s", exc)
    yield
    logger.info("[Shutdown] Draining connections…")
    try:
        await routes_pipelines.shutdown_pipeline_resources()
    except Exception as exc:
        logger.warning("[Shutdown] Pipeline resources cleanup warning: %s", exc)


app = FastAPI(
    title="Veloctra Data Platform API",
    description="Enterprise Stream Extraction, Vectorised Transformation, and Multi-Database ETL Platform",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins if isinstance(settings.cors_origins, list) else [settings.cors_origins],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    detail = sanitize_config({"error": str(exc), "type": type(exc).__name__})
    logger.error("Unhandled exception: %s\n%s", exc, traceback.format_exc())
    return JSONResponse(
        status_code=500,
        content={"detail": detail["error"], "type": detail["type"]},
    )


app.include_router(routes_auth.router)
app.include_router(routes_config.router)
app.include_router(routes_pipelines.router)
app.include_router(routes_projects.router)
app.include_router(routes_rbac.router)
app.include_router(routes_observability.router)
app.include_router(routes_data_crud.router)
app.include_router(websocket.router)




@app.get("/health", tags=["System"])
async def health():
    return {"status": "ok", "app": "Veloctra Data Platform", "version": "1.0.0"}


# ── Static Files & React SPA UI ───────────────────────────────────────────────────

_ui_dist = Path(__file__).parent / "ui" / "dist"
if not _ui_dist.exists():
    _ui_dist = Path(__file__).parent.parent.parent.parent / "apps" / "management-ui" / "dist"


if (_ui_dist / "assets").exists():
    app.mount("/assets", StaticFiles(directory=_ui_dist / "assets"), name="assets")


@app.get("/favicon.svg", include_in_schema=False)
@app.get("/favicon.ico", include_in_schema=False)
async def serve_favicon():
    favicon_file = _ui_dist / "favicon.svg"
    if not favicon_file.exists():
        favicon_file = Path(__file__).parent.parent.parent.parent / "apps" / "management-ui" / "public" / "favicon.svg"
    if favicon_file.exists():
        return FileResponse(favicon_file, media_type="image/svg+xml")
    return JSONResponse({"detail": "Not Found"}, status_code=404)


@app.get("/{full_path:path}", include_in_schema=False)
async def serve_react_app(request: Request, full_path: str):
    if full_path.startswith("api/") or full_path.startswith("auth/") or full_path.startswith("pipelines/") or full_path.startswith("configs/") or full_path.startswith("projects/") or full_path.startswith("rbac/") or full_path.startswith("data/") or full_path.startswith("ws/"):

        return JSONResponse({"detail": "Not Found"}, status_code=404)
    dist_index = _ui_dist / "index.html"
    if dist_index.exists():
        return FileResponse(dist_index)
    return JSONResponse({"status": "Veloctra Engine API active", "ui": "build React UI in apps/management-ui"})



