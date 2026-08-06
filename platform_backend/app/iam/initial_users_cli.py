"""Secure, duplicate-safe bootstrap for the three approved internal identities."""

import getpass

from sqlalchemy import select

from app.database import SessionLocal
from app.iam.models import User
from app.iam.schemas import RoleName, UserCreateRequest
from app.iam.service import UserService, ensure_default_roles, normalize_username


INITIAL_USERS = (
    ("admin", "超级管理员", RoleName.ADMIN),
    ("Wa", "客服主管", RoleName.CUSTOMER_SERVICE),
    ("江", "运营主管", RoleName.OPERATOR),
)


def main() -> int:
    with SessionLocal() as session:
        ensure_default_roles(session)
        existing = {
            value for value in session.scalars(select(User.username_normalized)).all()
        }
        missing = [item for item in INITIAL_USERS if normalize_username(item[0]) not in existing]
        for username, _, role in INITIAL_USERS:
            if normalize_username(username) in existing:
                print(f"SKIPPED existing {role.value} account: {username}")
        if not missing:
            print("No account changes were required.")
            return 0

        password = getpass.getpass(
            "Shared temporary password (8-128 characters; each account must change it): "
        )
        confirmation = getpass.getpass("Confirm temporary password: ")
        if password != confirmation:
            raise SystemExit("Passwords do not match.")

        service = UserService(session)
        for username, display_name, role in missing:
            created = service.create_user(UserCreateRequest(
                username=username,
                password=password,
                display_name=display_name,
                roles=[role],
                store_bindings=[],
            ))
            print(f"CREATED {role.value} account: {created.username}")
        print("All created accounts must replace the temporary password before business API use.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
