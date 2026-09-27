"""Authentication dependencies for FastAPI."""

from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer

from app.core.config import settings
from app.core.security import decode_access_token

# auto_error=False so we can implement the "optional auth" behaviour ourselves.
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_PREFIX}/auth/token",
    auto_error=False,
)


def _resolve(token: Optional[str]) -> Optional[str]:
    if not token:
        return None
    payload = decode_access_token(token)
    if not payload:
        return None
    return payload.get("sub")


def optional_user(
    request: Request,
    token: Optional[str] = Depends(oauth2_scheme),
) -> Optional[str]:
    username = _resolve(token)
    # Stash for the rate limiter / audit log.
    request.state.user = username
    return username


def get_current_user(
    request: Request,
    token: Optional[str] = Depends(oauth2_scheme),
) -> Optional[str]:
    username = _resolve(token)
    request.state.user = username

    if settings.AUTH_REQUIRED and not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return username
