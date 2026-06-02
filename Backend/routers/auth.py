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
    api_keys.pop(user_id)

def get_api_key(user_id: int) -> str:
    return api_keys.get(user_id)

# Prüft das Passwort. Stimmt es nicht → HTTP 401 (Unauthorized)
def verify_api_key(sent_api_key: str = Security(api_key_header)):
    if sent_api_key not in api_keys :
        raise HTTPException(status_code=401, detail="Ungültiger API-Key")
    return sent_api_key