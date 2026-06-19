from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from database import engine
import models
from routers import user, file, directory, sharing
from scheduler import start_scheduler, stop_scheduler
from logging_config import logger

# Tabellen anlegen (falls noch nicht vorhanden)
models.Base.metadata.create_all(bind=engine)

# Inline-Migrationen für bestehende DBs
with engine.connect() as _conn:
    for _stmt in [
        "ALTER TABLE users ADD COLUMN deletion_warning_sent DATETIME",
        "ALTER TABLE file_history ADD COLUMN nonce TEXT",
    ]:
        try:
            _conn.execute(text(_stmt))
            _conn.commit()
        except Exception:
            pass  # Spalte existiert bereits


@asynccontextmanager
async def lifespan(_app: FastAPI):
    start_scheduler()
    yield
    stop_scheduler()

app = FastAPI(
    title="WClouds",
    description="Self hosted Cloud Service!",
    version="1.0.0",
    lifespan=lifespan,
)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    response = await call_next(request)
    logger.info(
        "%s %s -> %s",
        request.method,
        request.url.path,
        response.status_code,
    )
    return response


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(
        "Fehler bei %s %s: %s",
        request.method,
        request.url.path,
        str(exc),
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Interner Serverfehler"},
    )

app.include_router(user.router)
app.include_router(file.router)
app.include_router(directory.router)
app.include_router(sharing.router)


@app.get("/")
def root():
    return {"message": "Hello to my World\n Besuche /docs für die Swagger-UI"}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
