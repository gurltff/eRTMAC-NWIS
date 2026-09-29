"""eRTMAC NWIS – Nearby Wells Intelligence System (prototype API)."""
import asyncio
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from . import models as m
from .config import CORS_ORIGINS, REPO_DIR
from .db import Base, SessionLocal, engine
from .routers import admin, auth, documents, driller, map as map_router, tracking, wells
from .services import ml, spatial
from .services.tracking import drilling_simulator_loop, simulators

FRONTEND_DIST = REPO_DIR / "frontend" / "dist"


def _ensure_data():
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        empty = db.query(m.Well).count() == 0
    if empty:  # first run: fill the database with sample data
        from seed.seed import seed
        seed()
    with SessionLocal() as db:
        spatial.refresh(db)


@asynccontextmanager
async def lifespan(_: FastAPI):
    _ensure_data()
    # Train the models in the background so the API is usable immediately.
    threading.Thread(target=ml.get_models, daemon=True).start()
    task = asyncio.create_task(drilling_simulator_loop())
    yield
    task.cancel()
    for uid in list(simulators.tasks):
        simulators.stop(uid)


app = FastAPI(title="eRTMAC NWIS API", version="0.1.0", lifespan=lifespan,
              description="Offset well knowledge and decision support – prototype running on SAMPLE data.")
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_credentials=False, allow_methods=["*"], allow_headers=["*"])

for r in (auth.router, driller.router, admin.router, tracking.router, wells.router, map_router.router, documents.router):
    app.include_router(r)


@app.get("/api/health")
def health():
    return {"ok": True, "models_ready": "risk" in ml._state}


# Serve the built frontend (npm run build) from the same process, if present.
if FRONTEND_DIST.exists():
    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        target = FRONTEND_DIST / path
        if path and target.is_file() and FRONTEND_DIST in target.resolve().parents:
            return FileResponse(target)
        return FileResponse(FRONTEND_DIST / "index.html")
