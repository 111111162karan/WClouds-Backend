import sys
import os
import secrets
import hashlib
import base64

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "Backend"))

from database import SessionLocal, engine
import models

models.Base.metadata.create_all(bind=engine)


def _ask_gb() -> int:
    while True:
        try:
            gb = int(input("Speicherplatz in GB: "))
            if gb > 0:
                return gb
            print("  Muss größer als 0 sein.")
        except ValueError:
            print("  Bitte eine ganze Zahl eingeben.")


def _ask_password(prompt: str = "Passwort: ") -> str:
    try:
        import getpass
        return getpass.getpass(prompt)
    except Exception:
        return input(prompt)


def _make_key(gb: int, redeemed: bool, db) -> str:
    """Legt einen Subscription-Key an und gibt den base64-kodierten Key zurück."""
    raw_key = secrets.token_urlsafe(32)
    db.add(models.DBStoragePlanKeys(key=raw_key, storage=gb, redeemed=redeemed))
    db.commit()
    return base64.b64encode(raw_key.encode()).decode()


# ── Option 1: nur einen Key erstellen ─────────────────────────────────────────

def create_key(db):
    print("\n--- Key erstellen ---")
    gb = _ask_gb()
    b64 = _make_key(gb, redeemed=False, db=db)
    print()
    print(f"  ✓ Key erstellt ({gb} GB)")
    print(f"  Key: {b64}")
    print()
    print("  Diesen Key bei der Registrierung im WClouds-Client eingeben.")
    print()


# ── Option 2: Nutzer direkt anlegen ──────────────────────────────────────────

def create_user(db):
    from pwdlib import PasswordHash

    print("\n--- Nutzer anlegen ---")
    gb    = _ask_gb()
    email = input("E-Mail   : ").strip()

    existing = db.query(models.DBUser).filter(models.DBUser.email == email).first()
    if existing:
        print(f"\n  Fehler: '{email}' ist bereits registriert.\n")
        return

    password = _ask_password("Passwort : ")

    # Frontend sendet SHA-256 des Klartext-Passworts; Backend bcryptet diesen Hash.
    # Wir simulieren exakt dasselbe damit der Login über den Client funktioniert.
    sha256_pw = hashlib.sha256(password.encode("utf-8")).hexdigest()
    hashed    = PasswordHash.recommended().hash(sha256_pw)

    # Subscription-Key im Hintergrund anlegen (sofort eingelöst)
    _make_key(gb, redeemed=True, db=db)

    new_user = models.DBUser(
        email        = email,
        password     = hashed,
        storage_plan = gb,
        public_key   = None,   # wird beim ersten Login über den Client gesetzt
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # Root-Ordner anlegen
    root_path = models.DBPath(path=f"/home/user{new_user.id}/")
    db.add(root_path)
    db.commit()
    db.refresh(root_path)

    db.add(models.DBFolder(
        name      = "Root",
        owner_id  = new_user.id,
        path_id   = root_path.id,
        parent_id = None,
    ))
    db.commit()

    print()
    print(f"  ✓ Nutzer angelegt")
    print(f"  ID      : {new_user.id}")
    print(f"  E-Mail  : {email}")
    print(f"  Speicher: {gb} GB")
    print()
    print("  Hinweis: Der RSA-Schlüssel wird automatisch beim ersten")
    print("  Login über den WClouds-Client generiert und hochgeladen.")
    print()


# ── Hauptmenü ─────────────────────────────────────────────────────────────────

def main():
    db = SessionLocal()
    try:
        while True:
            print("====================================")
            print("   WClouds Admin  -  init.py")
            print("====================================")
            print("  [1]  Key erstellen")
            print("  [2]  Nutzer direkt anlegen")
            print("  [0]  Beenden")
            print("------------------------------------")
            choice = input("Auswahl: ").strip()

            if choice == "1":
                create_key(db)
            elif choice == "2":
                create_user(db)
            elif choice == "0":
                break
            else:
                print("  Ungültige Auswahl.\n")
    finally:
        db.close()


if __name__ == "__main__":
    main()
