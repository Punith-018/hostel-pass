from datetime import datetime, timedelta, timezone
import bcrypt

from app.db import Base, SessionLocal, engine
from app.models import Notification, Pass, User


def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def seed():
    # Drop and recreate tables fresh
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        # 1. Staff users
        warden = User(
            username="warden",
            password_hash=hash_password("warden123"),
            name="Dr. S. K. Sharma (Warden)",
            role="warden",
            room_no=None,
            is_active=True,
        )
        guard = User(
            username="guard",
            password_hash=hash_password("guard123"),
            name="Ram Singh (Main Gate Guard)",
            role="guard",
            room_no=None,
            is_active=True,
        )
        db.add_all([warden, guard])

        # 2. Resident demo users (rooms 101–103)
        residents_data = [
            ("r101a", "pass123", "Rahul Verma", "101"),
            ("r101b", "pass123", "Aman Gupta", "101"),
            ("r102a", "pass123", "Priya Nair", "102"),
            ("r102b", "pass123", "Sneha Patel", "102"),
            ("r103a", "pass123", "Rohan Mehta", "103"),
        ]

        resident_users = {}
        for username, pwd, name, room in residents_data:
            u = User(
                username=username,
                password_hash=hash_password(pwd),
                name=name,
                role="resident",
                room_no=room,
                is_active=True,
            )
            db.add(u)
            resident_users[username] = u

        db.commit()
        for u in resident_users.values():
            db.refresh(u)
        db.refresh(warden)

        # 3. Sample passes relative to now (UTC) for demo & live board
        now = datetime.now(timezone.utc)

        # Pass 1: Approved Guest Pass active right now (Allowed Now on the board)
        p1 = Pass(
            type="guest",
            resident_id=resident_users["r101a"].id,
            start_at=now - timedelta(minutes=30),
            end_at=now + timedelta(hours=2),
            guest_name="Vikram Verma",
            guest_phone="9876543210",
            guest_relation="Parent",
            status="approved",
            decided_by=warden.id,
            decided_at=now - timedelta(hours=1),
            decision_note="Verified with parent over call.",
            created_at=now - timedelta(hours=2),
        )

        # Pass 2: Approved Guest Pass scheduled for later today
        p2 = Pass(
            type="guest",
            resident_id=resident_users["r102a"].id,
            start_at=now + timedelta(hours=3),
            end_at=now + timedelta(hours=5),
            guest_name="Ananya Nair",
            guest_phone="9812345678",
            guest_relation="Sibling",
            status="approved",
            decided_by=warden.id,
            decided_at=now - timedelta(minutes=45),
            decision_note="Approved.",
            created_at=now - timedelta(hours=1),
        )

        # Pass 3: Approved Out-Pass starting in 1 hour (Declared Out tonight)
        p3 = Pass(
            type="out",
            resident_id=resident_users["r103a"].id,
            start_at=now + timedelta(hours=1),
            end_at=now + timedelta(hours=8),
            destination="City Center / Library",
            reason="Late study session and group project work.",
            status="approved",
            decided_by=warden.id,
            decided_at=now - timedelta(minutes=20),
            decision_note="Take student ID card.",
            created_at=now - timedelta(hours=1),
        )

        # Pass 4: Pending Out-Pass waiting for warden review
        p4 = Pass(
            type="out",
            resident_id=resident_users["r101b"].id,
            start_at=now + timedelta(hours=2),
            end_at=now + timedelta(hours=9),
            destination="Railway Station",
            reason="Receiving family arriving on train.",
            status="pending",
            created_at=now - timedelta(minutes=15),
        )

        # Pass 5: Rejected Guest Pass
        p5 = Pass(
            type="guest",
            resident_id=resident_users["r102b"].id,
            start_at=now + timedelta(hours=4),
            end_at=now + timedelta(hours=6),
            guest_name="Karan Dave",
            guest_phone="9988776655",
            guest_relation="Friend",
            status="rejected",
            decided_by=warden.id,
            decided_at=now - timedelta(minutes=10),
            decision_note="Past guest cutoff limit for today.",
            created_at=now - timedelta(minutes=30),
        )

        db.add_all([p1, p2, p3, p4, p5])
        db.commit()

        # 4. Sample notifications
        n1 = Notification(
            user_id=warden.id,
            pass_id=p4.id,
            message=f"{resident_users['r101b'].name} (Room 101) requested an out-pass",
            created_at=p4.created_at,
        )
        n2 = Notification(
            user_id=resident_users["r101a"].id,
            pass_id=p1.id,
            message="Your guest pass for Vikram Verma was approved",
            created_at=p1.decided_at,
            read_at=now - timedelta(minutes=25),
        )
        n3 = Notification(
            user_id=resident_users["r102b"].id,
            pass_id=p5.id,
            message="Your guest pass for Karan Dave was rejected: Past guest cutoff limit for today.",
            created_at=p5.decided_at,
        )

        db.add_all([n1, n2, n3])
        db.commit()
        print("Database seeded successfully with demo users, sample passes, and notifications.")

    finally:
        db.close()


if __name__ == "__main__":
    seed()
