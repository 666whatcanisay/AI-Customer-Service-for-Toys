from sqlalchemy import select
from sqlalchemy.orm import Session

from app.iam import initial_users_cli
from app.iam.models import User
from app.iam.schemas import RoleName
from app.iam.service import role_names


class _SessionContext:
    def __init__(self, session: Session) -> None:
        self.session = session

    def __enter__(self) -> Session:
        return self.session

    def __exit__(self, *_: object) -> None:
        return None


def test_initial_user_cli_creates_three_unicode_safe_accounts_and_skips_duplicates(
    session: Session, monkeypatch, capsys
) -> None:
    prompts = iter(["TempPass", "TempPass"])
    monkeypatch.setattr(initial_users_cli, "SessionLocal", lambda: _SessionContext(session))
    monkeypatch.setattr(initial_users_cli.getpass, "getpass", lambda _: next(prompts))

    assert initial_users_cli.main() == 0
    users = list(session.scalars(select(User).order_by(User.username_normalized)))
    assert {user.username for user in users} == {"admin", "Wa", "江"}
    assert all(user.must_change_password for user in users)
    assert {
        user.username: role_names(session, user.id)[0] for user in users
    } == {
        "admin": RoleName.ADMIN,
        "Wa": RoleName.CUSTOMER_SERVICE,
        "江": RoleName.OPERATOR,
    }
    assert "TempPass" not in capsys.readouterr().out

    monkeypatch.setattr(
        initial_users_cli.getpass,
        "getpass",
        lambda _: (_ for _ in ()).throw(AssertionError("duplicate-only run must not prompt")),
    )
    assert initial_users_cli.main() == 0
    assert session.scalar(select(User).where(User.username == "Wa")) is not None
    assert len(list(session.scalars(select(User)))) == 3
