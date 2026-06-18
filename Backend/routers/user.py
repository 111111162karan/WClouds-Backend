import base64

from fastapi import HTTPException
import routers.auth as authenticator
from fastapi_restful.cbv import cbv
from pydantic import BaseModel, ConfigDict, Field
import datetime
import models
from pwdlib import PasswordHash

GB = 1024 ** 3

from sqlalchemy.orm import Session
from fastapi.params import Depends

from database import get_db
from fastapi import APIRouter

from routers.base import BaseAPI

import re

router = APIRouter(prefix="/user", tags=["User"])


# Copied from Website
def is_valid_email(email):

    """Check if the email is a valid format."""

    # Regular expression for validating an Email

    # AI Agent: alte Regex erlaubte nur einen Trennzeichen im lokalen Teil
    # und keine Großbuchstaben, dadurch wurden gültige Adressen wie
    # "John.Doe@gmail.com" oder "a.b.c@gmail.com" fälschlich abgelehnt.
    regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'

    # If the string matches the regex, it is a valid email

    if re.match(regex, email):

        return True

    else:

        return False

# Pydentic Schemas
class UserCreate(BaseModel):
    email: str
    password: str
    storage_plan_key: str
    # AI Agent: RSA-Public-Key (Base64 von ExportSubjectPublicKeyInfo) fuer
    # echtes E2E-Sharing - wird einmalig bei der Registrierung gesetzt,
    # niemals beim Login ueberschrieben (sonst wuerden alle bestehenden,
    # fuer den alten Key gewrappten DEKs unbrauchbar).
    public_key: str


class UserResponse(BaseModel):
    id: int
    email: str
    storage_plan: int
    # AI Agent: bewusst oeffentlich abrufbar - Public Keys sind per
    # Definition unkritisch, jeder eingeloggte User braucht sie zum Sharen.
    public_key: str | None = None


class UserLogin(BaseModel):
    email: str
    password: str


# AI Agent: das Frontend schickt PATCH /user/updateusedstorage (ohne
# user_id im Pfad) mit Body {"UserID": int, "usedBytes": long} - die alten
# Feldnamen/Pfad passten nicht zu dem, was die WPF-App tatsaechlich sendet.
class UserUpdateUsedStorage(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    user_id: int = Field(alias="UserID")
    used_bytes: int = Field(alias="usedBytes")


# AI Agent: Frontend schickt PATCH /user/updatelogin (ohne user_id im Pfad)
# mit Body {"email": str, "lastLogin": datetime} statt wie bisher
# erwartet /user/updatelogin/{user_id} ohne Body.
class UserUpdateLogin(BaseModel):
    email: str
    lastLogin: datetime.datetime | None = None


password_hash = PasswordHash.recommended()


@cbv(router)
class UserAPI(BaseAPI):
    db: Session = Depends(get_db)
    requester_id: int = Depends(authenticator.get_current_user_id)

    @router.get("/by-email/{email}", response_model=UserResponse)
    def get_user_by_email(self, email: str):
        user = self.db.query(models.DBUser).filter(models.DBUser.email == email).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return user

    @router.get("/{user_id}", response_model=UserResponse)
    def get_user(self, user_id: int):
        self.require_self(self.requester_id, user_id)
        return self.get_or_404(self.db, models.DBUser, user_id)

    # AI Agent: Pfad und Body an das tatsaechliche Frontend-Verhalten
    # angepasst (vorher /updateusedstorage/{user_id} ohne Body-Match) und
    # raise HTTPException(200, ...) durch ein echtes return ersetzt -
    # eine raised HTTPException fuer einen Erfolgsfall ist ein Anti-Pattern
    # und liefert nur {"detail": "..."} statt eines brauchbaren Bodys.
    @router.patch("/updateusedstorage")
    def update_used_storage(self, body: UserUpdateUsedStorage):
        self.require_self(self.requester_id, body.user_id)
        db_user = self.get_or_404(self.db, models.DBUser, body.user_id)
        db_user.used_storage = body.used_bytes / GB
        self.db.commit()
        self.db.refresh(db_user)
        return {"message": "Used storage updated", "used_storage": db_user.used_storage}

    # AI Agent: Pfad und Body an das tatsaechliche Frontend-Verhalten
    # angepasst (vorher /updatelogin/{user_id} ohne Body). Der vom Client
    # gesendete lastLogin-Zeitstempel wird bewusst ignoriert - die
    # Server-Zeit ist die verlaessliche Quelle, ein Client koennte sonst
    # einen beliebigen Zeitstempel faelschen.
    @router.patch("/updatelogin")
    def update_last_login(self, body: UserUpdateLogin):
        db_user = self.db.query(models.DBUser).filter(models.DBUser.email == body.email).first()
        if not db_user:
            raise HTTPException(status_code=404, detail="User not found")
        self.require_self(self.requester_id, db_user.id)
        db_user.last_login = datetime.datetime.now()
        db_user.deletion_warning_sent = None  # Warnung zurücksetzen wenn User wieder aktiv
        self.db.commit()
        self.db.refresh(db_user)
        return {"message": "Last login updated"}

    # AI Agent: es gab eine delete_api_key()-Funktion im auth-Modul, die
    # aber nirgends aufgerufen wurde - kein Logout-Endpoint existierte.
    @router.post("/logout")
    def logout(self):
        authenticator.delete_api_key(self.requester_id)
        return {"message": "Logged out"}


@cbv(router)
class UserLoginAPI(BaseAPI):
    db: Session = Depends(get_db)

    # AI Agent: status_code jetzt am Decorator statt per raise
    # HTTPException(201, ...) im Erfolgsfall (Anti-Pattern, siehe unten).
    @router.post("/register", status_code=201)
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

        # The client sends an SHA-256 hex digest; hash it once more with bcrypt
        # so the DB never stores a raw or single-hashed value.
        # Email check:
        if is_valid_email(user.email) == False:
            raise HTTPException(status_code=400, detail="Invalid email syntax")

        # AI Agent: Minimal-Validierung des Public Keys - ohne das scheitert
        # Sharing erst viel spaeter mit einem kryptischen RSA-Parsing-Fehler
        # beim Empfaenger statt mit einer klaren 400 hier beim Registrieren.
        try:
            decoded_public_key = base64.b64decode(user.public_key, validate=True)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid public key encoding")
        if len(decoded_public_key) < 100:
            raise HTTPException(status_code=400, detail="Invalid public key")

        new_user = models.DBUser(
            email=user.email,
            password=password_hash.hash(user.password),
            last_login=datetime.datetime.now(),
            storage_plan=int(stored_plan.storage),
            public_key=user.public_key,
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

        return {"id": new_user.id, "email": new_user.email, "storage_plan": new_user.storage_plan}

    @router.post("/login")
    def login_user(self, user: UserLogin):
        db_user = self.db.query(models.DBUser).filter(models.DBUser.email == user.email).first()

        if db_user and password_hash.verify(user.password, db_user.password):
            session_key = authenticator.create_api_key(db_user.id)
            db_user.last_login = datetime.datetime.now()
            db_user.deletion_warning_sent = None  # Warnung zurücksetzen wenn User wieder aktiv
            self.db.commit()
            self.db.refresh(db_user)
            return {"session_key": session_key, "user_id": db_user.id}
        else:
            raise HTTPException(status_code=401, detail="Invalid email or password")

