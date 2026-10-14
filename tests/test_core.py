import pytest
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import hash_password
from app.config import IST_TZ
from app.db import Base, get_db
from app.main import app
from app.models import Notification, Pass, User
from app.rules import effective_status

# In-memory SQLite engine per test session with StaticPool
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="function")
def db_session():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()

    # Seed users across all three roles
    warden = User(
        username="warden_test",
        password_hash=hash_password("warden123"),
        name="Dr. Warden",
        role="warden",
        room_no=None,
        is_active=True,
    )
    guard = User(
        username="guard_test",
        password_hash=hash_password("guard123"),
        name="Guard Singh",
        role="guard",
        room_no=None,
        is_active=True,
    )
    r1 = User(
        username="resident_1",
        password_hash=hash_password("pass123"),
        name="Resident One",
        role="resident",
        room_no="101",
        is_active=True,
    )
    r2 = User(
        username="resident_2",
        password_hash=hash_password("pass123"),
        name="Resident Two",
        role="resident",
        room_no="102",
        is_active=True,
    )
    inactive_user = User(
        username="inactive_res",
        password_hash=hash_password("pass123"),
        name="Inactive Resident",
        role="resident",
        room_no="103",
        is_active=False,
    )

    db.add_all([warden, guard, r1, r2, inactive_user])
    db.commit()

    yield db

    db.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def get_token(client, username, password):
    res = client.post("/api/auth/login", json={"username": username, "password": password})
    assert res.status_code == 200
    return res.json()["token"]


# =========================================================================
# 1. AUTHENTICATION & SECURITY TESTS (Doc 03)
# =========================================================================

def test_auth_login_valid_and_invalid(client):
    # Valid login
    res = client.post("/api/auth/login", json={"username": "resident_1", "password": "pass123"})
    assert res.status_code == 200
    data = res.json()
    assert "token" in data
    assert data["user"]["username"] == "resident_1"
    assert data["user"]["role"] == "resident"

    # Invalid password
    res = client.post("/api/auth/login", json={"username": "resident_1", "password": "wrongpassword"})
    assert res.status_code == 401
    assert res.json()["detail"] == "Invalid username or password"

    # Non-existent username
    res = client.post("/api/auth/login", json={"username": "does_not_exist", "password": "pass123"})
    assert res.status_code == 401
    assert res.json()["detail"] == "Invalid username or password"

    # Deactivated user blocked from login
    res = client.post("/api/auth/login", json={"username": "inactive_res", "password": "pass123"})
    assert res.status_code == 401
    assert res.json()["detail"] == "Invalid username or password"


def test_auth_token_deactivation_check(client, db_session):
    # Log in active user
    token = get_token(client, "resident_1", "pass123")
    res = client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200

    # Deactivate user in DB
    u = db_session.query(User).filter(User.username == "resident_1").first()
    u.is_active = False
    db_session.commit()

    # Next request with same token must immediately fail with 401
    res = client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 401


# =========================================================================
# 2. ROLE RESTRICTION & OWNERSHIP TESTS (Doc 02 & 03)
# =========================================================================

def test_role_restrictions_resident_warden_guard(client):
    r_tok = get_token(client, "resident_1", "pass123")
    w_tok = get_token(client, "warden_test", "warden123")
    g_tok = get_token(client, "guard_test", "guard123")

    r_hdr = {"Authorization": f"Bearer {r_tok}"}
    w_hdr = {"Authorization": f"Bearer {w_tok}"}
    g_hdr = {"Authorization": f"Bearer {g_tok}"}

    # Resident-only routes
    assert client.get("/api/passes/mine", headers=r_hdr).status_code == 200
    assert client.get("/api/passes/mine", headers=w_hdr).status_code == 403
    assert client.get("/api/passes/mine", headers=g_hdr).status_code == 403

    # Warden-only routes
    assert client.get("/api/passes/pending", headers=w_hdr).status_code == 200
    assert client.get("/api/passes/pending", headers=r_hdr).status_code == 403
    assert client.get("/api/passes/pending", headers=g_hdr).status_code == 403

    assert client.get("/api/passes", headers=w_hdr).status_code == 200
    assert client.get("/api/passes", headers=r_hdr).status_code == 403
    assert client.get("/api/passes", headers=g_hdr).status_code == 403

    # Guard + Warden routes
    assert client.get("/api/board", headers=g_hdr).status_code == 200
    assert client.get("/api/board", headers=w_hdr).status_code == 200
    assert client.get("/api/board", headers=r_hdr).status_code == 403


