"""User lifecycle, fixed-role assignment, Store binding, and session service."""

from datetime import datetime, timedelta, timezone
import unicodedata
from uuid import uuid4

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.errors import AppError
from app.iam.models import (
    Permission, Role, RolePermission, User, UserRole, UserSession, UserStoreBinding,
)
from app.iam.schemas import (
    LoginResponse, RoleName, StoreBindingInput, StoreBindingProjection,
    StoreOptionProjection, UserCreateRequest, UserProjection, UserStatus,
    UserUpdateRequest, canonical_username,
)
from app.iam.security import create_session_token, hash_password, hash_session_token, verify_password
from app.test_catalog.models import TestStore


PERMISSIONS_BY_ROLE: dict[RoleName, frozenset[str]] = {
    RoleName.CUSTOMER_SERVICE: frozenset({
        "workspace.access", "ai.reply", "feedback.submit", "customer_service.manage",
    }),
    RoleName.OPERATOR: frozenset({
        "product.manage", "sku.manage", "knowledge.manage", "faq.manage",
        "ai_quality.view", "store.view", "feedback.view",
    }),
    RoleName.ADMIN: frozenset({
        "workspace.access", "ai.reply", "feedback.submit", "customer_service.manage",
        "product.manage", "sku.manage", "knowledge.manage", "faq.manage",
        "ai_quality.view", "store.view", "feedback.view", "user.manage",
    }),
}
DEFAULT_ROLES = tuple(RoleName)
_FAKE_PASSWORD_HASH = hash_password("AI-CS invalid credential sentinel")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_username(username: str) -> str:
    return unicodedata.normalize("NFKC", username.strip()).casefold()


def permissions_for_roles(roles: list[RoleName]) -> list[str]:
    return sorted(set().union(*(PERMISSIONS_BY_ROLE[role] for role in roles)))


def ensure_default_roles(session: Session) -> None:
    existing = set(session.scalars(select(Role.role_name)).all())
    for role in DEFAULT_ROLES:
        if role.value not in existing:
            session.add(Role(role_name=role.value))
    session.flush()
    existing_permissions = set(session.scalars(select(Permission.permission_name)).all())
    for permission_name in sorted(set().union(*PERMISSIONS_BY_ROLE.values())):
        if permission_name not in existing_permissions:
            session.add(Permission(permission_name=permission_name))
    session.flush()
    roles_by_name = {
        row.role_name: row for row in session.scalars(select(Role)).all()
    }
    permissions_by_name = {
        row.permission_name: row for row in session.scalars(select(Permission)).all()
    }
    existing_links = set(session.execute(
        select(RolePermission.role_id, RolePermission.permission_id)
    ).all())
    for role, permission_names in PERMISSIONS_BY_ROLE.items():
        role_id = roles_by_name[role.value].id
        for permission_name in permission_names:
            permission_id = permissions_by_name[permission_name].id
            if (role_id, permission_id) not in existing_links:
                session.add(RolePermission(role_id=role_id, permission_id=permission_id))
    session.flush()


def _role_rows(session: Session, user_id: str) -> list[Role]:
    return list(session.scalars(
        select(Role).join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user_id).order_by(Role.role_name)
    ))


def role_names(session: Session, user_id: str) -> list[RoleName]:
    return [RoleName(row.role_name) for row in _role_rows(session, user_id)]


def _binding_rows(session: Session, user_id: str) -> list[tuple[UserStoreBinding, TestStore]]:
    return list(session.execute(
        select(UserStoreBinding, TestStore)
        .join(TestStore, TestStore.id == UserStoreBinding.store_id)
        .where(UserStoreBinding.user_id == user_id)
        .order_by(UserStoreBinding.is_default.desc(), TestStore.store_name, TestStore.id)
    ).all())


def project_user(session: Session, user: User) -> UserProjection:
    roles = role_names(session, user.id)
    stores = [
        StoreBindingProjection(
            id=binding.id, store_id=store.id, store_code=store.store_code,
            store_name=store.store_name, platform=store.platform,
            is_default=binding.is_default,
        )
        for binding, store in _binding_rows(session, user.id)
    ]
    return UserProjection(
        id=user.id, username=user.username, display_name=user.display_name,
        status=UserStatus(user.status), roles=roles,
        permissions=permissions_for_roles(roles), stores=stores,
        must_change_password=user.must_change_password,
        all_store_access=bool({RoleName.ADMIN, RoleName.OPERATOR}.intersection(roles)),
        created_at=user.created_at, updated_at=user.updated_at,
    )


