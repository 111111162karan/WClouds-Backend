from fastapi import APIRouter, HTTPException
from fastapi_restful.cbv import cbv
from pydantic import BaseModel
from sqlalchemy.orm import Session
from fastapi.params import Depends
from typing import Optional

import os as _os
import models
from database import get_db
from routers.auth import get_current_user_id
from routers.base import BaseAPI, sanitize_name, safe_header_value
from datetime import datetime
import io
import zipfile
from urllib.parse import quote, unquote

router = APIRouter(prefix="/directories", tags=["Directories"])



class DirectoryCreate(BaseModel):
    name: str
    parent_id: Optional[int] = None
    owner_id: int


def add_folder_to_zip(zf: zipfile.ZipFile, db: Session, folder: models.DBFolder, prefix: str):
    files = db.query(models.DBFile).filter(models.DBFile.folder_id == folder.id).all()
    for f in files:
        path = db.query(models.DBPath).filter(models.DBPath.id == f.path_id).first()
        if path and _os.path.exists(path.path):
            with open(path.path, "rb") as enc_file:
                encrypted = enc_file.read()
            zf.writestr(f"{prefix}{f.name}", encrypted)
            # AI Agent: nonce ist im Model nullable - zipfile.writestr
            # akzeptiert kein None, daher Fallback auf leeren String.
            zf.writestr(f"{prefix}{f.name}.nonce", f.nonce or "")  # ← Nonce separat

            # AI Agent: nach dem Umbau auf Envelope-Encryption braucht der
            # Client auch den gewrappten DEK, sonst kann nach einem
            # Ordner-Download niemand mehr etwas entschluesseln. Ordner sind
            # aktuell nicht teilbar (nur der Owner laedt seine eigenen
            # Ordner herunter), daher reicht der Key-Eintrag des Datei-Owners.
            key_entry = db.query(models.DBFileKey).filter(
                models.DBFileKey.file_id == f.id,
                models.DBFileKey.user_id == f.owner_id
            ).first()
            zf.writestr(f"{prefix}{f.name}.key", key_entry.wrapped_key if key_entry else "")

    subfolders = db.query(models.DBFolder).filter(models.DBFolder.parent_id == folder.id).all()
    for sub in subfolders:
        add_folder_to_zip(zf, db, sub, f"{prefix}{sub.name}/")

def delete_folder_recursive(db: Session, folder: models.DBFolder):
    files = db.query(models.DBFile).filter(models.DBFile.folder_id == folder.id).all()
    for f in files:
        db_path = db.query(models.DBPath).filter(models.DBPath.id == f.path_id).first()
        owner = db.query(models.DBUser).filter(models.DBUser.id == f.owner_id).first()
        if db_path and _os.path.exists(db_path.path):
            if owner:
                from routers.file import GB
                owner.used_storage = max(0.0, owner.used_storage - _os.path.getsize(db_path.path) / GB)
            _os.remove(db_path.path)
        db.query(models.DBAccess).filter(models.DBAccess.file_id == f.id).delete()
        db.query(models.DBFileKey).filter(models.DBFileKey.file_id == f.id).delete()
        db.delete(f)
        if db_path:
            db.delete(db_path)

    for sub in db.query(models.DBFolder).filter(models.DBFolder.parent_id == folder.id).all():
        delete_folder_recursive(db, sub)

    folder_path = db.query(models.DBPath).filter(models.DBPath.id == folder.path_id).first()
    db.delete(folder)
    if folder_path:
        db.delete(folder_path)


def get_folder_size(db: Session, folder: models.DBFolder) -> float:
    total = 0.0
    files = db.query(models.DBFile).filter(models.DBFile.folder_id == folder.id).all()
    for f in files:
        path = db.query(models.DBPath).filter(models.DBPath.id == f.path_id).first()
        if path and _os.path.exists(path.path):
            total += _os.path.getsize(path.path)
    subfolders = db.query(models.DBFolder).filter(models.DBFolder.parent_id == folder.id).all()
    for sub in subfolders:
        total += get_folder_size(db, sub) * 1024 * 1024  # zurück zu bytes
    return round(total / (1024 * 1024), 3)

# KI | Prompt: gib mir im backend also bei den python das fertige directory.py
def build_directory_tree(db: Session, folder: models.DBFolder) -> dict:
    sub_folders = db.query(models.DBFolder).filter(
        models.DBFolder.parent_id == folder.id
    ).all()

    files = db.query(models.DBFile).filter(
        models.DBFile.owner_id == folder.owner_id,
        (models.DBFile.folder_id == folder.id) | (models.DBFile.folder_id == None)
        if folder.parent_id is None  # nur bei Root
        else models.DBFile.folder_id == folder.id
    ).all()

    return {
        "ID": folder.id,
        "Name": folder.name,
        "SubDirectories": [
            build_directory_tree(db, sub) for sub in sub_folders
        ],
        "Content": [
            {
                "ID": f.id,
                "FileName": _os.path.splitext(f.name)[0],
                "Extension": _os.path.splitext(f.name)[1]
            }
            for f in files
        ]
    }


