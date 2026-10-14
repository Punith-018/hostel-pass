from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config import CURFEW, GUEST_CUTOFF, IST_TZ
from app.models import Pass, User
from app.schemas import PassCreate


def to_ist(dt: datetime) -> datetime:
    """Ensure datetime is converted to local IST timezone for wall-clock rule checks."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(IST_TZ)



def rule_error(code: str, message: str):
    """Raises HTTP 400 with {code, message} as specified in Doc 02 Section 5."""
    raise HTTPException(status_code=400, detail={"code": code, "message": message})


def validate_pass(user: User, data: PassCreate, db: Session):
    """
    Validates pass request based on the 6 strict rules in Doc 02 Section 5.
    Raises HTTPException(400, {"code", "message"}) on the first failure.
    Invalid passes are NOT saved.
    """
    now = datetime.now(timezone.utc)

    # 1. Start time must be in the future
    if data.start_at <= now:
        rule_error("START_IN_PAST", "Start time must be in the future")

    # 2. End must be after start
    if data.end_at <= data.start_at:
        rule_error("END_BEFORE_START", "End must be after start")

    start_ist = to_ist(data.start_at)
    end_ist = to_ist(data.end_at)

    if data.type == "out":
        # 3. Out-pass: end_at is after curfew (22:00) on the start date (local time)
        # "No out-pass needed if you're back before 10 pm"
        is_same_day = start_ist.date() == end_ist.date()
        if is_same_day and end_ist.time() <= CURFEW:
            rule_error(
                "NO_PASS_NEEDED", "No out-pass needed if you're back before 10 pm"
            )

    elif data.type == "guest":
        # 4. Guest: start and end on the same local date
        if start_ist.date() != end_ist.date():
            rule_error("GUEST_SAME_DAY", "Guests are day visitors only")

        # 5. Guest: local end time <= GUEST_CUTOFF (20:00)
        if end_ist.time() > GUEST_CUTOFF:
            rule_error("GUEST_CUTOFF", "Guests must leave by 8 pm")

    # 6. Both: no overlapping pass, same resident, same type,
    # status pending or approved and not yet ended
    # Overlap condition: existing.start_at < new.end_at AND new.start_at < existing.end_at
    overlapping = (
        db.query(Pass)
        .filter(
            Pass.resident_id == user.id,
            Pass.type == data.type,
            Pass.status.in_(["pending", "approved"]),
            Pass.end_at > now,  # not yet ended
            Pass.start_at < data.end_at,
            Pass.end_at > data.start_at,
        )
        .first()
    )

    if overlapping:
        rule_error("OVERLAP", "You already have a pass for this time")


def effective_status(p: Pass, now: datetime | None = None) -> str:
    """
    Computes effective status dynamically from the clock on every read.
    - if p.status == 'approved' and now >= p.end_at: return 'expired'
    - if p.status == 'pending'  and now >= p.start_at: return 'lapsed'
    - return p.status
    """
    if now is None:
        now = datetime.now(timezone.utc)

    # Ensure tz-aware comparison
    p_end = p.end_at if p.end_at.tzinfo else p.end_at.replace(tzinfo=timezone.utc)
    p_start = (
        p.start_at if p.start_at.tzinfo else p.start_at.replace(tzinfo=timezone.utc)
    )

    if p.status == "approved" and now >= p_end:
        return "expired"
    if p.status == "pending" and now >= p_start:
        return "lapsed"
    return p.status
