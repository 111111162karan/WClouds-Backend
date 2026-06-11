from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Float
from sqlalchemy.orm import relationship

from database import Base


class DBUser(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String)
    password = Column(String)
    last_login = Column(DateTime)
    used_storage = Column(Integer, default=0)   # in Gigabytes
    storage_plan = Column(Integer)              # in Gigabytes


class DBFile(Base):
    __tablename__ = "files"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    owner_id = Column(Integer, ForeignKey("users.id"))
    path_id = Column(Integer, ForeignKey("path.id"))
    folder_id = Column(Integer, ForeignKey("folders.id"), nullable=True)
    nonce = Column(String, nullable=True)       # KI | Prompt: die dateien die gespeichert werden
                                                # sollen auch verschlüsselt werden und erklär mir dann
                                                # wie es funktioniert


class DBFolder(Base):
    __tablename__ = "folders"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    owner_id = Column(Integer, ForeignKey("users.id"))
    path_id = Column(Integer, ForeignKey("path.id"))
    parent_id = Column(Integer, ForeignKey("folders.id"), nullable=True)


class DBPath(Base):
    __tablename__ = "path"

    id = Column(Integer, primary_key=True, index=True)
    path = Column(String)


class DBAccess(Base):
    __tablename__ = "access"

    access_id = Column(Integer, primary_key=True, index=True)
    member_id = Column(Integer, index=True)
    file_id = Column(Integer, ForeignKey("files.id"))
    can_read = Column(Boolean, default=False)
    can_write = Column(Boolean, default=False)


class DBFileHistory(Base):
    __tablename__ = "file_history"

    backup_file_id = Column(Integer, primary_key=True, index=True)
    size = Column(Float)    # in Gigabytes
    date = Column(DateTime)
    user_id = Column(Integer, ForeignKey("users.id"))
    file_id = Column(Integer, ForeignKey("files.id"))
    path = Column(ForeignKey("path.id"))


class DBFolderHistory(Base):
    __tablename__ = "folder_history"

    backup_file_id = Column(Integer, primary_key=True, index=True)
    size = Column(Float)    # in Gigabytes
    date = Column(DateTime)
    user_id = Column(Integer, ForeignKey("users.id"))
    folder_id = Column(Integer, ForeignKey("folders.id"))
    path = Column(ForeignKey("path.id"))


class DBStoragePlanKeys(Base):
    __tablename__ = "subscription_keys"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String)
    storage = Column(Integer)   # in Gigabytes
    redeemed = Column(Boolean)