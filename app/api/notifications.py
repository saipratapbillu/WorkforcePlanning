from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.security.dependencies import get_current_user
from app.services.security_service import SecurityService

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("")
def list_notifications(db: Session = Depends(get_db), user=Depends(get_current_user)):
    rows = SecurityService(db).GetVisibleNotifications(user)
    return [{
        "notification_id": str(row["NotificationID"]),
        "type": row["NotificationType"],
        "title": row["Title"],
        "body": row["Body"],
        "resource_type": row["ResourceType"],
        "resource_id": row["ResourceID"],
        "is_read": row["IsRead"],
        "created_at_utc": row["CreatedAtUtc"],
    } for row in rows]


@router.post("/{notification_id}/read")
def mark_notification_read(
    notification_id: UUID,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    rows = SecurityService(db).GetVisibleNotifications(user, notification_id)
    if not rows:
        raise HTTPException(status_code=404, detail="Notification not found")
    if not rows[0]["IsRead"]:
        changed = SecurityService(db).MarkVisibleNotificationRead(user, notification_id)
        if not changed:
            raise HTTPException(status_code=404, detail="Notification not found")
        db.commit()
    return {"notification_id": str(rows[0]["NotificationID"]), "is_read": True}