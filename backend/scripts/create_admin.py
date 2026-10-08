"""Create an administrator account (admins cannot self-register).

Usage: python -m scripts.create_admin admin@example.com "First" ["Last"]
The password is read interactively so it never lands in shell history.
"""

import asyncio
import getpass
import sys

from pydantic import TypeAdapter, ValidationError

from app.core.security import hash_password
from app.db.session import SessionLocal, engine
from app.models import Role, User
from app.schemas.user import Password
from app.services import user_service


async def main(email: str, first_name: str, last_name: str | None) -> None:
    async with SessionLocal() as db:
        if await user_service.get_by_email(db, email):
            sys.exit("A user with this email already exists")
        password = getpass.getpass("Password: ")
        if password != getpass.getpass("Confirm password: "):
            sys.exit("Passwords do not match")
        try:
            TypeAdapter(Password).validate_python(password)
        except ValidationError as exc:
            sys.exit(f"Weak password: {exc.errors()[0]['msg']}")
        db.add(
            User(
                email=email.strip().lower(),
                first_name=first_name,
                last_name=last_name,
                hashed_password=hash_password(password),
                role=Role.ADMIN,
            )
        )
        await db.commit()
        print(f"Admin created: {email}")
    await engine.dispose()


if __name__ == "__main__":
    if len(sys.argv) not in (3, 4):
        sys.exit('Usage: python -m scripts.create_admin <email> "<first name>" ["<last name>"]')
    asyncio.run(main(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) == 4 else None))
