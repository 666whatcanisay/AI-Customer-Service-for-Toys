"""Secure bootstrap for the first ADMIN; passwords are read with getpass."""

import argparse
import getpass

from app.database import SessionLocal
from app.iam.schemas import RoleName, UserCreateRequest
from app.iam.service import UserService, ensure_default_roles


def main() -> int:
    parser = argparse.ArgumentParser(description="Create an AI-CS bootstrap administrator")
    parser.add_argument("--username", required=True)
    parser.add_argument("--display-name", required=True)
    args = parser.parse_args()
    password = getpass.getpass("Temporary password (8-128 characters; change required at first login): ")
    confirmation = getpass.getpass("Confirm password: ")
    if password != confirmation:
        raise SystemExit("Passwords do not match.")
    with SessionLocal() as session:
        ensure_default_roles(session)
        created = UserService(session).create_user(UserCreateRequest(
            username=args.username, password=password, display_name=args.display_name,
            roles=[RoleName.ADMIN], store_bindings=[],
        ))
    print(f"Created ADMIN user {created.username} ({created.id}).")
    print("The account must replace the temporary password before business API use.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
