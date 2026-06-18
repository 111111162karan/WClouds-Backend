import sys
import os
import secrets
import hashlib
import base64
import shutil
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

_backend_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Backend")
os.chdir(_backend_dir)
sys.path.insert(0, _backend_dir)

from database import SessionLocal, engine
import models

models.Base.metadata.create_all(bind=engine)

UPLOADS_DIR = os.path.join(_backend_dir, "uploads")

def _now():
    return datetime.now(ZoneInfo("Europe/Vienna")).replace(tzinfo=None)

def _ask_gb() -> int:
    while True:
        try:
            gb = int(input("  Speicherplatz in GB: "))
            if gb > 0:
                return gb
            print("  Muss groesser als 0 sein.")
        except ValueError:
            print("  Bitte eine ganze Zahl eingeben.")

def _hash_password(raw: str) -> str:
    from pwdlib import PasswordHash
    sha256 = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return PasswordHash.recommended().hash(sha256)

def _make_key(gb: int, redeemed: bool, db) -> str:
    raw = secrets.token_urlsafe(32)
    db.add(models.DBStoragePlanKeys(key=raw, storage=gb, redeemed=redeemed))
    db.commit()
    return base64.b64encode(raw.encode()).decode()

def _create_user_with_root(email: str, password: str, gb: int, db) -> models.DBUser:
    hashed = _hash_password(password)
    _make_key(gb, redeemed=True, db=db)

    user = models.DBUser(email=email, password=hashed, storage_plan=gb, public_key=None)
    db.add(user)
    db.commit()
    db.refresh(user)

    root_path = models.DBPath(path=f"/home/user{user.id}/")
    db.add(root_path)
    db.commit()
    db.refresh(root_path)

    root_folder = models.DBFolder(name="Root", owner_id=user.id, path_id=root_path.id, parent_id=None)
    db.add(root_folder)
    db.commit()
    db.refresh(root_folder)

    db.add(models.DBFolderHistory(size=0.0, date=_now(), user_id=user.id, folder_id=root_folder.id, path=root_path.id))
    db.commit()

    return user

def _create_folder(name: str, owner_id: int, parent_id: int, parent_path: str, db) -> models.DBFolder:
    path_str = f"{parent_path}{name}/"
    p = models.DBPath(path=path_str)
    db.add(p)
    db.commit()
    db.refresh(p)

    folder = models.DBFolder(name=name, owner_id=owner_id, path_id=p.id, parent_id=parent_id)
    db.add(folder)
    db.commit()
    db.refresh(folder)

    db.add(models.DBFolderHistory(size=0.0, date=_now(), user_id=owner_id, folder_id=folder.id, path=p.id))
    db.commit()
    return folder

def _create_dummy_file(name: str, ext: str, owner_id: int, folder_id: int,
                       folder_path: str, size_kb: int, db) -> models.DBFile:
    os.makedirs(os.path.join(UPLOADS_DIR, str(owner_id)), exist_ok=True)
    file_uuid = secrets.token_hex(16)
    disk_path = os.path.join(UPLOADS_DIR, str(owner_id), f"{file_uuid}.enc")

    # Dummy-Inhalt: zufaellige Bytes (simuliert verschluesselten Inhalt)
    with open(disk_path, "wb") as f:
        f.write(secrets.token_bytes(size_kb * 1024))

    size_gb = (size_kb * 1024) / (1024 ** 3)

    path_obj = models.DBPath(path=disk_path)
    db.add(path_obj)
    db.commit()
    db.refresh(path_obj)

    nonce = secrets.token_hex(12)
    db_file = models.DBFile(name=f"{name}{ext}", owner_id=owner_id,
                            path_id=path_obj.id, folder_id=folder_id, nonce=nonce)
    db.add(db_file)
    db.commit()
    db.refresh(db_file)

    db.add(models.DBFileHistory(size=size_gb, date=_now(), user_id=owner_id,
                                file_id=db_file.id, path=path_obj.id, nonce=nonce))
    db.commit()

    user = db.query(models.DBUser).filter_by(id=owner_id).first()
    if user:
        user.used_storage = round((user.used_storage or 0) + size_gb, 6)
        db.commit()

    return db_file


# ── Option 1 ──────────────────────────────────────────────────────────────────

def create_key(db):
    print("\n--- Key erstellen ---")
    gb  = _ask_gb()
    b64 = _make_key(gb, redeemed=False, db=db)

    txt_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            f"wclouds_key_{gb}gb.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(f"{b64}")


    print(f"  OK  Key erstellt ({gb} GB)")
    print(f"  Key: {b64}")
    print(f"  Gespeichert: {txt_path}\n")


# ── Option 2 ──────────────────────────────────────────────────────────────────

def create_user(db):
    print("\n--- Nutzer anlegen ---")
    gb = _ask_gb()
    email = input("  E-Mail  : ").strip()

    if db.query(models.DBUser).filter_by(email=email).first():
        print(f"  Fehler: '{email}' ist bereits registriert.\n")
        return

    password = input("  Passwort: ").strip()
    if not password:
        print("  Fehler: Passwort darf nicht leer sein.\n")
        return

    user = _create_user_with_root(email, password, gb, db)

    print(f"  OK  Nutzer angelegt (ID {user.id}, {gb} GB)")
    print("  Hinweis: RSA-Key wird beim ersten App-Login generiert.\n")


