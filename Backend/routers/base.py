from fastapi import HTTPException
from sqlalchemy.orm import Session
import models

class BaseAPI:

    def get_or_404(self, db: Session, model, item_id: int):
        item = db.query(model).filter(model.id == item_id).first()
        if not item:
            raise HTTPException(status_code=404, detail=f"Eintrag in"
                                                        f"'{model.__tablename__}' mit ID '{item_id}'"
                                                        f"nicht gefunden")
        return item

    # KI Start | Prompt: mir ist gerade aufgefallen ich habe im auth skript eine
    # # funktion die da ist zum schauen ob der user auch rechte auf eine datei
    # # hat bzw get user id by key oder so das soll bite bei jedem endpunkt gecheckt
    # # werden ob zb ein file auch wirklich einem user gehört etc
    def require_self(self, requester_id: int, target_user_id: int):
        """Stellt sicher, dass der eingeloggte User auch der ist, dessen
        Daten angefragt/verändert werden. Verhindert, dass User A einfach
        die user_id in der URL gegen die von User B tauscht."""
        if requester_id != target_user_id:
            raise HTTPException(status_code=403, detail="Kein Zugriff auf diesen Benutzer")

    def require_file_access(self, db: Session, file_id: int, requester_id: int, write: bool = False):
        """Lädt die Datei (404 falls nicht vorhanden) und prüft, ob
        requester_id entweder Eigentümer ist oder über die access-Tabelle
        die passenden Rechte (can_read/can_write) hat. Gibt die Datei
        zurück, wenn der Zugriff erlaubt ist, sonst 403."""
        file = self.get_or_404(db, models.DBFile, file_id)
        if file.owner_id == requester_id:
            return file

        access = db.query(models.DBAccess).filter(
            models.DBAccess.file_id == file_id,
            models.DBAccess.member_id == requester_id
        ).first()

        if not access or (write and not access.can_write) or (not write and not access.can_read):
            raise HTTPException(status_code=403, detail="Kein Zugriff auf diese Datei")

        return file

    def require_folder_owner(self, db: Session, folder_id: int, requester_id: int):
        """Lädt den Ordner (404 falls nicht vorhanden) und prüft Eigentümerschaft.
        Hinweis: Ordner haben aktuell kein eigenes Sharing-System (DBAccess
        hat nur ein file_id-Feld, kein folder_id) - deshalb hier nur ein
        Owner-Check und kein can_read/can_write wie bei Dateien."""
        folder = self.get_or_404(db, models.DBFolder, folder_id)
        if folder.owner_id != requester_id:
            raise HTTPException(status_code=403, detail="Kein Zugriff auf diesen Ordner")
        return folder
    # KI Ende
