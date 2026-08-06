"""Login/session and ADMIN-only user-management endpoints."""

from fastapi import APIRouter, Depends, Header, Request, Response
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.iam.dependencies import (
    Principal, bearer_token, get_current_principal, require_customer_service_manage,
    require_user_manage,
)
from app.iam.schemas import (
    ChangePasswordRequest, CurrentUserResponse, DefaultStoreRequest, LoginRequest, LoginResponse,
    RoleAssignmentRequest, RoleListResponse, SelfStoreBindingRequest,
    StoreBindingAssignmentRequest, StoreOptionListResponse, UserCreateRequest,
    UserListResponse, UserProjection, UserUpdateRequest,
)
from app.iam.service import AuthenticationService, DEFAULT_ROLES, UserService, project_user
from app.iam.models import User


auth_router = APIRouter(prefix="/api/v1/auth", tags=["identity-access-management"])
admin_router = APIRouter(prefix="/api/v1/admin/users", tags=["user-management"])


@auth_router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, request: Request, response: Response, session: Session = Depends(get_db)) -> LoginResponse:
    settings = get_settings()
    result = AuthenticationService(
        session,
        settings.iam_session_ttl_minutes,
        max_failures=settings.iam_login_max_failures,
        window_seconds=settings.iam_login_window_seconds,
        cooldown_seconds=settings.iam_login_cooldown_seconds,
        max_active_sessions=settings.iam_max_active_sessions,
    ).login(
        payload.username,
        payload.password,
        request.client.host if request.client is not None else "unknown",
    )
    response.headers["Cache-Control"] = "no-store"
    return result


@auth_router.get("/me", response_model=CurrentUserResponse)
def me(
    response: Response,
    principal: Principal = Depends(get_current_principal),
    session: Session = Depends(get_db),
) -> CurrentUserResponse:
    response.headers["Cache-Control"] = "no-store"
    user = session.get(User, principal.user_id)
    assert user is not None
    return CurrentUserResponse(user=project_user(session, user))


@auth_router.post("/logout", status_code=204)
def logout(
    authorization: str | None = Header(default=None),
    _: Principal = Depends(get_current_principal),
    session: Session = Depends(get_db),
) -> Response:
    AuthenticationService(session, get_settings().iam_session_ttl_minutes).logout(
        bearer_token(authorization)
    )
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


@auth_router.post("/change-password", status_code=204)
def change_password(
    request: ChangePasswordRequest,
    principal: Principal = Depends(get_current_principal),
    session: Session = Depends(get_db),
) -> Response:
    AuthenticationService(session, get_settings().iam_session_ttl_minutes).change_password(
        principal.user_id, request.current_password, request.new_password
    )
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


@auth_router.get("/store-options", response_model=StoreOptionListResponse)
def store_options(
    principal: Principal = Depends(require_customer_service_manage),
    session: Session = Depends(get_db),
) -> StoreOptionListResponse:
    return StoreOptionListResponse(
        items=UserService(session).list_customer_service_store_options(principal.user_id)
    )


@auth_router.put("/store-bindings", response_model=UserProjection)
def replace_own_store_bindings(
    request: SelfStoreBindingRequest,
    principal: Principal = Depends(require_customer_service_manage),
    session: Session = Depends(get_db),
) -> UserProjection:
    return UserService(session).assign_own_customer_service_stores(
        principal.user_id, request.store_ids, request.default_store_id
    )


@auth_router.put("/default-store", response_model=UserProjection)
def set_default_store(
    request: DefaultStoreRequest,
    principal: Principal = Depends(require_customer_service_manage),
    session: Session = Depends(get_db),
) -> UserProjection:
    return UserService(session).set_default_store(principal.user_id, request.store_id)


@admin_router.get("/roles", response_model=RoleListResponse)
def list_roles(_: Principal = Depends(require_user_manage)) -> RoleListResponse:
    return RoleListResponse(items=list(DEFAULT_ROLES))


@admin_router.get("", response_model=UserListResponse)
def list_users(
    _: Principal = Depends(require_user_manage), session: Session = Depends(get_db)
) -> UserListResponse:
    items = UserService(session).list_users()
    return UserListResponse(items=items, total=len(items))


@admin_router.post("", response_model=UserProjection, status_code=201)
def create_user(
    request: UserCreateRequest, _: Principal = Depends(require_user_manage),
    session: Session = Depends(get_db),
) -> UserProjection:
    return UserService(session).create_user(request)


@admin_router.get("/{user_id}", response_model=UserProjection)
def get_user(
    user_id: str, _: Principal = Depends(require_user_manage),
    session: Session = Depends(get_db),
) -> UserProjection:
    return UserService(session).get_user(user_id)


@admin_router.patch("/{user_id}", response_model=UserProjection)
def update_user(
    user_id: str, request: UserUpdateRequest,
    _: Principal = Depends(require_user_manage), session: Session = Depends(get_db),
) -> UserProjection:
    return UserService(session).update_user(user_id, request)


@admin_router.delete("/{user_id}", response_model=UserProjection)
def deactivate_user(
    user_id: str, _: Principal = Depends(require_user_manage),
    session: Session = Depends(get_db),
) -> UserProjection:
    return UserService(session).deactivate_user(user_id)


@admin_router.put("/{user_id}/roles", response_model=UserProjection)
def assign_roles(
    user_id: str, request: RoleAssignmentRequest,
    _: Principal = Depends(require_user_manage), session: Session = Depends(get_db),
) -> UserProjection:
    return UserService(session).assign_roles(user_id, list(request.roles))


@admin_router.put("/{user_id}/store-bindings", response_model=UserProjection)
def assign_store_bindings(
    user_id: str, request: StoreBindingAssignmentRequest,
    _: Principal = Depends(require_user_manage), session: Session = Depends(get_db),
) -> UserProjection:
    return UserService(session).assign_store_bindings(user_id, list(request.store_bindings))
