from fastapi_restful.cbv import cbv
from fastapi.responses import FileResponse as FastAPIFileResponse  # KI
from pydantic import BaseModel
from datetime import datetime
import uuid

import models
import os

from sqlalchemy.orm import Session
from fastapi.params import Depends



from database import get_db
from fastapi import APIRouter, UploadFile, File, HTTPException, Form  # KI | Prompt: die dateien die gespeichert werden

from routers.auth import get_current_user_id
# sollen auch verschlüsselt werden und erklär mir dann
                                                # wie es funktioniert

from routers.base import BaseAPI, sanitize_name

GB = 1024 ** 3

router = APIRouter(prefix="/files", tags=["Files"])

# KI | Prompt: die dateien die gespeichert werden
# sollen auch verschlüsselt werden und erklär mir dann
# wie es funktioniert
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


class FileResponse(BaseModel):
    id: int
    name: str
    owner_id: int
    nonce: str | None = None  # KI: Nonce-Feld hinzugefügt

    class Config:
        from_attributes = True  # KI


@cbv(router)
class FileAPI(BaseAPI):

    db: Session = Depends(get_db)
    requester_id: int = Depends(get_current_user_id)

    @router.post("/")
    def upload_file(
        self,
        nonce: str = Form(...),
        folder_id: int = Form(None),
        original_name: str = Form(...),
        # AI Agent: Client generiert pro Datei einen zufaelligen DEK,
        # verschluesselt damit den Inhalt und wrapped denselben DEK direkt
        # fuer sich selbst (Owner) mit dem eigenen Public Key. Ohne das
        # waere der rohe DEK nach dem Upload fuer immer verloren.
        wrapped_key_for_owner: str = Form(...),
        uploaded_file: UploadFile = File(...)
                                                # KI | Prompt: die dateien die gespeichert werden
                                                # sollen auch verschlüsselt werden und erklär mir dann
                                                # wie es funktioniert

    ):
        # Owner wird ausschließlich aus dem API-Key abgeleitet, niemals aus
        # Client-Daten - sonst könnte ein User Dateien im Namen eines
        # anderen Users hochladen, nur indem er ein anderes owner_id-Feld
        # mitsendet.
        owner_id = self.requester_id

        # Wenn in einen bestimmten Ordner hochgeladen wird, muss der
        # Ordner auch wirklich dem Uploader gehören.
        if folder_id is not None:
            self.require_folder_owner(self.db, folder_id, self.requester_id)

        encrypted_data = uploaded_file.file.read()

        # AI Agent: Quota-Check - bisher konnte jeder User beliebig viel
        # hochladen, unabhaengig vom gebuchten storage_plan.
        owner = self.get_or_404(self.db, models.DBUser, owner_id)
        size_gb = len(encrypted_data) / GB
        if owner.used_storage + size_gb > owner.storage_plan:
            raise HTTPException(status_code=413, detail="Speicherlimit erreicht")

        user_upload_dir = os.path.join(UPLOAD_DIR, str(owner_id))
        os.makedirs(user_upload_dir, exist_ok=True)

        # AI Agent: Speicherdateiname kam bisher direkt vom Client
        # (original_name) - damit waren Path-Traversal ("../../etc/passwd")
        # und gegenseitiges Ueberschreiben gleichnamiger Dateien moeglich.
        # Eine UUID ist vom Original-Dateinamen unabhaengig; der Anzeigename
        # wird weiterhin sanitisiert in db_file.name gespeichert.
        disk_filename = f"{uuid.uuid4().hex}.enc"
        save_path = os.path.join(user_upload_dir, disk_filename)
        with open(save_path, "wb") as f:
            f.write(encrypted_data)

        db_path = models.DBPath(path=save_path)
        self.db.add(db_path)
        self.db.commit()
        self.db.refresh(db_path)

        display_name = sanitize_name(original_name)
        db_file = models.DBFile(
            name=display_name,
            owner_id=owner_id,
            path_id=db_path.id,
            folder_id=folder_id,
            nonce=nonce                      # KI
        )
        self.db.add(db_file)

        # AI Agent: used_storage wurde beim Upload nie automatisch erhoeht,
        # nur ueber den separaten (und bisher mit dem Frontend nicht
        # uebereinstimmenden) /updateusedstorage-Endpoint.
        owner.used_storage += size_gb

        self.db.commit()
        self.db.refresh(db_file)

        # AI Agent: Owner-Eintrag in der Key-Tabelle - der wird beim
        # Download/Overwrite gebraucht, um den DEK ueberhaupt wieder
        # entpacken zu koennen.
        owner_key = models.DBFileKey(
            file_id=db_file.id,
            user_id=owner_id,
            wrapped_key=wrapped_key_for_owner
        )
        self.db.add(owner_key)
        self.db.commit()

        history = models.DBFileHistory(
            size=size_gb,
            date=datetime.utcnow(),
            user_id=owner_id,
            file_id=db_file.id,
            path=db_path.id,
            nonce=nonce
        )
        self.db.add(history)
        if folder_id is not None:
            folder_history = models.DBFolderHistory(
                size=size_gb,
                date=datetime.utcnow(),
                user_id=owner_id,
                folder_id=folder_id,
                path=db_path.id
            )
            self.db.add(folder_history)
        self.db.commit()

        # AI Agent: Response-Format an das vom Frontend erwartete
        # SavedFile-Objekt {ID, FileName, Extension} angepasst - vorher kam
        # {"message": "uploaded", "file_id": ...} zurueck, das beim
        # Deserialisieren in SavedFile nur leere/0-Werte ergeben haette.
        return {
            "ID": db_file.id,
            "FileName": os.path.splitext(display_name)[0],
            "Extension": os.path.splitext(display_name)[1]
        }

    # KI | Prompt: die dateien die gespeichert werden
    # sollen auch verschlüsselt werden und erklär mir dann
    # wie es funktioniert
    @router.get("/download/{file_id}")
    def download_file(self, file_id: int):
        db_file = self.require_file_access(self.db, file_id, self.requester_id, write=False)

        db_path = self.db.query(models.DBPath).filter(models.DBPath.id == db_file.path_id).first()
        if not db_path or not os.path.exists(db_path.path):
            raise HTTPException(status_code=404, detail="File not found on disk")

        # AI Agent: nonce ist im Model nullable, HTTP-Header dürfen aber
        # keinen None-Wert haben - sonst wirft Starlette hier einen Fehler.
        return FastAPIFileResponse(
            path=db_path.path,
            media_type="application/octet-stream",
            filename=db_file.name + ".enc",
            headers={"X-Nonce": db_file.nonce or ""}
        )

    # AI Agent: liefert dem Requester seinen eigenen gewrappten DEK fuer
    # diese Datei. Lesezugriff reicht, weil auch read-only-Grantees zum
    # Entschluesseln einen Key brauchen - require_file_access(write=False)
    # laesst sowohl reine Leser als auch Schreiber durch.
    @router.get("/{file_id}/key")
    def get_file_key(self, file_id: int):
        self.require_file_access(self.db, file_id, self.requester_id, write=False)

        key_entry = self.db.query(models.DBFileKey).filter(
            models.DBFileKey.file_id == file_id,
            models.DBFileKey.user_id == self.requester_id
        ).first()
        if not key_entry:
            # Zugriff besteht laut DBAccess/Owner-Check, aber kein Key
            # vorhanden - das ist ein Dateninkonsistenz-Fall (z.B. Share
            # ist beim Schreiben des Keys fehlgeschlagen), kein normaler
            # 403-Fall.
            raise HTTPException(status_code=404, detail="Kein Schluessel fuer diese Datei gefunden")

        return {"wrapped_key": key_entry.wrapped_key}

    @router.get("/{user_id}", response_model=list[FileResponse])
    def get_user_files(self, user_id: int):
        self.require_self(self.requester_id, user_id)
        files = self.db.query(models.DBFile)\
            .filter(models.DBFile.owner_id == user_id)\
            .all()
        return files

    # AI Agent: Es gab bisher KEINEN Endpoint, um den Inhalt einer
    # existierenden Datei zu ersetzen (nur Create/Read/Delete) - "can_write"
    # wurde nur fuer DELETE geprueft. Wichtig: der DEK bleibt UNVERAENDERT
    # (kein Re-Wrap fuer alle Berechtigten noetig), nur ein frischer Nonce
    # pro Verschluesselung - das ist mit AES-GCM korrekt und sicher.
    @router.put("/{file_id}")
    def overwrite_file(
        self,
        file_id: int,
        nonce: str = Form(...),
        uploaded_file: UploadFile = File(...)
    ):
        db_file = self.require_file_access(self.db, file_id, self.requester_id, write=True)
        owner = self.db.query(models.DBUser).filter(models.DBUser.id == db_file.owner_id).first()
        old_db_path = self.db.query(models.DBPath).filter(models.DBPath.id == db_file.path_id).first()

        old_file_path = old_db_path.path if old_db_path else None
        old_nonce = db_file.nonce
        old_size_gb = os.path.getsize(old_file_path) / GB if old_file_path and os.path.exists(old_file_path) else 0.0

        encrypted_data = uploaded_file.file.read()
        new_size_gb = len(encrypted_data) / GB

        # AI Agent: Quota-Check zulasten des OWNERS (nicht des Requesters)
        projected_usage = owner.used_storage - old_size_gb + new_size_gb
        if projected_usage > owner.storage_plan:
            raise HTTPException(status_code=413, detail="Speicherlimit erreicht")

        # Altes File in Backup-Verzeichnis verschieben (nicht löschen)
        backup_dir = os.path.join(UPLOAD_DIR, "backup", str(db_file.owner_id))
        os.makedirs(backup_dir, exist_ok=True)
        backup_path = os.path.join(backup_dir, f"{uuid.uuid4().hex}.enc")
        if old_file_path and os.path.exists(old_file_path):
            os.rename(old_file_path, backup_path)
            if old_db_path:
                old_db_path.path = backup_path  # altes DBPath zeigt jetzt auf Backup

        # Neues File schreiben + neues DBPath anlegen
        user_upload_dir = os.path.join(UPLOAD_DIR, str(db_file.owner_id))
        os.makedirs(user_upload_dir, exist_ok=True)
        new_save_path = os.path.join(user_upload_dir, f"{uuid.uuid4().hex}.enc")
        with open(new_save_path, "wb") as f:
            f.write(encrypted_data)

        new_db_path = models.DBPath(path=new_save_path)
        self.db.add(new_db_path)
        self.db.flush()

        db_file.path_id = new_db_path.id
        db_file.nonce = nonce
        owner.used_storage = max(0.0, projected_usage)
        self.db.commit()

        # History-Eintrag für neue Version
        history = models.DBFileHistory(
            size=new_size_gb,
            date=datetime.utcnow(),
            user_id=self.requester_id,
            file_id=file_id,
            path=new_db_path.id,
            nonce=nonce
        )
        self.db.add(history)
        if db_file.folder_id is not None:
            self.db.add(models.DBFolderHistory(
                size=new_size_gb,
                date=datetime.utcnow(),
                user_id=self.requester_id,
                folder_id=db_file.folder_id,
                path=new_db_path.id
            ))
        self.db.commit()

        return {"message": "overwritten", "file_id": db_file.id}

    @router.get("/info/{file_id}")
    def get_file_info(self, file_id: int):
        file = self.require_file_access(self.db, file_id, self.requester_id, write=False)

        db_path = self.db.query(models.DBPath).filter(models.DBPath.id == file.path_id).first()
        size_mb = 0.0
        if db_path and os.path.exists(db_path.path):
            size_mb = round(os.path.getsize(db_path.path) / (1024 * 1024), 3)

        owner = self.db.query(models.DBUser).filter(models.DBUser.id == file.owner_id).first()
        owner_email = owner.email if owner else str(file.owner_id)

        last_history = (
            self.db.query(models.DBFileHistory)
            .filter(models.DBFileHistory.file_id == file.id)
            .order_by(models.DBFileHistory.date.desc())
            .first()
        )
        changed_date = last_history.date.date().isoformat() if last_history and last_history.date else None
        changed_time = last_history.date.strftime("%H:%M") if last_history and last_history.date else None
        changed_user = (
            self.db.query(models.DBUser).filter(models.DBUser.id == last_history.user_id).first()
            if last_history else None
        )
        changed_user_email = changed_user.email if changed_user else owner_email

        return {
            "Name": file.name,
            "Owner": owner_email,
            "ChangedUser": changed_user_email,
            "ChangedDate": changed_date,
            "ChangedTime": changed_time,
            "Size": size_mb
        }

    @router.get("/history/{history_id}/download")
    def download_history_backup(self, history_id: int):
        h = self.db.query(models.DBFileHistory).filter(
            models.DBFileHistory.backup_file_id == history_id
        ).first()
        if not h:
            raise HTTPException(status_code=404, detail="History-Eintrag nicht gefunden")

        self.require_file_access(self.db, h.file_id, self.requester_id, write=False)

        if not h.path or not h.nonce:
            raise HTTPException(status_code=404, detail="Kein Backup für diesen Eintrag vorhanden")

        db_path = self.db.query(models.DBPath).filter(models.DBPath.id == h.path).first()
        if not db_path or not os.path.exists(db_path.path):
            raise HTTPException(status_code=404, detail="Backup-Datei nicht auf Disk gefunden")

        return FastAPIFileResponse(
            path=db_path.path,
            media_type="application/octet-stream",
            filename="backup.enc",
            headers={"X-Nonce": h.nonce}
        )

    @router.get("/{file_id}/history")
    def get_file_history(self, file_id: int):
        self.require_file_access(self.db, file_id, self.requester_id, write=False)

        entries = (
            self.db.query(models.DBFileHistory)
            .filter(models.DBFileHistory.file_id == file_id)
            .order_by(models.DBFileHistory.date.desc())
            .all()
        )

        result = []
        for h in entries:
            user = self.db.query(models.DBUser).filter(models.DBUser.id == h.user_id).first()
            db_path = self.db.query(models.DBPath).filter(models.DBPath.id == h.path).first() if h.path else None
            has_backup = bool(h.nonce and db_path and os.path.exists(db_path.path))
            result.append({
                "HistoryId": h.backup_file_id,
                "Date": h.date.date().isoformat() if h.date else None,
                "Time": h.date.strftime("%H:%M") if h.date else None,
                "SizeMb": round(h.size * 1024, 3) if h.size else 0.0,
                "ChangedUser": user.email if user else str(h.user_id),
                "HasBackup": has_backup
            })
        return result

    # KI | Prompt: die dateien die gespeichert werden
    # sollen auch verschlüsselt werden und erklär mir dann
    # wie es funktioniert
    @router.delete("/{file_id}")
    def delete_file(self, file_id: int):
        db_file = self.require_file_access(self.db, file_id, self.requester_id, write=True)

        db_path = self.db.query(models.DBPath).filter(models.DBPath.id == db_file.path_id).first()

        # AI Agent: Gegenstueck zum Quota-Tracking beim Upload - sonst
        # bliebe used_storage nach dem Loeschen einer Datei dauerhaft zu hoch.
        owner = self.db.query(models.DBUser).filter(models.DBUser.id == db_file.owner_id).first()
        if db_path and os.path.exists(db_path.path) and owner:
            size_gb = os.path.getsize(db_path.path) / GB
            owner.used_storage = max(0.0, owner.used_storage - size_gb)

        if db_path and os.path.exists(db_path.path):
            os.remove(db_path.path)

        # AI Agent: DBAccess- und DBFileKey-Zeilen fuer diese Datei wurden
        # beim Loeschen bisher nie aufgeraeumt - verwaiste Eintraege blieben
        # zurueck (insb. bei DBFileKey jetzt auch sicherheitsrelevant, falls
        # eine neue Datei je dieselbe file_id wiederverwenden wuerde).
        self.db.query(models.DBAccess).filter(models.DBAccess.file_id == file_id).delete()
        self.db.query(models.DBFileKey).filter(models.DBFileKey.file_id == file_id).delete()

        self.db.delete(db_file)
        if db_path:
            self.db.delete(db_path)
        self.db.commit()

        return {"message": "deleted"}