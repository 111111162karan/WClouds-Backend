from fastapi_restful.cbv import cbv
from pydantic import BaseModel

import models

from sqlalchemy.orm import Session
from fastapi.params import Depends

from database import get_db
from fastapi import APIRouter, HTTPException

from routers.auth import get_current_user_id
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
    requester_id: int = Depends(get_current_user_id)

    @router.post("/file")
    def share_file(self, request: ShareFileRequest):
        # KI | Prompt: mir ist gerade aufgefallen ich habe im auth skript eine
        # # funktion die da ist zum schauen ob der user auch rechte auf eine datei
        # # hat bzw get user id by key oder so das soll bite bei jedem endpunkt gecheckt
        # # werden ob zb ein file auch wirklich einem user gehört etc

        # Nur der Eigentümer einer Datei darf sie teilen - sonst könnte
        # sich jeder mit gültigem API-Key selbst Zugriff auf fremde
        # Dateien geben.
        file = self.get_or_404(self.db, models.DBFile, request.fileId)
        if file.owner_id != self.requester_id:
            raise HTTPException(status_code=403, detail="Nur der Eigentümer kann eine Datei teilen")

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
        file = self.get_or_404(self.db, models.DBFile, file_id)
        if file.owner_id != self.requester_id:
            raise HTTPException(status_code=403, detail="Nur der Eigentümer kann Zugriffsrechte entziehen")

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
        file = self.get_or_404(self.db, models.DBFile, file_id)
        if file.owner_id != self.requester_id:
            raise HTTPException(status_code=403, detail="Nur der Eigentümer kann die Mitgliederliste sehen")

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

    # AI Prompt: can a user now see files if it got shared to them and if not it should make another folder on the datapage besides root called shared
    @router.get("/shared-with-me/{user_id}")
    def get_shared_with_me(self, user_id: int):
        self.require_self(self.requester_id, user_id)

        access_list = self.db.query(models.DBAccess).filter(
            models.DBAccess.member_id == user_id
        ).all()

        result = []
        for access in access_list:
            file = self.db.query(models.DBFile).filter(models.DBFile.id == access.file_id).first()
            if not file:
                continue
            import os as _os
            result.append({
                "ID": file.id,
                "FileName": _os.path.splitext(file.name)[0],
                "Extension": _os.path.splitext(file.name)[1],
                "CanRead": access.can_read,
                "CanWrite": access.can_write
            })
        return result