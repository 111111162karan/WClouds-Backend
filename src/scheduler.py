import os
import shutil
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler

import models
from database import SessionLocal
from email_service import send_deletion_warning

_scheduler = BackgroundScheduler(timezone="UTC")


# ── Cascade-Delete ─────────────────────────────────────────────────────────────

def _delete_user_cascade(db, user: models.DBUser) -> None:
    uid = user.id

    # File-IDs des Users (für abhängige Tabellen)
    file_ids = [
        fid for (fid,) in
        db.query(models.DBFile.id).filter(models.DBFile.owner_id == uid).all()
    ]

    # History-Einträge (referenzieren Files/Folders → zuerst löschen)
    db.query(models.DBFileHistory).filter(models.DBFileHistory.user_id == uid).delete()
    db.query(models.DBFolderHistory).filter(models.DBFolderHistory.user_id == uid).delete()

    # Geteilte Zugriffe (als Mitglied und als Datei-Owner)
    db.query(models.DBAccess).filter(models.DBAccess.member_id == uid).delete()
    if file_ids:
        db.query(models.DBAccess).filter(
            models.DBAccess.file_id.in_(file_ids)
        ).delete(synchronize_session=False)

    # Verschlüsselungsschlüssel (eigene und für eigene Dateien)
    db.query(models.DBFileKey).filter(models.DBFileKey.user_id == uid).delete()
    if file_ids:
        db.query(models.DBFileKey).filter(
            models.DBFileKey.file_id.in_(file_ids)
        ).delete(synchronize_session=False)

    # Dateien und Ordner
    db.query(models.DBFile).filter(models.DBFile.owner_id == uid).delete()
    # parent_id-Selbstreferenz auflösen, dann alle Ordner löschen
    db.query(models.DBFolder).filter(models.DBFolder.owner_id == uid).update(
        {"parent_id": None}, synchronize_session=False
    )
    db.query(models.DBFolder).filter(models.DBFolder.owner_id == uid).delete()

    # Physische Dateien vom Disk löschen
    uploads_dir = os.path.join(os.path.dirname(__file__), "uploads", str(uid))
    if os.path.isdir(uploads_dir):
        shutil.rmtree(uploads_dir, ignore_errors=True)

    db.delete(user)
    print(f"[Scheduler] Account gelöscht: {user.email} (id={uid})")


# ── Tägliche Prüfung ──────────────────────────────────────────────────────────

def check_inactive_users() -> None:
    print(f"[Scheduler] Inaktive-User-Check gestartet: {datetime.utcnow():%Y-%m-%d %H:%M} UTC")
    db = SessionLocal()
    try:
        now          = datetime.utcnow()
        one_year_ago = now - timedelta(days=365)
        one_week_ago = now - timedelta(days=7)

        # Schritt 1: Warnung schicken (inaktiv > 1 Jahr, noch keine Warnung)
        to_warn = (
            db.query(models.DBUser)
            .filter(
                models.DBUser.last_login < one_year_ago,
                models.DBUser.deletion_warning_sent.is_(None),
            )
            .all()
        )
        warned = 0
        for user in to_warn:
            if send_deletion_warning(user.email):
                user.deletion_warning_sent = now
                warned += 1
        if warned:
            db.commit()
            print(f"[Scheduler] {warned} Warnung(en) gesendet.")

        # Schritt 2: Löschen (Warnung > 7 Tage alt, immer noch inaktiv > 1 Jahr)
        to_delete = (
            db.query(models.DBUser)
            .filter(
                models.DBUser.deletion_warning_sent.isnot(None),
                models.DBUser.deletion_warning_sent < one_week_ago,
                models.DBUser.last_login < one_year_ago,
            )
            .all()
        )
        for user in to_delete:
            _delete_user_cascade(db, user)
        if to_delete:
            db.commit()
            print(f"[Scheduler] {len(to_delete)} Account(s) gelöscht.")

    except Exception as exc:
        db.rollback()
        print(f"[Scheduler] Fehler: {exc}")
    finally:
        db.close()


# ── Start / Stop ──────────────────────────────────────────────────────────────

def start_scheduler() -> None:
    _scheduler.add_job(
        check_inactive_users,
        trigger="interval",
        hours=24,
        next_run_time=datetime.utcnow(),   # direkt beim Start einmal durchlaufen
        id="inactive_user_check",
        replace_existing=True,
    )
    _scheduler.start()
    print("[Scheduler] Gestartet – prüft inaktive Accounts täglich.")


def stop_scheduler() -> None:
    _scheduler.shutdown(wait=False)
    print("[Scheduler] Gestoppt.")
