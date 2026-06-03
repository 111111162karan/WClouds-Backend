from fastapi import HTTPException
from sqlalchemy.orm import Session


class BaseAPI:

    def get_or_404(self, db: Session, model, item_id: int):
        item = db.query(model).filter(model.id == item_id).first()
        if not item:
            raise HTTPException(status_code=404, detail=f"Eintrag in"
                                                        f"'{model.__tablename__}' mit ID '{item_id}'"
                                                        f"nicht gefunden")
        return item

    
