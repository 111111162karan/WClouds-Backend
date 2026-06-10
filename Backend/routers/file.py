from fastapi_restful.cbv import cbv
from fastapi.responses import FileResponse as FastAPIFileResponse  # KI
from pydantic import BaseModel

import models
import os

from sqlalchemy.orm import Session
from fastapi.params import Depends

from database import get_db
from fastapi import APIRouter, UploadFile, File, HTTPException, Form  # KI | Prompt: die dateien die gespeichert werden

from routers.auth import verify_api_key
# sollen auch verschlüsselt werden und erklär mir dann
                                                # wie es funktioniert

from routers.base import BaseAPI

router = APIRouter(prefix="/files", tags=["Files"])

# KI | Prompt: die dateien die gespeichert werden
# sollen auch verschlüsselt werden und erklär mir dann
# wie es funktioniert
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


class FileResponse(BaseModel):
    id: int
    name: str
    owner_id: int
    nonce: str | None = None  # KI: Nonce-Feld hinzugefügt

    class Config:
        from_attributes = True  # KI


@cbv(router)
class FileAPI(BaseAPI):

    db: Session = Depends(get_db)
    api_key: str = Depends(verify_api_key)

    @router.post("/")
    def upload_file(
        self,
        owner_id: int = Form(...),
        nonce: str = Form(...),
        folder_id: int = Form(None),
        original_name: str = Form(...),
        uploaded_file: UploadFile = File(...)
                                                # KI | Prompt: die dateien die gespeichert werden
                                                # sollen auch verschlüsselt werden und erklär mir dann
                                                # wie es funktioniert

    ):
        # KI | Prompt: die dateien die gespeichert werden
        # sollen auch verschlüsselt werden und erklär mir dann
        # wie es funktioniert
        encrypted_data = uploaded_file.file.read()
        user_upload_dir = os.path.join(UPLOAD_DIR, str(owner_id))
        os.makedirs(user_upload_dir, exist_ok=True)
        save_path = os.path.join(user_upload_dir, f"{uploaded_file.filename}.enc")
        with open(save_path, "wb") as f:
            f.write(encrypted_data)

        db_path = models.DBPath(path=save_path)
        self.db.add(db_path)
        self.db.commit()
        self.db.refresh(db_path)

        db_file = models.DBFile(
            name=original_name,
            owner_id=owner_id,
            path_id=db_path.id,
            folder_id=folder_id,
            nonce=nonce                      # KI
        )
        self.db.add(db_file)
        self.db.commit()
        self.db.refresh(db_file)

        return {"message": "uploaded", "file_id": db_file.id}  # KI | Prompt: die dateien die gespeichert werden
                                                # sollen auch verschlüsselt werden und erklär mir dann
                                                # wie es funktioniert

    # KI | Prompt: die dateien die gespeichert werden
    # sollen auch verschlüsselt werden und erklär mir dann
    # wie es funktioniert
    @router.get("/download/{file_id}")
    def download_file(self, file_id: int):
        db_file = self.db.query(models.DBFile).filter(models.DBFile.id == file_id).first()
        if not db_file:
            raise HTTPException(status_code=404, detail="File not found")

        db_path = self.db.query(models.DBPath).filter(models.DBPath.id == db_file.path_id).first()
        if not db_path or not os.path.exists(db_path.path):
            raise HTTPException(status_code=404, detail="File not found on disk")

        return FastAPIFileResponse(
            path=db_path.path,
            media_type="application/octet-stream",
            filename=db_file.name + ".enc",
            headers={"X-Nonce": db_file.nonce}
        )

    @router.get("/{user_id}", response_model=list[FileResponse])
    def get_user_files(self, user_id: int):
        files = self.db.query(models.DBFile)\
            .filter(models.DBFile.owner_id == user_id)\
            .all()
        return files

    @router.get("/info/{file_id}", response_model=FileResponse)
    def get_file_info(self, file_id: int):
        file = self.db.query(models.DBFile).filter(models.DBFile.id == file_id).first()
        if not file:
            raise HTTPException(status_code=404, detail="File not found")
        return file

    # KI | Prompt: die dateien die gespeichert werden
    # sollen auch verschlüsselt werden und erklär mir dann
    # wie es funktioniert
    @router.delete("/{file_id}")
    def delete_file(self, file_id: int):
        db_file = self.db.query(models.DBFile).filter(models.DBFile.id == file_id).first()
        if not db_file:
            raise HTTPException(status_code=404, detail="File not found")

        db_path = self.db.query(models.DBPath).filter(models.DBPath.id == db_file.path_id).first()

        if db_path and os.path.exists(db_path.path):
            os.remove(db_path.path)

        self.db.delete(db_file)
        if db_path:
            self.db.delete(db_path)
        self.db.commit()

        return {"message": "deleted"}