def _validate_default_store(roles: list[RoleName], bindings: list[StoreBindingInput]) -> None:
    defaults = sum(1 for item in bindings if item.is_default)
    if defaults > 1:
        raise AppError("STORE_BINDING_INVALID", "Only one default Store is allowed.", status_code=422)


def _validate_stores(session: Session, bindings: list[StoreBindingInput]) -> None:
    requested = {item.store_id for item in bindings}
    existing = set(session.scalars(select(TestStore.id).where(TestStore.id.in_(requested))).all()) if requested else set()
    if existing != requested:
        raise AppError("STORE_BINDING_INVALID", "One or more Stores do not exist.", status_code=422)


def _replace_roles(session: Session, user: User, roles: list[RoleName]) -> None:
    ensure_default_roles(session)
    rows = list(session.scalars(select(Role).where(Role.role_name.in_([role.value for role in roles]))))
    if len(rows) != len(roles):
        raise AppError("ROLE_INVALID", "One or more roles are invalid.", status_code=422)
    session.execute(delete(UserRole).where(UserRole.user_id == user.id))
    session.add_all(UserRole(user_id=user.id, role_id=row.id) for row in rows)
    session.flush()


def _replace_bindings(session: Session, user: User, bindings: list[StoreBindingInput]) -> None:
    _validate_stores(session, bindings)
    session.execute(delete(UserStoreBinding).where(UserStoreBinding.user_id == user.id))
    session.add_all(
        UserStoreBinding(
            user_id=user.id, store_id=item.store_id, is_default=item.is_default,
            created_at=utc_now(),
        )
        for item in bindings
    )
    session.flush()


def user_or_404(session: Session, user_id: str) -> User:
    user = session.get(User, user_id)
    if user is None:
        raise AppError("USER_NOT_FOUND", "User not found.", status_code=404)
    return user


class UserService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_users(self) -> list[UserProjection]:
        users = self.session.scalars(select(User).order_by(User.username_normalized)).all()
        return [project_user(self.session, user) for user in users]

    def create_user(
        self, request: UserCreateRequest, *, must_change_password: bool = True
    ) -> UserProjection:
        roles = list(request.roles)
        bindings = list(request.store_bindings)
        _validate_default_store(roles, bindings)
        _validate_stores(self.session, bindings)
        now = utc_now()
        user = User(
            id=str(uuid4()), username=canonical_username(request.username),
            username_normalized=normalize_username(request.username),
            password_hash=hash_password(request.password),
            must_change_password=must_change_password,
            display_name=request.display_name, status=UserStatus.ACTIVE.value,
            created_at=now, updated_at=now,
        )
        self.session.add(user)
        try:
            self.session.flush()
        except IntegrityError:
            self.session.rollback()
            raise AppError("USERNAME_CONFLICT", "Username is already registered.", status_code=409) from None
        _replace_roles(self.session, user, roles)
        _replace_bindings(self.session, user, bindings)
        self.session.commit()
        return project_user(self.session, user)

    def get_user(self, user_id: str) -> UserProjection:
        return project_user(self.session, user_or_404(self.session, user_id))

    def update_user(self, user_id: str, request: UserUpdateRequest) -> UserProjection:
        user = user_or_404(self.session, user_id)
        revoke = False
        if request.display_name is not None:
            user.display_name = request.display_name
        if request.password is not None:
            user.password_hash = hash_password(request.password)
            user.must_change_password = True
            revoke = True
        if request.status is not None:
            user.status = request.status.value
            revoke = request.status == UserStatus.DISABLED
        user.updated_at = utc_now()
        if revoke:
            self._revoke_user_sessions(user.id)
        self.session.commit()
        return project_user(self.session, user)

    def assign_roles(self, user_id: str, roles: list[RoleName]) -> UserProjection:
        user = user_or_404(self.session, user_id)
        current_bindings = [
            StoreBindingInput(store_id=binding.store_id, is_default=binding.is_default)
            for binding, _ in _binding_rows(self.session, user.id)
        ]
        _validate_default_store(roles, current_bindings)
        _replace_roles(self.session, user, roles)
        user.updated_at = utc_now()
        self.session.commit()
        return project_user(self.session, user)

    def assign_store_bindings(
        self, user_id: str, bindings: list[StoreBindingInput]
    ) -> UserProjection:
        user = user_or_404(self.session, user_id)
        _validate_default_store(role_names(self.session, user.id), bindings)
        _replace_bindings(self.session, user, bindings)
        user.updated_at = utc_now()
        self.session.commit()
        return project_user(self.session, user)

    def list_customer_service_store_options(self, user_id: str) -> list[StoreOptionProjection]:
        user = user_or_404(self.session, user_id)
        if RoleName.CUSTOMER_SERVICE not in role_names(self.session, user.id):
            raise AppError(
                "AUTHORIZATION_DENIED",
                "Only CUSTOMER_SERVICE accounts select customer Stores.",
                status_code=403,
            )
        stores = self.session.scalars(
            select(TestStore).where(TestStore.customer_service_status == "ENABLED")
            .order_by(TestStore.store_name, TestStore.id)
        ).all()
        return [
            StoreOptionProjection(
                store_id=store.id, store_code=store.store_code,
                store_name=store.store_name, platform=store.platform,
            )
            for store in stores
        ]

    def assign_own_customer_service_stores(
        self, user_id: str, store_ids: list[int]
    ) -> UserProjection:
        allowed = {item.store_id for item in self.list_customer_service_store_options(user_id)}
        requested = set(store_ids)
        if not requested or not requested.issubset(allowed):
            raise AppError(
                "STORE_BINDING_INVALID",
                "Customer Store selection must contain enabled Store options only.",
                status_code=422,
            )
        return self.assign_store_bindings(
            user_id,
            [StoreBindingInput(store_id=store_id, is_default=False) for store_id in store_ids],
        )

    def deactivate_user(self, user_id: str) -> UserProjection:
        return self.update_user(user_id, UserUpdateRequest(status=UserStatus.DISABLED))

    def _revoke_user_sessions(self, user_id: str) -> None:
        self.session.execute(
            update(UserSession).where(
                UserSession.user_id == user_id, UserSession.revoked_at.is_(None)
            ).values(revoked_at=utc_now())
        )


