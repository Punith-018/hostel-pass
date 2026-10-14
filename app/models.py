from datetime import datetime, timezone
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import relationship

from app.db import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(80), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    name = Column(String(80), nullable=False)
    role = Column(String(20), nullable=False)  # resident, warden, guard
    room_no = Column(String(20), nullable=True)  # null for staff
    is_active = Column(Boolean, default=True, nullable=False)

    # Relationships
    passes = relationship(
        "Pass", back_populates="resident", foreign_keys="Pass.resident_id"
    )
    decisions = relationship(
        "Pass", back_populates="decided_by_user", foreign_keys="Pass.decided_by"
    )
    notifications = relationship("Notification", back_populates="user")


class Pass(Base):
    __tablename__ = "passes"

    id = Column(Integer, primary_key=True, index=True)
    type = Column(String(20), nullable=False)  # out, guest
    resident_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    start_at = Column(DateTime(timezone=True), nullable=False)
    end_at = Column(DateTime(timezone=True), nullable=False)

    # Out-pass specific
    destination = Column(String(200), nullable=True)
    reason = Column(String(200), nullable=True)

    # Guest-pass specific
    guest_name = Column(String(80), nullable=True)
    guest_phone = Column(String(20), nullable=True)
    guest_relation = Column(String(50), nullable=True)

    # Lifecycle & decision
    status = Column(
        String(20), default="pending", nullable=False
    )  # pending, approved, rejected, cancelled
    decided_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    decided_at = Column(DateTime(timezone=True), nullable=True)
    decision_note = Column(String(200), nullable=True)

    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    resident = relationship("User", foreign_keys=[resident_id], back_populates="passes")
    decided_by_user = relationship(
        "User", foreign_keys=[decided_by], back_populates="decisions"
    )
    notifications = relationship("Notification", back_populates="pass_rel")

    # Composite indexes from spec: (status, start_at), (resident_id, created_at)
    __table_args__ = (
        Index("ix_passes_status_start_at", "status", "start_at"),
        Index("ix_passes_resident_id_created_at", "resident_id", "created_at"),
    )


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    pass_id = Column(Integer, ForeignKey("passes.id"), nullable=False)
    message = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    read_at = Column(DateTime(timezone=True), nullable=True)  # null = unread

    # Relationships
    user = relationship("User", back_populates="notifications")
    pass_rel = relationship("Pass", back_populates="notifications")
