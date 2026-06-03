from fastapi_restful.cbv import cbv
from pydantic import BaseModel

import models
import os
import shutil

from sqlalchemy.orm import Session
from fastapi.params import Depends

from database import get_db
from fastapi import APIRouter, UploadFile, File, HTTPException

from routers.base import BaseAPI

router = APIRouter(prefix="/files", tags=["Files"])


class FileResponse(BaseModel):
    id: int
    name: str
    owner_id: int


@cbv(router)
class FileAPI(BaseAPI):

    db: Session = Depends(get_db)

    @router.post("/")
    def upload_file(uploaded_file: UploadFile = File(...)):
        with open(uploaded_file.filename, "wb") as f:
            f.write(uploaded_file.file.read())

        return {"message": "uploaded"}

    @router.get("/{user_id}")
    def get_user_files(self, user_id: int):

        files = self.db.query(models.DBFile)\
            .filter(models.DBFile.owner_id == user_id)\
            .all()

        return files

    @router.get("/info/{file_id}")
    def get_file_info(self, file_id: int):
        file = self.db.query(models.DBFile).filter(models.DBFile.id == file_id).first()
        if not file:
            raise HTTPException(status_code=404, detail="File not found")
        return file