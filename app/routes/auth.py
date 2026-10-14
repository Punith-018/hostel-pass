from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import create_access_token, get_current_user, verify_password
from app.db import get_db
from app.models import User
from app.schemas import LoginRequest, TokenResponse, UserOut

router = APIRouter(tags=["auth"])


@router.post("/auth/login", response_model=TokenResponse)
def login(request: LoginRequest, db: Session = Depends(get_db)):
    # Look up user by username
    user = db.query(User).filter(User.username == request.username).first()

    # Spec 03 Section 1: Wrong username or password both return identical 401
    # Also verify is_active
    if not user or not verify_password(request.password, user.password_hash) or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    # 12-hour JWT token with user id and role
    token = create_access_token(user_id=user.id, role=user.role)
    return TokenResponse(token=token, user=user)


@router.get("/me", response_model=UserOut)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user
