import base64

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

    @router.get("/by-email/{email}", response_model=UserResponse)
    def get_user_by_email(self, email: str):
        user = self.db.query(models.DBUser).filter(models.DBUser.email == email).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return user

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

        try:
            decoded_key = base64.b64decode(user.storage_plan_key).decode("utf-8").strip()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid storage plan key encoding")

        stored_plan = (
            self.db.query(models.DBStoragePlanKeys)
            .filter(models.DBStoragePlanKeys.key == decoded_key)
            .first()
        )
        if not stored_plan:
            raise HTTPException(status_code=401, detail="Invalid storage plan key")

        if stored_plan.redeemed:
            raise HTTPException(status_code=409, detail="Storage plan key already redeemed")

        existing_user = (
            self.db.query(models.DBUser)
            .filter(models.DBUser.email == user.email)
            .first()
        )
        if existing_user:
            raise HTTPException(status_code=409, detail="Email already registered")

        # The client sends a SHA-256 hex digest; hash it once more with bcrypt
        # so the DB never stores a raw or single-hashed value.
        new_user = models.DBUser(
            email=user.email,
            password=password_hash.hash(user.password),
            last_login=datetime.datetime.now(),
            storage_plan=int(stored_plan.storage),
        )
        self.db.add(new_user)
        self.db.commit()
        self.db.refresh(new_user)

        stored_plan.redeemed = True
        self.db.commit()

        db_path = models.DBPath(path=f"/home/user{new_user.id}/")
        self.db.add(db_path)
        self.db.commit()
        self.db.refresh(db_path)

        root_folder = models.DBFolder(
            name="Root",
            owner_id=new_user.id,
            path_id=db_path.id,
            parent_id=None
        )
        self.db.add(root_folder)
        self.db.commit()

        raise HTTPException(status_code=201, detail="User created")

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

