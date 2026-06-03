from fastapi import APIRouter, HTTPException
from fastapi_restful.cbv import cbv
from pydantic import BaseModel
from sqlalchemy.orm import Session
from fastapi.params import Depends
from typing import Optional

import models
from database import get_db
from routers.auth import verify_api_key
from routers.base import BaseAPI

router = APIRouter(prefix="/directories", tags=["Directories"])

class DirectoryCreate(BaseModel):
    name: str
    parent_id: Optional[int] = None
    owner_id: int

def build_directory_tree(db: Session, folder: models.DBFolder) -> dict:
    sub_folders = db.query(models.DBFolder).filter(models.DBFolder.parent_id == folder.id).all()
    files = db.query(models.DBFile).filter(models.DBFile.path_id == folder.path_id).all()

    return {
        "ID": folder.id,
        "Name": folder.name,
        "SubDirectories": [build_directory_tree(db, sub) for sub in sub_folders],
        "Content": [
            {"ID": f.id, "FileName": f.name, "Extension": ""}
            for f in files
        ]
    }

@cbv(router)
class DirectoryAPI(BaseAPI):
    db: Session = Depends(get_db)
    api_key: str = Depends(verify_api_key)

    @router.get("/{directory_id}")
    def get_directory(self, directory_id: int):
        folder = self.get_or_404(self.db, models.DBFolder, directory_id)
        return build_directory_tree(self.db, folder)

    @router.post("/")
    def create_directory(self, body: DirectoryCreate):
        if body.parent_id:
            parent = self.get_or_404(self.db, models.DBFolder, body.parent_id)
            parent_path = self.db.query(models.DBPath).filter(models.DBPath.id == parent.path_id).first()
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

        raise HTTPException(status_code=201, detail="Directory created")