class AuthenticationService:
    def __init__(self, session: Session, ttl_minutes: int) -> None:
        self.session = session
        self.ttl_minutes = ttl_minutes

    def login(self, username: str, password: str) -> LoginResponse:
        user = self.session.scalar(
            select(User).where(User.username_normalized == normalize_username(username))
        )
        encoded = user.password_hash if user is not None else _FAKE_PASSWORD_HASH
        valid = verify_password(password, encoded)
        if user is None or not valid or user.status != UserStatus.ACTIVE.value:
            raise AppError(
                "AUTHENTICATION_FAILED", "Username or password is invalid.", status_code=401
            )
        token = create_session_token()
        now = utc_now()
        expires_at = now + timedelta(minutes=self.ttl_minutes)
        self.session.add(UserSession(
            id=str(uuid4()), user_id=user.id, token_hash=hash_session_token(token),
            created_at=now, expires_at=expires_at,
        ))
        self.session.commit()
        return LoginResponse(
            access_token=token, expires_at=expires_at,
            user=project_user(self.session, user),
        )

    def logout(self, token: str) -> None:
        row = self.session.scalar(
            select(UserSession).where(UserSession.token_hash == hash_session_token(token))
        )
        if row is not None and row.revoked_at is None:
            row.revoked_at = utc_now()
            self.session.commit()

    def change_password(
        self, user_id: str, current_password: str, new_password: str
    ) -> None:
        user = user_or_404(self.session, user_id)
        if not verify_password(current_password, user.password_hash):
            raise AppError(
                "AUTHENTICATION_FAILED", "Current password is invalid.", status_code=401
            )
        if verify_password(new_password, user.password_hash):
            raise AppError(
                "VALIDATION_ERROR", "New password must differ from the current password.",
                status_code=422,
            )
        user.password_hash = hash_password(new_password)
        user.must_change_password = False
        user.updated_at = utc_now()
        self.session.execute(
            update(UserSession).where(
                UserSession.user_id == user.id, UserSession.revoked_at.is_(None)
            ).values(revoked_at=utc_now())
        )
        self.session.commit()
