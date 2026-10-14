from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import require_role
from app.config import IST_TZ
from app.db import get_db
from app.models import Pass, User
from app.schemas import BoardGuestOut, BoardOutOut, BoardResponse

router = APIRouter(tags=["board"])


@router.get("/board", response_model=BoardResponse)
def get_board(
    current_user: User = Depends(require_role("guard", "warden")),
    db: Session = Depends(get_db),
):
    """
    Doc 02 Section 7 & Doc 03 Section 3:
    GET /board response — approved passes only, filtered by time:
    - guests: guest passes where start_at is today (IST) and end_at > now.
      Fields: guest name, relation, host name, host room, start, end, is_now (start <= now < end).
    - out: out-passes where start_at <= now + 12h and end_at > now.
      Fields: resident name, room, start, end. Labelled 'declared out'.
    Notice: Sensitive fields (destination, reason, guest_phone, decision_note) are strictly stripped.
    """
    now = datetime.now(timezone.utc)
    now_ist = now.astimezone(IST_TZ)
    today_ist = now_ist.date()

    # Calculate IST day start and end in UTC for guest passes
    today_start_ist = datetime.combine(today_ist, datetime.min.time(), tzinfo=IST_TZ)
    today_end_ist = datetime.combine(today_ist, datetime.max.time(), tzinfo=IST_TZ)
    today_start_utc = today_start_ist.astimezone(timezone.utc)
    today_end_utc = today_end_ist.astimezone(timezone.utc)

    # 1. Guests: approved, start_at is today (IST), end_at > now
    guest_passes = (
        db.query(Pass)
        .filter(
            Pass.type == "guest",
            Pass.status == "approved",
            Pass.start_at >= today_start_utc,
            Pass.start_at <= today_end_utc,
            Pass.end_at > now,
        )
        .order_by(Pass.start_at.asc())
        .all()
    )

    guest_items = []
    for gp in guest_passes:
        # Check if currently active (is_now)
        gp_start = gp.start_at if gp.start_at.tzinfo else gp.start_at.replace(tzinfo=timezone.utc)
        gp_end = gp.end_at if gp.end_at.tzinfo else gp.end_at.replace(tzinfo=timezone.utc)
        is_now = gp_start <= now < gp_end

        guest_items.append(
            BoardGuestOut(
                guest_name=gp.guest_name or "",
                relation=gp.guest_relation or "",
                host_name=gp.resident.name if gp.resident else "Unknown",
                host_room=gp.resident.room_no if gp.resident else None,
                start_at=gp.start_at,
                end_at=gp.end_at,
                is_now=is_now,
            )
        )

    # 2. Out-passes: approved, start_at <= now + 12h and end_at > now
    cutoff_12h = now + timedelta(hours=12)
    out_passes = (
        db.query(Pass)
        .filter(
            Pass.type == "out",
            Pass.status == "approved",
            Pass.start_at <= cutoff_12h,
            Pass.end_at > now,
        )
        .order_by(Pass.start_at.asc())
        .all()
    )

    out_items = []
    for op in out_passes:
        out_items.append(
            BoardOutOut(
                resident_name=op.resident.name if op.resident else "Unknown",
                room=op.resident.room_no if op.resident else None,
                start_at=op.start_at,
                end_at=op.end_at,
            )
        )

    return BoardResponse(guests=guest_items, out=out_items)
