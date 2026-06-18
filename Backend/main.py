from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from sqlalchemy import text

from database import engine
import models
from routers import user, file, directory, sharing
from scheduler import start_scheduler, stop_scheduler

# Tabellen anlegen (falls noch nicht vorhanden)
models.Base.metadata.create_all(bind=engine)

# Inline-Migration: deletion_warning_sent-Spalte zu bestehenden DBs hinzufügen
with engine.connect() as _conn:
    try:
        _conn.execute(text("ALTER TABLE users ADD COLUMN deletion_warning_sent DATETIME"))
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

app.include_router(user.router)
app.include_router(file.router)
app.include_router(directory.router)
app.include_router(sharing.router)


@app.get("/")
def root():
    return {"message": "Hello to my World\n Besuche /docs für die Swagger-UI"}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
