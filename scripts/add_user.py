"""One-off script to insert a single user into the database.

Edit the values in `main()` below, then run:
    python -m scripts.add_user
"""

import asyncio
import uuid

from app.core.security import hash_password
from app.db.session import AsyncSessionLocal
from app.models.enums import UserRole
from app.models.user import User
from app.repositories.user_repository import UserRepository


async def add_user(
    *,
    name: str,
    email: str,
    role: UserRole,
    password: str,
    manager_id: uuid.UUID | None = None,
    is_active: bool = True,
) -> User:
    async with AsyncSessionLocal() as session:
        repo = UserRepository(session)

        existing = await repo.get_by_email(email)
        if existing is not None:
            raise ValueError(f"A user with email '{email}' already exists (id={existing.id}).")

        user = User(
            id=uuid.uuid4(),
            name=name,
            email=email,
            password_hash=hash_password(password),
            role=role,
            manager_id=manager_id,
            is_active=is_active,
        )
        user = await repo.create(user)
        await session.commit()
        return user


async def main() -> None:
    # ── Edit these values ────────────────────────────────────────────
    name = "Jane Doe"
    email = "jane.doe@example.com"
    role = UserRole.IT_ADMIN  # UserRole.EMPLOYEE | UserRole.MANAGER | UserRole.IT_ADMIN
    password = "password@123"
    # ─────────────────────────────────────────────────────────────────

    user = await add_user(name=name, email=email, role=role, password=password)
    print(f"Created user: id={user.id} name={user.name!r} email={user.email} role={user.role.value}")


if __name__ == "__main__":
    asyncio.run(main())
