from fastapi_restful.cbv import cbv
from pydantic import BaseModel

import models

from sqlalchemy.orm import Session
from fastapi.params import Depends

from database import get_db
from fastapi import APIRouter, HTTPException

from routers.auth import verify_api_key
from routers.base import BaseAPI


router = APIRouter(prefix="/share", tags=["Sharing"])


class ShareFileRequest(BaseModel):
    fileId: int
    memberIds: list[int]
    canRead: bool
    canWrite: bool

# KI Prompt: Please implement the ShareService routers
@cbv(router)
class SharingAPI(BaseAPI):

    db: Session = Depends(get_db)
    api_key: str = Depends(verify_api_key)

    @router.post("/file")
    def share_file(self, request: ShareFileRequest):
        # Check that the file exists
        file = self.db.query(models.DBFile).filter(models.DBFile.id == request.fileId).first()
        if not file:
            raise HTTPException(status_code=404, detail="File not found")

        # Check that all member users exist
        for member_id in request.memberIds:
            user = self.db.query(models.DBUser).filter(models.DBUser.id == member_id).first()
            if not user:
                raise HTTPException(status_code=404, detail=f"User {member_id} not found")

        # Create or update an access entry for each member
        for member_id in request.memberIds:
            existing = self.db.query(models.DBAccess).filter(
                models.DBAccess.member_id == member_id,
                models.DBAccess.file_id == request.fileId
            ).first()

            if existing:
                existing.can_read = request.canRead
                existing.can_write = request.canWrite
            else:
                access = models.DBAccess(
                    member_id=member_id,
                    file_id=request.fileId,
                    can_read=request.canRead,
                    can_write=request.canWrite
                )
                self.db.add(access)

        self.db.commit()
        return {"message": "File shared successfully", "file_id": request.fileId, "members": request.memberIds}

    @router.delete("/file/{file_id}/member/{member_id}")
    def revoke_access(self, file_id: int, member_id: int):
        access = self.db.query(models.DBAccess).filter(
            models.DBAccess.file_id == file_id,
            models.DBAccess.member_id == member_id
        ).first()

        if not access:
            raise HTTPException(status_code=404, detail="Access entry not found")

        self.db.delete(access)
        self.db.commit()
        return {"message": "Access revoked"}

    @router.get("/file/{file_id}")
    def get_file_members(self, file_id: int):
        self.get_or_404(self.db, models.DBFile, file_id)

        access_list = self.db.query(models.DBAccess).filter(
            models.DBAccess.file_id == file_id
        ).all()

        return [
            {
                "member_id": a.member_id,
                "can_read": a.can_read,
                "can_write": a.can_write
            }
            for a in access_list
        ]