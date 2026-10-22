from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.clock import Clock, get_clock
from app.db import get_db
from app.enums import Role
from app.errors import AppError
from app.models import User
from app.security import read_token

DbSession = Annotated[Session, Depends(get_db)]
ClockDep = Annotated[Clock, Depends(get_clock)]

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)] = None,
) -> User:
    """The acting user comes from the `Authorization: Bearer <token>` header issued at login."""
    if credentials is None:
        raise AppError(401, "Please log in to continue", "unauthenticated")
    user_id = read_token(credentials.credentials)
    user = db.get(User, user_id) if user_id is not None else None
    if user is None:
        raise AppError(401, "Your session has expired. Please log in again", "unauthenticated")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_buyer(user: CurrentUser) -> User:
    if user.role != Role.BUYER:
        raise AppError(403, "Only buyers can do this", "forbidden")
    return user


def require_supplier(user: CurrentUser) -> User:
    if user.role != Role.SUPPLIER:
        raise AppError(403, "Only suppliers can place bids", "forbidden")
    return user


Buyer = Annotated[User, Depends(require_buyer)]
Supplier = Annotated[User, Depends(require_supplier)]
