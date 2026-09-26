from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import services
from app.auth import driver_of, organization_of, require_role
from app.db import get_db
from app.models import Delivery, User
from app.schemas import StatusIn
from app.serializers import delivery_json

router = APIRouter(prefix="/deliveries", tags=["deliveries"])


def _get(db: Session, delivery_id: int) -> Delivery:
    delivery = db.get(Delivery, delivery_id)
    if delivery is None:
        raise HTTPException(404, "Delivery not found")
    return delivery


@router.patch("/{delivery_id}/status")
def update_status(delivery_id: int, body: StatusIn, user: User = Depends(require_role("DRIVER", "ADMIN")),
                  db: Session = Depends(get_db)):
    delivery = _get(db, delivery_id)
    if user.role == "DRIVER" and delivery.driver_id != driver_of(db, user).id:
        raise HTTPException(403, "This delivery belongs to another driver")
    return delivery_json(services.advance(db, delivery, body.status))


@router.post("/{delivery_id}/confirm")
def confirm(delivery_id: int, user: User = Depends(require_role("ORGANIZATION", "ADMIN")),
            db: Session = Depends(get_db)):
    delivery = _get(db, delivery_id)
    org_id = organization_of(db, user).id if user.role == "ORGANIZATION" else None
    return delivery_json(services.confirm(db, delivery, org_id))