# ── Option 3 ──────────────────────────────────────────────────────────────────

DUMMY_STRUCTURE = [
    # (ordnername, [(dateiname, endung, groesse_kb), ...])
    ("Dokumente", [
        ("Bericht_2025",      ".pdf",  120),
        ("Budget_Q1",         ".xlsx",  48),
        ("Praesentation",     ".pptx",  85),
        ("Notizen",           ".txt",    4),
    ]),
    ("Bilder", [
        ("Urlaub_Sommer",     ".jpg",  340),
        ("Profilbild",        ".png",   92),
        ("Screenshot_01",     ".png",   55),
    ]),
    ("Videos", [
        ("Intro_Clip",        ".mp4", 800),
    ]),
    ("Backup", [
        ("Archiv_Alt",        ".zip", 500),
        ("Konfiguration",     ".json",   8),
    ]),
]

def create_test_users(db):
    print("\n--- Test-User erstellen ---")
    print("  Erstellt 2 Nutzer mit Dummy-Daten und teilt eine Datei zwischen ihnen.")
    print()

    # Nutzer 1
    EMAIL1, PASS1 = "alice@wclouds.local", "test123"
    if db.query(models.DBUser).filter_by(email=EMAIL1).first():
        print(f"  Uebersprungen: {EMAIL1} existiert bereits.")
        u1 = db.query(models.DBUser).filter_by(email=EMAIL1).first()
    else:
        u1 = _create_user_with_root(EMAIL1, PASS1, 50, db)
        root1 = db.query(models.DBFolder).filter_by(owner_id=u1.id, parent_id=None).first()
        root_path1 = db.query(models.DBPath).filter_by(id=root1.path_id).first()

        shared_file = None
        for folder_name, files in DUMMY_STRUCTURE:
            sub = _create_folder(folder_name, u1.id, root1.id, root_path1.path, db)
            for fname, ext, kb in files:
                f = _create_dummy_file(fname, ext, u1.id, sub.id, root_path1.path, kb, db)
                if shared_file is None:
                    shared_file = f  # erste Datei zum Teilen merken

        print(f"  OK  {EMAIL1} / {PASS1}  (ID {u1.id}, 50 GB)")

    # Nutzer 2
    EMAIL2, PASS2 = "bob@wclouds.local", "test123"
    if db.query(models.DBUser).filter_by(email=EMAIL2).first():
        print(f"  Uebersprungen: {EMAIL2} existiert bereits.")
    else:
        u2 = _create_user_with_root(EMAIL2, PASS2, 20, db)
        root2 = db.query(models.DBFolder).filter_by(owner_id=u2.id, parent_id=None).first()
        root_path2 = db.query(models.DBPath).filter_by(id=root2.path_id).first()

        # Bob bekommt einen eigenen Ordner
        _create_folder("Projekte", u2.id, root2.id, root_path2.path, db)
        sub_bob = _create_folder("Downloads", u2.id, root2.id, root_path2.path, db)
        _create_dummy_file("Setup_Anleitung", ".pdf", u2.id, sub_bob.id, root_path2.path, 60, db)

        print(f"  OK  {EMAIL2} / {PASS2}  (ID {u2.id}, 20 GB)")

        # Teilen: erste Datei von Alice mit Bob (nur lesen)
        shared_file = db.query(models.DBFile).filter_by(owner_id=u1.id).first()
        if shared_file:
            existing = db.query(models.DBAccess).filter_by(
                file_id=shared_file.id, member_id=u2.id).first()
            if not existing:
                db.add(models.DBAccess(member_id=u2.id, file_id=shared_file.id,
                                       can_read=True, can_write=False))
                db.commit()
                print(f"  OK  '{shared_file.name}' von Alice mit Bob geteilt (nur lesen)")

    print()
    print("  Zugangsdaten:")
    print("    alice@wclouds.local  /  test123")
    print("    bob@wclouds.local    /  test123")
    print()
    print("  Hinweis: Dateien sind Dummy-Bytes (nicht entschlusselbar).")
    print("  Ordner- und Datei-Listing, Info, History funktionieren aber vollstaendig.\n")


# ── Hauptmenue ────────────────────────────────────────────────────────────────

def main():
    db = SessionLocal()
    try:
        while True:
            print("====================================")
            print("   WClouds Admin  -  init.py")
            print("====================================")
            print("  [1]  Key erstellen")
            print("  [2]  Nutzer direkt anlegen")
            # print("  [3]  Test-User mit Dummy-Daten")
            print("  [0]  Beenden")
            print("------------------------------------")
            choice = input("Auswahl: ").strip()
            if choice == "1":
                create_key(db)
            elif choice == "2":
                create_user(db)
            # elif choice == "3":
            #    create_test_users(db)
            elif choice == "0":
                break
            else:
                print("  Ungueltige Auswahl.\n")
    finally:
        db.close()

if __name__ == "__main__":
    main()
