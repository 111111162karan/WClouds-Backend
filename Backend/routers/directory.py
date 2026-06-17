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
from routers.base import BaseAPI
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
            zf.writestr(f"{prefix}{f.name}.nonce", f.nonce)  # ← Nonce separat

    subfolders = db.query(models.DBFolder).filter(models.DBFolder.parent_id == folder.id).all()
    for sub in subfolders:
        add_folder_to_zip(zf, db, sub, f"{prefix}{sub.name}/")

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

        if body.parent_id:
            parent = self.require_folder_owner(self.db, body.parent_id, self.requester_id)
            parent_path = self.db.query(models.DBPath).filter(
                models.DBPath.id == parent.path_id
            ).first()
            new_path_str = f"{parent_path.path}{body.name}/"
        else:
            new_path_str = f"/home/user{body.owner_id}/"

        new_path = models.DBPath(path=new_path_str)
        self.db.add(new_path)
        self.db.commit()
        self.db.refresh(new_path)

        new_folder = models.DBFolder(
            name=body.name,
            owner_id=body.owner_id,
            path_id=new_path.id,
            parent_id=body.parent_id
        )
        self.db.add(new_folder)
        self.db.commit()
        self.db.refresh(new_folder)

        return {"ID": new_folder.id, "Name": new_folder.name, "SubDirectories": [], "Content": []}



    @router.get("/info/{directory_id}")
    def get_directory_info(self, directory_id: int):
        folder = self.require_folder_owner(self.db, directory_id, self.requester_id)
        size = get_folder_size(self.db, folder)
        return {
            "Name": folder.name,
            "Owner": folder.owner_id,
            "ChangedUser": folder.owner_id,
            "ChangedDate": None,
            "ChangedTime": None,
            "Size": size
        }

    @router.get("/download/{directory_id}")
    def download_directory(self, directory_id: int):
        folder = self.require_folder_owner(self.db, directory_id, self.requester_id)

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            add_folder_to_zip(zf, self.db, folder, "")

        zip_buffer.seek(0)
        from fastapi.responses import StreamingResponse
        return StreamingResponse(
            zip_buffer,
            media_type="application/zip",
            headers={"Content-Disposition": f"attachment; filename={folder.name}.zip",
                     "X-Folder-Name": folder.name}
        )