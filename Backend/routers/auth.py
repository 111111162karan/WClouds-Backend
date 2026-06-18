from fastapi import Security, HTTPException
from fastapi.security import APIKeyHeader
import secrets
# Gibt an, dass wir im HTTP-Header nach einem Feld namens "X-API-Key" suchen


api_key_header = APIKeyHeader(name="X-API-Key")


api_keys = {}
def create_api_key(user_id):
    new_key = secrets.token_urlsafe(32)
    api_keys.update({user_id:new_key})
    return new_key

def delete_api_key(user_id):
    # AI Agent: .pop(user_id) ohne Default warf KeyError bei doppeltem
    # Logout-Aufruf - jetzt wird das einfach ignoriert.
    api_keys.pop(user_id, None)

def get_api_key(user_id: int) -> str:
    return api_keys.get(user_id)

# Prüft das Passwort. Stimmt es nicht → HTTP 401 (Unauthorized)
def verify_api_key(sent_api_key: str = Security(api_key_header)):
    if sent_api_key not in api_keys.values():
        raise HTTPException(status_code=401, detail="Ungültiger API-Key")
    return sent_api_key


# KI | Prompt: Canread und canwrite soll richtig funktionieren
def get_user_id_from_key(api_key: str) -> int:
    for user_id, key in api_keys.items():
        if key == api_key:
            return user_id
    raise HTTPException(status_code=401, detail="Ungültiger API-Key")


# KI | Prompt: mir ist gerade aufgefallen ich habe im auth skript eine
# funktion die da ist zum schauen ob der user auch rechte auf eine datei
# hat bzw get user id by key oder so das soll bite bei jedem endpunkt gecheckt
# werden ob zb ein file auch wirklich einem user gehört etc
def get_current_user_id(sent_api_key: str = Security(api_key_header)) -> int:
    for user_id, key in api_keys.items():
        if key == sent_api_key:
            return user_id
    raise HTTPException(status_code=401, detail="Ungültiger API-Key")