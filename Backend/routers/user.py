from fastapi import HTTPException
import routers.auth as authenticator
from fastapi_restful.cbv import cbv
from pydantic import BaseModel
import datetime
import models
from pwdlib import PasswordHash

from sqlalchemy.orm import Session
from fastapi.params import Depends

from database import get_db
from fastapi import APIRouter

from routers.auth import verify_api_key
from routers.base import BaseAPI

router = APIRouter(prefix="/user", tags=["User"])

# Pydentic Schemas
class UserCreate(BaseModel):
    email: str
    password: str
    storage_plan_key: str

class UserResponse(BaseModel):
    id: int
    email : str
    storage_plan: int

class UserLogin(BaseModel):
    email: str
    password: str

class UserUpdateUsedStorage(BaseModel):
    user_id: int
    used_storage: int


password_hash = PasswordHash.recommended()

@cbv(router)
class UserAPI(BaseAPI):
    db: Session = Depends(get_db)
    api_key : str = Depends(verify_api_key)



    @router.get("/{user_id}", response_model=UserResponse)
    def get_user(self, user_id: int):
        return self.get_or_404(self.db, models.DBUser, user_id)

    @router.patch("/updateusedstorage/{user_id}")
    def update_used_storage(self, user_id: int, body: UserUpdateUsedStorage):
        db_user = self.get_or_404(self.db, models.DBUser, user_id)
        db_user.used_storage = body.used_storage
        self.db.commit()
        self.db.refresh(db_user)
        raise HTTPException(status_code=200, detail="Used storage updated")

    @router.patch("/updatelogin/{user_id}")
    def update_last_login(self, user_id: int):
        db_user = self.get_or_404(self.db, models.DBUser, user_id)
        db_user.last_login = datetime.datetime.now()
        self.db.commit()
        self.db.refresh(db_user)
        raise HTTPException(status_code=200, detail="Last login updated")

@cbv(router)
class UserLoginAPI(BaseAPI):
    db: Session = Depends(get_db)
    @router.post("/register")
    def create_user(self, user: UserCreate):


        print("KEY:", user.storage_plan_key)
        stored_plan = self.db.query(models.DBStoragePlanKeys).filter(models.DBStoragePlanKeys.key == user.storage_plan_key).first()
        if stored_plan:
            existing_user = self.db.query(models.DBUser).filter(models.DBUser.email == user.email).first()
            if existing_user:
                raise HTTPException(status_code=409, detail="Email already registered")
            today = datetime.datetime.now()
            new_user = models.DBUser(
                email=user.email,
                password=password_hash.hash(user.password),
                last_login=today,
                storage_plan=int(stored_plan.storage)
            )
            self.db.add(new_user)
            self.db.commit()
            self.db.refresh(new_user)
            stored_plan.redeemed = True
            self.db.commit()
            raise HTTPException(status_code=201, detail="User created")
        else:
            raise HTTPException(status_code=401, detail="Invalid storage plan key")

    @router.post("/login")
    def login_user(self, user: UserLogin):
        db_user = self.db.query(models.DBUser).filter(models.DBUser.email == user.email).first()
        if db_user and password_hash.verify(user.password, db_user.password):
            session_key = authenticator.create_api_key(db_user.id)
            db_user.last_login = datetime.datetime.now()
            self.db.commit()
            self.db.refresh(db_user)
            return {"session_key": session_key, "user_id": db_user.id}
        else:
            raise HTTPException(status_code=401, detail="Invalid email or password")

