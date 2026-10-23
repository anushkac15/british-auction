from fastapi import APIRouter
from redis import Redis
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.deps import ClockDep, CurrentUser, DbSession
from app.errors import AppError
from app.models import User
from app.schemas.inputs import LoginInput, RegisterInput
from app.schemas.outputs import AccountOut, AuthResponse, MeResponse
from app.security import burn_password_check, create_token, hash_password, verify_password
from app.throttle import MemoryLoginThrottle, RedisLoginThrottle

router = APIRouter(prefix="/auth", tags=["auth"])


def _build_login_throttle() -> MemoryLoginThrottle | RedisLoginThrottle:
    if settings.login_throttle_store == "redis":
        client = Redis.from_url(settings.redis_url, socket_timeout=1, socket_connect_timeout=1)
        return RedisLoginThrottle(client, settings.login_max_failures, settings.login_lockout_seconds)
    return MemoryLoginThrottle(settings.login_max_failures, settings.login_lockout_seconds)


login_throttle = _build_login_throttle()


def _account(user: User) -> AccountOut:
    return AccountOut(id=user.id, name=user.name, email=user.email, role=user.role)


def _email_taken() -> AppError:
    return AppError(409, "An account with this email already exists", "email_taken", "email")


@router.post("/register", response_model=AuthResponse, status_code=201)
def register(body: RegisterInput, db: DbSession, clock: ClockDep) -> AuthResponse:
    if db.scalar(select(User.id).where(func.lower(User.email) == body.email)) is not None:
        raise _email_taken()
    user = User(name=body.name, email=body.email, role=body.role, password_hash=hash_password(body.password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise _email_taken() from None
    return AuthResponse(server_now=clock.now(), user=_account(user), access_token=create_token(user.id))


@router.post("/login", response_model=AuthResponse)
def login(body: LoginInput, db: DbSession, clock: ClockDep) -> AuthResponse:
    wait = login_throttle.retry_after(body.email)
    if wait is not None:
        minutes = max(1, round(wait / 60))
        raise AppError(
            429,
            f"Too many failed login attempts. Try again in {minutes} minute{'' if minutes == 1 else 's'}.",
            "too_many_attempts",
        )
    user = db.scalar(select(User).where(func.lower(User.email) == body.email))
    if user is None:
        burn_password_check(body.password)
    if user is None or not verify_password(body.password, user.password_hash):
        login_throttle.record_failure(body.email)
        raise AppError(401, "Incorrect email or password", "invalid_credentials")
    login_throttle.reset(body.email)
    return AuthResponse(server_now=clock.now(), user=_account(user), access_token=create_token(user.id))


@router.get("/me", response_model=MeResponse)
def me(user: CurrentUser, clock: ClockDep) -> MeResponse:
    return MeResponse(server_now=clock.now(), user=_account(user))
