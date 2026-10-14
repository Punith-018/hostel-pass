from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.models import Notification


def notify(db: Session, user_id: int, pass_id: int, message: str) -> Notification:
    """Inserts a notification row."""
    notif = Notification(
        user_id=user_id,
        pass_id=pass_id,
        message=message,
        created_at=datetime.now(timezone.utc),
    )
    db.add(notif)
    db.commit()
    db.refresh(notif)
    return notif