def test_resident_pass_ownership_privacy(client, db_session):
    r1_tok = get_token(client, "resident_1", "pass123")
    r2_tok = get_token(client, "resident_2", "pass123")

    now = datetime.now(timezone.utc)
    # Create pass for resident 1
    p1 = Pass(
        type="out",
        resident_id=db_session.query(User).filter(User.username == "resident_1").first().id,
        start_at=now + timedelta(hours=2),
        end_at=now + timedelta(hours=6),
        destination="Market",
        reason="Errands",
        status="pending",
    )
    db_session.add(p1)
    db_session.commit()
    db_session.refresh(p1)

    # Resident 2 attempts to cancel resident 1's pass
    # Doc 03 Section 2: Must return 404 (not 403) so residents cannot probe pass IDs
    res = client.post(f"/api/passes/{p1.id}/cancel", headers={"Authorization": f"Bearer {r2_tok}"})
    assert res.status_code == 404
    assert res.json()["detail"] == "Pass not found"

    # Resident 1 can cancel their own pass
    res_cancel = client.post(f"/api/passes/{p1.id}/cancel", headers={"Authorization": f"Bearer {r1_tok}"})
    assert res_cancel.status_code == 200
    assert res_cancel.json()["status"] == "cancelled"


# =========================================================================
# 3. VALIDATION RULES (Doc 02 Section 5 - All 6 Rules)
# =========================================================================

