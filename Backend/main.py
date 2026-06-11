import uvicorn
from fastapi import FastAPI
from database import engine
import models
from routers import user, file, directory, sharing

# Einstiegspunkt
# erstellt alle Tabellen in der Datenbank (falls nicht existent)

models.Base.metadata.create_all(bind=engine)


app = FastAPI(title="WClouds", description="Self hosted Cloud Service!", version="1.0.0")

app.include_router(user.router)
app.include_router(file.router)
app.include_router(directory.router)
app.include_router(sharing.router)
@app.get("/")
def root():
    return {"message": "Hello to my World\n Besuche /docs für die Swagger-UI"}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)