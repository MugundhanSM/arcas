"""Authentication endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.v1.dependencies import get_current_user
from app.core.security import create_access_token, hash_password, verify_password
from app.database.dependencies import get_db
from app.repositories.audit_repository import AuditRepository
from app.repositories.user_repository import UserRepository

router = APIRouter()


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    password: str = Field(..., min_length=6, max_length=128)


class RegisterResponse(BaseModel):
    username: str
    message: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str


class MeResponse(BaseModel):
    username: str | None = None
    authenticated: bool


@router.post(
    "/auth/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
)
def register(
    payload: RegisterRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    existing = UserRepository.find_by_username(db, payload.username)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username is already registered.",
        )

    UserRepository.create(
        db=db,
        username=payload.username,
        hashed_password=hash_password(payload.password),
    )

    AuditRepository.record(
        db=db,
        action="user.register",
        actor=payload.username,
        detail="New user registered.",
    )

    return RegisterResponse(
        username=payload.username,
        message="User registered successfully.",
    )


@router.post("/auth/token", response_model=TokenResponse)
def login_for_access_token(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    user = UserRepository.find_by_username(db, form_data.username)

    if user is None or not verify_password(
        form_data.password, user.hashed_password
    ):
        AuditRepository.record(
            db=db,
            action="auth.login.failed",
            actor=form_data.username,
            detail="Invalid credentials.",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled.",
        )

    token = create_access_token(subject=user.username)

    AuditRepository.record(
        db=db,
        action="auth.login.success",
        actor=user.username,
        detail="Issued access token.",
    )

    return TokenResponse(access_token=token, username=user.username)


@router.get("/auth/me", response_model=MeResponse)
def read_me(username: str | None = Depends(get_current_user)):
    return MeResponse(username=username, authenticated=bool(username))
