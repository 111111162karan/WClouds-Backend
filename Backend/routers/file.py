from fastapi_restful.cbv import cbv
from fastapi.responses import FileResponse as FastAPIFileResponse  # KI
from pydantic import BaseModel
import uuid

import models
import os

from sqlalchemy.orm import Session
from fastapi.params import Depends



from database import get_db
from fastapi import APIRouter, UploadFile, File, HTTPException, Form  # KI | Prompt: die dateien die gespeichert werden

from routers.auth import get_current_user_id
# sollen auch verschlüsselt werden und erklär mir dann
                                                # wie es funktioniert

from routers.base import BaseAPI, sanitize_name

GB = 1024 ** 3

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
    requester_id: int = Depends(get_current_user_id)

    @router.post("/")
    def upload_file(
        self,
        nonce: str = Form(...),
        folder_id: int = Form(None),
        original_name: str = Form(...),
        uploaded_file: UploadFile = File(...)
                                                # KI | Prompt: die dateien die gespeichert werden
                                                # sollen auch verschlüsselt werden und erklär mir dann
                                                # wie es funktioniert

    ):
        # Owner wird ausschließlich aus dem API-Key abgeleitet, niemals aus
        # Client-Daten - sonst könnte ein User Dateien im Namen eines
        # anderen Users hochladen, nur indem er ein anderes owner_id-Feld
        # mitsendet.
        owner_id = self.requester_id

        # Wenn in einen bestimmten Ordner hochgeladen wird, muss der
        # Ordner auch wirklich dem Uploader gehören.
        if folder_id is not None:
            self.require_folder_owner(self.db, folder_id, self.requester_id)

        encrypted_data = uploaded_file.file.read()

        # AI Agent: Quota-Check - bisher konnte jeder User beliebig viel
        # hochladen, unabhaengig vom gebuchten storage_plan.
        owner = self.get_or_404(self.db, models.DBUser, owner_id)
        size_gb = len(encrypted_data) / GB
        if owner.used_storage + size_gb > owner.storage_plan:
            raise HTTPException(status_code=413, detail="Speicherlimit erreicht")

        user_upload_dir = os.path.join(UPLOAD_DIR, str(owner_id))
        os.makedirs(user_upload_dir, exist_ok=True)

        # AI Agent: Speicherdateiname kam bisher direkt vom Client
        # (original_name) - damit waren Path-Traversal ("../../etc/passwd")
        # und gegenseitiges Ueberschreiben gleichnamiger Dateien moeglich.
        # Eine UUID ist vom Original-Dateinamen unabhaengig; der Anzeigename
        # wird weiterhin sanitisiert in db_file.name gespeichert.
        disk_filename = f"{uuid.uuid4().hex}.enc"
        save_path = os.path.join(user_upload_dir, disk_filename)
        with open(save_path, "wb") as f:
            f.write(encrypted_data)

        db_path = models.DBPath(path=save_path)
        self.db.add(db_path)
        self.db.commit()
        self.db.refresh(db_path)

        display_name = sanitize_name(original_name)
        db_file = models.DBFile(
            name=display_name,
            owner_id=owner_id,
            path_id=db_path.id,
            folder_id=folder_id,
            nonce=nonce                      # KI
        )
        self.db.add(db_file)

        # AI Agent: used_storage wurde beim Upload nie automatisch erhoeht,
        # nur ueber den separaten (und bisher mit dem Frontend nicht
        # uebereinstimmenden) /updateusedstorage-Endpoint.
        owner.used_storage += size_gb

        self.db.commit()
        self.db.refresh(db_file)

        # AI Agent: Response-Format an das vom Frontend erwartete
        # SavedFile-Objekt {ID, FileName, Extension} angepasst - vorher kam
        # {"message": "uploaded", "file_id": ...} zurueck, das beim
        # Deserialisieren in SavedFile nur leere/0-Werte ergeben haette.
        return {
            "ID": db_file.id,
            "FileName": os.path.splitext(display_name)[0],
            "Extension": os.path.splitext(display_name)[1]
        }

    # KI | Prompt: die dateien die gespeichert werden
    # sollen auch verschlüsselt werden und erklär mir dann
    # wie es funktioniert
    @router.get("/download/{file_id}")
    def download_file(self, file_id: int):
        db_file = self.require_file_access(self.db, file_id, self.requester_id, write=False)

        db_path = self.db.query(models.DBPath).filter(models.DBPath.id == db_file.path_id).first()
        if not db_path or not os.path.exists(db_path.path):
            raise HTTPException(status_code=404, detail="File not found on disk")

        # AI Agent: nonce ist im Model nullable, HTTP-Header dürfen aber
        # keinen None-Wert haben - sonst wirft Starlette hier einen Fehler.
        return FastAPIFileResponse(
            path=db_path.path,
            media_type="application/octet-stream",
            filename=db_file.name + ".enc",
            headers={"X-Nonce": db_file.nonce or ""}
        )

    @router.get("/{user_id}", response_model=list[FileResponse])
    def get_user_files(self, user_id: int):
        self.require_self(self.requester_id, user_id)
        files = self.db.query(models.DBFile)\
            .filter(models.DBFile.owner_id == user_id)\
            .all()
        return files

    @router.get("/info/{file_id}")
    def get_file_info(self, file_id: int):
        file = self.require_file_access(self.db, file_id, self.requester_id, write=False)

        db_path = self.db.query(models.DBPath).filter(models.DBPath.id == file.path_id).first()
        size_mb = 0.0
        if db_path and os.path.exists(db_path.path):
            size_mb = round(os.path.getsize(db_path.path) / (1024 * 1024), 3)
        return {
            "Name": file.name,
            "Owner": file.owner_id,
            "ChangedUser": file.owner_id,
            "ChangedDate": None,
            "ChangedTime": None,
            "Size": size_mb
        }

    # KI | Prompt: die dateien die gespeichert werden
    # sollen auch verschlüsselt werden und erklär mir dann
    # wie es funktioniert
    @router.delete("/{file_id}")
    def delete_file(self, file_id: int):
        db_file = self.require_file_access(self.db, file_id, self.requester_id, write=True)

        db_path = self.db.query(models.DBPath).filter(models.DBPath.id == db_file.path_id).first()

        # AI Agent: Gegenstueck zum Quota-Tracking beim Upload - sonst
        # bliebe used_storage nach dem Loeschen einer Datei dauerhaft zu hoch.
        owner = self.db.query(models.DBUser).filter(models.DBUser.id == db_file.owner_id).first()
        if db_path and os.path.exists(db_path.path) and owner:
            size_gb = os.path.getsize(db_path.path) / GB
            owner.used_storage = max(0.0, owner.used_storage - size_gb)

        if db_path and os.path.exists(db_path.path):
            os.remove(db_path.path)

        self.db.delete(db_file)
        if db_path:
            self.db.delete(db_path)
        self.db.commit()

        return {"message": "deleted"}