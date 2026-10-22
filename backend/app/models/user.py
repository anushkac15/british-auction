from sqlalchemy import Enum, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.enums import Role


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(200), unique=True)
    role: Mapped[Role] = mapped_column(
        Enum(Role, native_enum=False, length=20, name="role", create_constraint=True)
    )
    password_hash: Mapped[str | None] = mapped_column(String(255))


Index("uq_users_email_lower", func.lower(User.email), unique=True)
