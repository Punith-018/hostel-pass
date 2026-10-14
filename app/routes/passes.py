from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth import require_role
from app.config import IST_TZ
from app.db import get_db
from app.models import Pass, User
from app.notify import notify
from app.rules import effective_status, validate_pass
from app.schemas import DecisionRequest, PassCreate, PassOut

router = APIRouter(tags=["passes"])


def format_ist_datetime(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    ist = dt.astimezone(IST_TZ)
    return ist.strftime("%d %b, %I:%M %p").replace(" 0", " ")


def serialize_pass(p: Pass) -> PassOut:
    out_dict = {
        col.name: getattr(p, col.name)
        for col in p.__table__.columns
    }
    out_dict["effective_status"] = effective_status(p)
    out_dict["resident_name"] = p.resident.name if p.resident else None
    out_dict["resident_room"] = p.resident.room_no if p.resident else None
    out_dict["decided_by_name"] = p.decided_by_user.name if p.decided_by_user else None
    return PassOut(**out_dict)


# ==========================================
# RESIDENT ENDPOINTS
# ==========================================

@router.post("/passes", response_model=PassOut, status_code=status.HTTP_201_CREATED)
def create_pass(
    pass_in: PassCreate,
    current_user: User = Depends(require_role("resident")),
    db: Session = Depends(get_db),
):
    validate_pass(current_user, pass_in, db)

    start_utc = (
        pass_in.start_at
        if pass_in.start_at.tzinfo
        else pass_in.start_at.replace(tzinfo=timezone.utc)
    )
    end_utc = (
        pass_in.end_at
        if pass_in.end_at.tzinfo
        else pass_in.end_at.replace(tzinfo=timezone.utc)
    )

    new_pass = Pass(
        type=pass_in.type,
        resident_id=current_user.id,
        start_at=start_utc,
        end_at=end_utc,
        destination=pass_in.destination if pass_in.type == "out" else None,
        reason=pass_in.reason if pass_in.type == "out" else None,
        guest_name=pass_in.guest_name if pass_in.type == "guest" else None,
        guest_phone=pass_in.guest_phone if pass_in.type == "guest" else None,
        guest_relation=pass_in.guest_relation if pass_in.type == "guest" else None,
        status="pending",
        created_at=datetime.now(timezone.utc),
    )
    db.add(new_pass)
    db.commit()
    db.refresh(new_pass)

    warden = db.query(User).filter(User.role == "warden", User.is_active == True).first()
    if warden:
        room_str = f" ({current_user.room_no})" if current_user.room_no else ""
        time_str = f"{format_ist_datetime(new_pass.start_at)} – {format_ist_datetime(new_pass.end_at)}"
        msg = f"{current_user.name}{room_str} requested a {new_pass.type}-pass for {time_str}"
        notify(db, warden.id, new_pass.id, msg)

    return serialize_pass(new_pass)


@router.get("/passes/mine", response_model=List[PassOut])
def get_my_passes(
    current_user: User = Depends(require_role("resident")),
    db: Session = Depends(get_db),
):
    """Resident views own passes, newest first."""
    passes = (
        db.query(Pass)
        .filter(Pass.resident_id == current_user.id)
        .order_by(Pass.created_at.desc())
        .all()
    )
    return [serialize_pass(p) for p in passes]


@router.post("/passes/{pass_id}/cancel", response_model=PassOut)
def cancel_pass(
    pass_id: int,
    current_user: User = Depends(require_role("resident")),
    db: Session = Depends(get_db),
):
    """
    Doc 02 Section 7 & Doc 03 Section 2 & 4:
    Cancel uses conditional UPDATE:
    WHERE status IN ('pending','approved') AND end_at > now AND resident_id = me
    If pass belongs to someone else or doesn't exist, return 404 (not 403) so residents can't probe IDs.
    If 0 rows updated because already ended, cancelled or rejected -> 409
    """
    now = datetime.now(timezone.utc)

    # First check if the pass exists and belongs to current_user
    # Doc 03 Section 2: If no row matches resident_id = me, return 404 (not 403)
    target_pass = (
        db.query(Pass)
        .filter(Pass.id == pass_id, Pass.resident_id == current_user.id)
        .first()
    )
    if not target_pass:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pass not found",
        )

    # Conditional update for concurrency safety
    stmt = text(
        """
        UPDATE passes
        SET status = 'cancelled', cancelled_at = :now
        WHERE id = :id
          AND resident_id = :resident_id
          AND status IN ('pending', 'approved')
          AND end_at > :now
        """
    )
    result = db.execute(
        stmt,
        {"id": pass_id, "resident_id": current_user.id, "now": now},
    )
    db.commit()

    if result.rowcount == 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "CANNOT_CANCEL",
                "message": "This pass has already ended, was already cancelled, or is not cancellable",
            },
        )

    db.refresh(target_pass)

    # Notify warden (Doc 02 Section 8)
    warden = db.query(User).filter(User.role == "warden", User.is_active == True).first()
    if warden:
        ist_dt = target_pass.start_at
        if ist_dt.tzinfo is None:
            ist_dt = ist_dt.replace(tzinfo=timezone.utc)
        date_str = ist_dt.astimezone(IST_TZ).strftime("%d %b")
        msg = f"{current_user.name} cancelled his {target_pass.type}-pass for {date_str}"
        notify(db, warden.id, target_pass.id, msg)

    return serialize_pass(target_pass)