def test_validation_rule_1_start_in_past(client):
    token = get_token(client, "resident_1", "pass123")
    now_utc = datetime.now(timezone.utc)
    payload = {
        "type": "out",
        "start_at": (now_utc - timedelta(minutes=15)).isoformat(),
        "end_at": (now_utc + timedelta(hours=2)).isoformat(),
        "destination": "Hospital",
        "reason": "Checkup",
    }
    res = client.post("/api/passes", json=payload, headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 400
    assert res.json()["detail"]["code"] == "START_IN_PAST"
    assert res.json()["detail"]["message"] == "Start time must be in the future"


def test_validation_rule_2_end_before_start(client):
    token = get_token(client, "resident_1", "pass123")
    now_utc = datetime.now(timezone.utc)
    payload = {
        "type": "out",
        "start_at": (now_utc + timedelta(hours=4)).isoformat(),
        "end_at": (now_utc + timedelta(hours=2)).isoformat(),
        "destination": "Hospital",
        "reason": "Checkup",
    }
    res = client.post("/api/passes", json=payload, headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 400
    assert res.json()["detail"]["code"] == "END_BEFORE_START"
    assert res.json()["detail"]["message"] == "End must be after start"


def test_validation_rule_3_no_pass_needed(client):
    token = get_token(client, "resident_1", "pass123")
    now_utc = datetime.now(timezone.utc)
    now_ist = now_utc.astimezone(IST_TZ)

    # 15:00 to 19:00 IST tomorrow (back before 22:00 curfew on same day)
    t_start = (now_ist + timedelta(days=2)).replace(hour=15, minute=0, second=0, microsecond=0)
    t_end = t_start.replace(hour=19, minute=0)

    payload = {
        "type": "out",
        "start_at": t_start.astimezone(timezone.utc).isoformat(),
        "end_at": t_end.astimezone(timezone.utc).isoformat(),
        "destination": "Mall",
        "reason": "Shopping",
    }
    res = client.post("/api/passes", json=payload, headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 400
    assert res.json()["detail"]["code"] == "NO_PASS_NEEDED"
    assert res.json()["detail"]["message"] == "No out-pass needed if you're back before 10 pm"


def test_validation_rule_4_guest_same_day(client):
    token = get_token(client, "resident_1", "pass123")
    now_utc = datetime.now(timezone.utc)
    now_ist = now_utc.astimezone(IST_TZ)

    d1 = (now_ist + timedelta(days=2)).replace(hour=10, minute=0, second=0, microsecond=0)
    d2 = (now_ist + timedelta(days=3)).replace(hour=10, minute=0, second=0, microsecond=0)

    payload = {
        "type": "guest",
        "start_at": d1.astimezone(timezone.utc).isoformat(),
        "end_at": d2.astimezone(timezone.utc).isoformat(),
        "guest_name": "Anita Verma",
        "guest_phone": "9876543210",
        "guest_relation": "Parent",
    }
    res = client.post("/api/passes", json=payload, headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 400
    assert res.json()["detail"]["code"] == "GUEST_SAME_DAY"
    assert res.json()["detail"]["message"] == "Guests are day visitors only"


def test_validation_rule_5_guest_cutoff(client):
    token = get_token(client, "resident_1", "pass123")
    now_utc = datetime.now(timezone.utc)
    now_ist = now_utc.astimezone(IST_TZ)

    d1 = (now_ist + timedelta(days=2)).replace(hour=15, minute=0, second=0, microsecond=0)
    d_late = d1.replace(hour=20, minute=30)  # past 20:00

    payload = {
        "type": "guest",
        "start_at": d1.astimezone(timezone.utc).isoformat(),
        "end_at": d_late.astimezone(timezone.utc).isoformat(),
        "guest_name": "Anita Verma",
        "guest_phone": "9876543210",
        "guest_relation": "Parent",
    }
    res = client.post("/api/passes", json=payload, headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 400
    assert res.json()["detail"]["code"] == "GUEST_CUTOFF"
    assert res.json()["detail"]["message"] == "Guests must leave by 8 pm"


def test_validation_rule_6_overlap(client):
    token = get_token(client, "resident_1", "pass123")
    now_utc = datetime.now(timezone.utc)
    now_ist = now_utc.astimezone(IST_TZ)

    # Valid out-pass returning at 23:30 (past 22:00 curfew)
    start_dt = (now_ist + timedelta(days=2)).replace(hour=18, minute=0, second=0, microsecond=0)
    end_dt = start_dt.replace(hour=23, minute=30)

    payload = {
        "type": "out",
        "start_at": start_dt.astimezone(timezone.utc).isoformat(),
        "end_at": end_dt.astimezone(timezone.utc).isoformat(),
        "destination": "Family Dinner",
        "reason": "Birthday celebration",
    }
    res = client.post("/api/passes", json=payload, headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 201

    # Attempt second overlapping pass of same type
    res_overlap = client.post("/api/passes", json=payload, headers={"Authorization": f"Bearer {token}"})
    assert res_overlap.status_code == 400
    assert res_overlap.json()["detail"]["code"] == "OVERLAP"
    assert res_overlap.json()["detail"]["message"] == "You already have a pass for this time"


# =========================================================================
# 4. DECISIONS, DOUBLE-CLICK CONCURRENCY, & LIFECYCLE (Doc 02 Section 7)
# =========================================================================

def test_warden_decision_atomic_and_double_click_safety(client, db_session):
    w_tok = get_token(client, "warden_test", "warden123")
    w_hdr = {"Authorization": f"Bearer {w_tok}"}

    r_tok = get_token(client, "resident_1", "pass123")
    r_hdr = {"Authorization": f"Bearer {r_tok}"}

    now = datetime.now(timezone.utc)
    now_ist = now.astimezone(IST_TZ)

    # Resident raises a pass
    start_dt = (now_ist + timedelta(days=2)).replace(hour=18, minute=0, second=0, microsecond=0)
    end_dt = start_dt.replace(hour=23, minute=0)
    payload = {
        "type": "out",
        "start_at": start_dt.astimezone(timezone.utc).isoformat(),
        "end_at": end_dt.astimezone(timezone.utc).isoformat(),
        "destination": "Conference",
        "reason": "Tech symposium",
    }
    p_res = client.post("/api/passes", json=payload, headers=r_hdr)
    pass_id = p_res.json()["id"]

    # First decision by warden: approve
    dec_res1 = client.post(
        f"/api/passes/{pass_id}/decision",
        json={"decision": "approve", "note": "Approved, keep ID handy"},
        headers=w_hdr,
    )
    assert dec_res1.status_code == 200
    assert dec_res1.json()["status"] == "approved"
    assert dec_res1.json()["decision_note"] == "Approved, keep ID handy"

    # Second decision on the same pass -> 409 NOT_PENDING
    dec_res2 = client.post(
        f"/api/passes/{pass_id}/decision",
        json={"decision": "reject", "note": "Duplicate"},
        headers=w_hdr,
    )
    assert dec_res2.status_code == 409
    assert dec_res2.json()["detail"]["code"] == "NOT_PENDING"


def test_effective_status_clock_computation():
    now = datetime.now(timezone.utc)

    # Approved and end_at in past -> expired
    p_exp = Pass(status="approved", start_at=now - timedelta(hours=3), end_at=now - timedelta(hours=1))
    assert effective_status(p_exp, now) == "expired"

    # Pending and start_at in past -> lapsed
    p_lap = Pass(status="pending", start_at=now - timedelta(minutes=5), end_at=now + timedelta(hours=2))
    assert effective_status(p_lap, now) == "lapsed"


# =========================================================================
# 5. BOARD DATA FILTERING & FIELD PRIVACY (Doc 03 Section 3)
# =========================================================================

def test_guard_board_privacy_and_filtering(client, db_session):
    g_tok = get_token(client, "guard_test", "guard123")
    g_hdr = {"Authorization": f"Bearer {g_tok}"}

    u1 = db_session.query(User).filter(User.username == "resident_1").first()
    w = db_session.query(User).filter(User.username == "warden_test").first()

    now = datetime.now(timezone.utc)

    # 1. Approved guest pass active right now
    gp = Pass(
        type="guest",
        resident_id=u1.id,
        start_at=now - timedelta(minutes=20),
        end_at=now + timedelta(hours=2),
        guest_name="Sanjay Sharma",
        guest_phone="9988776655",
        guest_relation="Uncle",
        status="approved",
        decided_by=w.id,
        decided_at=now - timedelta(minutes=30),
        decision_note="Verified by warden",
    )
    # 2. Approved out-pass starting in 1 hour
    op = Pass(
        type="out",
        resident_id=u1.id,
        start_at=now + timedelta(hours=1),
        end_at=now + timedelta(hours=5),
        destination="Secret Location",
        reason="Private Family Matter",
        status="approved",
        decided_by=w.id,
        decided_at=now - timedelta(minutes=30),
    )
    # 3. Pending pass (must NOT show on the board)
    pending_p = Pass(
        type="guest",
        resident_id=u1.id,
        start_at=now + timedelta(hours=1),
        end_at=now + timedelta(hours=3),
        guest_name="Unapproved Guest",
        status="pending",
    )
    # 4. Expired pass (must NOT show on the board)
    exp_p = Pass(
        type="guest",
        resident_id=u1.id,
        start_at=now - timedelta(hours=4),
        end_at=now - timedelta(hours=1),
        guest_name="Yesterday Guest",
        status="approved",
    )
    db_session.add_all([gp, op, pending_p, exp_p])
    db_session.commit()

    res = client.get("/api/board", headers=g_hdr)
    assert res.status_code == 200
    board = res.json()

    # Verify only approved and active passes appear
    guest_names = [g["guest_name"] for g in board["guests"]]
    assert "Sanjay Sharma" in guest_names
    assert "Unapproved Guest" not in guest_names
    assert "Yesterday Guest" not in guest_names

    # Check 'is_now' flag
    active_guest = next(g for g in board["guests"] if g["guest_name"] == "Sanjay Sharma")
    assert active_guest["is_now"] is True

    # Check declared out
    out_residents = [o["resident_name"] for o in board["out"]]
    assert u1.name in out_residents

    # Crucial Security Check: Sensitive fields must NOT exist in board schema
    for guest in board["guests"]:
        assert "guest_phone" not in guest
        assert "decision_note" not in guest
    for out in board["out"]:
        assert "destination" not in out
        assert "reason" not in out


# =========================================================================
# 6. NOTIFICATION FLOW & READ STATUS (Doc 02 Section 8)
# =========================================================================

def test_notification_flow(client, db_session):
    r_tok = get_token(client, "resident_1", "pass123")
    r_hdr = {"Authorization": f"Bearer {r_tok}"}
    u1 = db_session.query(User).filter(User.username == "resident_1").first()

    n = Notification(
        user_id=u1.id,
        pass_id=1,
        message="Your pass was approved",
    )
    db_session.add(n)
    db_session.commit()
    db_session.refresh(n)

    # Get notifications
    res = client.get("/api/notifications", headers=r_hdr)
    assert res.status_code == 200
    data = res.json()
    assert data["unread_count"] == 1
    assert data["notifications"][0]["id"] == n.id
    assert data["notifications"][0]["read_at"] is None

    # Mark as read
    res_read = client.post(f"/api/notifications/{n.id}/read", headers=r_hdr)
    assert res_read.status_code == 200
    assert res_read.json()["read_at"] is not None

    # Verify unread_count is now 0
    res_after = client.get("/api/notifications", headers=r_hdr)
    assert res_after.json()["unread_count"] == 0