@cbv(router)
class DirectoryAPI(BaseAPI):

    db: Session = Depends(get_db)
    requester_id: int = Depends(get_current_user_id)

    @router.get("/{user_id}")
    def get_directory(self, user_id: int):
        self.require_self(self.requester_id, user_id)

        root = (
            self.db.query(models.DBFolder)
            .filter(
                models.DBFolder.owner_id == user_id,
                models.DBFolder.parent_id == None  # noqa: E711
            )
            .first()
        )

        if not root:
            # Auto-create the root folder for this user on first access
            root_path = models.DBPath(path=f"/home/user{user_id}/")
            self.db.add(root_path)
            self.db.commit()
            self.db.refresh(root_path)

            root = models.DBFolder(
                name="Root",
                owner_id=user_id,
                path_id=root_path.id,
                parent_id=None
            )
            self.db.add(root)
            self.db.commit()
            self.db.refresh(root)

        return build_directory_tree(self.db, root)

    @router.get("/root/{user_id}")
    def get_root_directory(self, user_id: int):
        self.require_self(self.requester_id, user_id)

        root = self.db.query(models.DBFolder).filter(
            models.DBFolder.owner_id == user_id,
            models.DBFolder.parent_id == None
        ).first()
        if not root:
            raise HTTPException(status_code=404, detail="No root folder found")
        return build_directory_tree(self.db, root)

    # KI | Prompt: gib mir im backend also bei den python das fertige directory.py
    @router.post("/")
    def create_directory(self, body: DirectoryCreate):
        self.require_self(self.requester_id, body.owner_id)

        safe_name = sanitize_name(body.name)
        if body.parent_id:
            parent = self.require_folder_owner(self.db, body.parent_id, self.requester_id)
            parent_path = self.db.query(models.DBPath).filter(
                models.DBPath.id == parent.path_id
            ).first()
            new_path_str = f"{parent_path.path}{safe_name}/"
        else:
            new_path_str = f"/home/user{body.owner_id}/"

        new_path = models.DBPath(path=new_path_str)
        self.db.add(new_path)
        self.db.commit()
        self.db.refresh(new_path)

        # AI Agent: Ordnername kam bisher ungeprueft vom Client - ein Name
        # wie "../../etc" haette beim Zip-Download (Zip-Slip) und in der
        # gespeicherten path-Spalte Probleme machen koennen.
        new_folder = models.DBFolder(
            name=safe_name,
            owner_id=body.owner_id,
            path_id=new_path.id,
            parent_id=body.parent_id
        )
        self.db.add(new_folder)
        self.db.commit()
        self.db.refresh(new_folder)

        folder_history = models.DBFolderHistory(
            size=0.0,
            date=datetime.utcnow(),
            user_id=body.owner_id,
            folder_id=new_folder.id,
            path=new_path.id
        )
        self.db.add(folder_history)
        self.db.commit()

        return {"ID": new_folder.id, "Name": new_folder.name, "SubDirectories": [], "Content": []}



    @router.get("/info/{directory_id}")
    def get_directory_info(self, directory_id: int):
        folder = self.require_folder_owner(self.db, directory_id, self.requester_id)
        size = get_folder_size(self.db, folder)

        owner = self.db.query(models.DBUser).filter(models.DBUser.id == folder.owner_id).first()
        owner_email = owner.email if owner else str(folder.owner_id)

        last_history = (
            self.db.query(models.DBFolderHistory)
            .filter(models.DBFolderHistory.folder_id == folder.id)
            .order_by(models.DBFolderHistory.date.desc())
            .first()
        )
        changed_date = last_history.date.date().isoformat() if last_history and last_history.date else None
        changed_time = last_history.date.strftime("%H:%M") if last_history and last_history.date else None
        changed_user = (
            self.db.query(models.DBUser).filter(models.DBUser.id == last_history.user_id).first()
            if last_history else None
        )
        changed_user_email = changed_user.email if changed_user else owner_email

        return {
            "Name": folder.name,
            "Owner": owner_email,
            "ChangedUser": changed_user_email,
            "ChangedDate": changed_date,
            "ChangedTime": changed_time,
            "Size": size
        }

    @router.delete("/{directory_id}")
    def delete_directory(self, directory_id: int):
        folder = self.require_folder_owner(self.db, directory_id, self.requester_id)
        if folder.parent_id is None:
            raise HTTPException(status_code=400, detail="Root folder cannot be deleted")
        delete_folder_recursive(self.db, folder)
        self.db.commit()
        return {"message": "deleted"}

    @router.get("/download/{directory_id}")
    def download_directory(self, directory_id: int):
        folder = self.require_folder_owner(self.db, directory_id, self.requester_id)

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            add_folder_to_zip(zf, self.db, folder, "")

        zip_buffer.seek(0)
        from fastapi.responses import StreamingResponse
        # AI Agent: folder.name landete bisher 1:1 in den Headern - ein
        # Name mit Zeichen ausserhalb von Latin-1 (z.B. Emoji, kyrillisch,
        # japanisch) liess StreamingResponse mit einem UnicodeEncodeError
        # abstuerzen.
        safe_name = safe_header_value(folder.name)
        return StreamingResponse(
            zip_buffer,
            media_type="application/zip",
            headers={"Content-Disposition": f"attachment; filename={safe_name}.zip",
                     "X-Folder-Name": safe_name}
        )