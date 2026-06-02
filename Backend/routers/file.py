from fastapi_restful.cbv import cbv
from pydantic import BaseModel

import models

from sqlalchemy.orm import Session
from fastapi.params import Depends

from database import get_db
from fastapi import APIRouter
from routers.base import BaseAPI

router = APIRouter(prefix="/files", tags=["Files"])

# Pydentic Schemas
class FileCreate(BaseModel):
    pass

class UserResponse(BaseModel):
    pass


@cbv(router)
class FileAPI(BaseAPI):

    db: Session = Depends(get_db())

    @router.post("/")
    def create_user(self,name:UserCreate):
        pass
    @router.get("/{user_id}", response_model=UserResponse)
    def get_user(self, user_id: int):
        self.get_or_404(self.db, models.DBUser, user_id)


