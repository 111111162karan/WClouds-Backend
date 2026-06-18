from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Float, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from database import Base


class DBUser(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String)
    password = Column(String)
    last_login = Column(DateTime)
    # AI Agent: war Integer - Dateigroessen in GB sind fast immer
    # Bruchzahlen (z.B. 0.003 GB), mit Integer wurde jede Quota-Buchung
    # auf 0 abgeschnitten und das Limit damit nie erreicht.
    used_storage = Column(Float, default=0)     # in Gigabytes
    storage_plan = Column(Integer)              # in Gigabytes
    # AI Agent: RSA-Public-Key des Accounts fuer Envelope-Encryption beim
    # Sharing - Public Keys sind per Definition unkritisch, daher kein
    # nullable=False-Zwang (alte/Test-User ohne Key bleiben moeglich).
    public_key = Column(Text, nullable=True)


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
    # AI Agent: member_id war ein nackter Integer ohne ForeignKey - das
    # erlaubte verwaiste/falsche Eintraege (Share an nicht-existierende
    # User-ID) ohne jede DB-seitige Garantie.
    member_id = Column(Integer, ForeignKey("users.id"), index=True)
    file_id = Column(Integer, ForeignKey("files.id"))
    can_read = Column(Boolean, default=False)
    can_write = Column(Boolean, default=False)


# AI Agent: Neue Tabelle fuer Envelope-Encryption. Pro Datei wird ein
# zufaelliger Data-Encryption-Key (DEK) erzeugt, der Inhalt wird damit
# AES-GCM-verschluesselt. Der DEK selbst wird hier PRO BERECHTIGTEM USER
# (inklusive Owner!) mit dessen RSA-Public-Key gewrappt abgelegt - ohne den
# Owner-Eintrag koennte der Owner seine eigene Datei nie wieder entschluesseln,
# weil der rohe DEK sonst nirgends dauerhaft existiert.
class DBFileKey(Base):
    __tablename__ = "file_keys"
    __table_args__ = (UniqueConstraint("file_id", "user_id", name="uq_file_key_file_user"),)

    id = Column(Integer, primary_key=True, index=True)
    file_id = Column(Integer, ForeignKey("files.id"), index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    wrapped_key = Column(Text)


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