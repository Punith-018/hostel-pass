from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


# Auth schemas
class LoginRequest(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    name: str
    role: str
    room_no: Optional[str] = None
    is_active: bool


class TokenResponse(BaseModel):
    token: str
    user: UserOut


# Pass submission schema
class PassCreate(BaseModel):
    type: str  # "out" | "guest"
    start_at: datetime
    end_at: datetime

    # Out-pass specific (max length 200 per Doc 03 Section 5)
    destination: Optional[str] = Field(default=None, max_length=200)
    reason: Optional[str] = Field(default=None, max_length=200)

    # Guest-pass specific (name 80, phone 10 digits, relation 50)
    guest_name: Optional[str] = Field(default=None, max_length=80)
    guest_phone: Optional[str] = Field(default=None, max_length=20)
    guest_relation: Optional[str] = Field(default=None, max_length=50)

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        if v not in ("out", "guest"):
            raise ValueError("Type must be either 'out' or 'guest'")
        return v

    @field_validator("guest_phone")
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v_clean = v.strip()
            digits = "".join(filter(str.isdigit, v_clean))
            if len(digits) != 10:
                raise ValueError("Guest phone must be 10 digits")
            return digits
        return v


# Warden decision request
class DecisionRequest(BaseModel):
    decision: str  # "approve" | "reject"
    note: Optional[str] = Field(default=None, max_length=200)

    @field_validator("decision")
    @classmethod
    def validate_decision(cls, v: str) -> str:
        if v not in ("approve", "reject"):
            raise ValueError("Decision must be 'approve' or 'reject'")
        return v


# Full Pass output schema for Resident and Warden (Doc 03 Section 3)
class PassOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: str
    resident_id: int
    start_at: datetime
    end_at: datetime
    destination: Optional[str] = None
    reason: Optional[str] = None
    guest_name: Optional[str] = None
    guest_phone: Optional[str] = None
    guest_relation: Optional[str] = None
    status: str
    effective_status: str
    decided_by: Optional[int] = None
    decided_at: Optional[datetime] = None
    decision_note: Optional[str] = None
    created_at: datetime
    cancelled_at: Optional[datetime] = None

    # Enriched fields for warden UI & history
    resident_name: Optional[str] = None
    resident_room: Optional[str] = None
    decided_by_name: Optional[str] = None


# Board Schemas for Guard and Warden (Doc 03 Section 3 - strictly strips sensitive fields)
# Notice: destination, reason, guest_phone, decision_note are excluded
class BoardGuestOut(BaseModel):
    guest_name: str
    relation: str
    host_name: str
    host_room: Optional[str] = None
    start_at: datetime
    end_at: datetime
    is_now: bool


class BoardOutOut(BaseModel):
    resident_name: str
    room: Optional[str] = None
    start_at: datetime
    end_at: datetime


class BoardResponse(BaseModel):
    guests: List[BoardGuestOut]
    out: List[BoardOutOut]


# Notification schemas
class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    pass_id: int
    message: str
    created_at: datetime
    read_at: Optional[datetime] = None


class NotificationListResponse(BaseModel):
    unread_count: int
    notifications: List[NotificationOut]