# ==========================================
# WARDEN ENDPOINTS
# ==========================================

@router.get("/passes/pending", response_model=List[PassOut])
def get_pending_passes(
    current_user: User = Depends(require_role("warden")),
    db: Session = Depends(get_db),
):
    """
    Warden sees pending passes with start_at in future, soonest first.
    Doc 02 Section 7: GET /passes/pending: pending and start in future, soonest first.
    """
    now = datetime.now(timezone.utc)
    passes = (
        db.query(Pass)
        .filter(Pass.status == "pending", Pass.start_at > now)
        .order_by(Pass.start_at.asc())
        .all()
    )
    return [serialize_pass(p) for p in passes]


@router.post("/passes/{pass_id}/decision", response_model=PassOut)
def decide_pass(
    pass_id: int,
    req: DecisionRequest,
    current_user: User = Depends(require_role("warden")),
    db: Session = Depends(get_db),
):
    """
    Doc 02 Section 7:
    Decision must be safe against double clicks. Use one conditional update:
    UPDATE passes SET status=?, decided_by=?, decided_at=?, decision_note=?
    WHERE id=? AND status='pending' AND start_at > now
    If 0 rows changed -> 409 {"code":"NOT_PENDING","message":"This pass was already decided, cancelled or has lapsed"}.
    """
    now = datetime.now(timezone.utc)
    new_status = "approved" if req.decision == "approve" else "rejected"

    stmt = text(
        """
        UPDATE passes
        SET status = :new_status,
            decided_by = :decided_by,
            decided_at = :now,
            decision_note = :decision_note
        WHERE id = :id
          AND status = 'pending'
          AND start_at > :now
        """
    )
    result = db.execute(
        stmt,
        {
            "new_status": new_status,
            "decided_by": current_user.id,
            "now": now,
            "decision_note": req.note,
            "id": pass_id,
        },
    )
    db.commit()

    if result.rowcount == 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "NOT_PENDING",
                "message": "This pass was already decided, cancelled or has lapsed",
            },
        )

    updated_pass = db.query(Pass).filter(Pass.id == pass_id).first()

    # Notify resident (Doc 02 Section 8)
    ist_dt = updated_pass.start_at
    if ist_dt.tzinfo is None:
        ist_dt = ist_dt.replace(tzinfo=timezone.utc)
    date_str = ist_dt.astimezone(IST_TZ).strftime("%d %b")

    if new_status == "approved":
        msg = f"Your {updated_pass.type}-pass for {date_str} was approved"
    else:
        note_suffix = f": {req.note}" if req.note else ""
        msg = f"Your {updated_pass.type}-pass for {date_str} was rejected{note_suffix}"

    notify(db, updated_pass.resident_id, updated_pass.id, msg)

    return serialize_pass(updated_pass)


@router.get("/passes", response_model=List[PassOut])
def get_pass_history(
    status: Optional[str] = Query(default=None),
    type: Optional[str] = Query(default=None),
    resident_id: Optional[int] = Query(default=None),
    date: Optional[str] = Query(default=None),  # YYYY-MM-DD
    current_user: User = Depends(require_role("warden")),
    db: Session = Depends(get_db),
):
    """
    Doc 02 Section 7:
    GET /passes (Warden only) - history; query status, type, resident_id, date
    """
    query = db.query(Pass)

    if status:
        query = query.filter(Pass.status == status)
    if type:
        query = query.filter(Pass.type == type)
    if resident_id:
        query = query.filter(Pass.resident_id == resident_id)
    if date:
        # Filter where local date matches date string
        # Match against start_at string date
        try:
            target_date = datetime.strptime(date, "%Y-%m-%d").date()
            # Match date in IST range
            # Or filter in Python / SQLAlchemy date casting
            # Since SQLite DATE(start_at) is in UTC, calculate day bounds in UTC for the given IST day
            # Start of IST day: target_date 00:00 IST -> UTC
            # End of IST day: target_date 23:59:59.999999 IST -> UTC
            day_start_ist = datetime.combine(target_date, datetime.min.time(), tzinfo=IST_TZ)
            day_end_ist = datetime.combine(target_date, datetime.max.time(), tzinfo=IST_TZ)
            query = query.filter(
                Pass.start_at >= day_start_ist.astimezone(timezone.utc),
                Pass.start_at <= day_end_ist.astimezone(timezone.utc),
            )
        except ValueError:
            pass

    passes = query.order_by(Pass.created_at.desc()).all()
    return [serialize_pass(p) for p in passes]
