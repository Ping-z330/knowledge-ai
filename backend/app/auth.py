"""JWT + API_TOKEN 双轨鉴权。

- UI 登录通过 /api/auth/login 获取 JWT，存于前端 localStorage。
- 脚本/外部调用可继续使用 API_TOKEN（向后兼容）。
- require_auth 始终强制鉴权，不再有"token 为空则放行"的后门。
"""

import secrets
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import get_settings
from .schemas import AuthUser

_bearer_scheme = HTTPBearer(auto_error=False)


def create_access_token(username: str) -> tuple[str, int]:
    """签发 JWT。jwt_secret 或 admin_password 未配置时抛 RuntimeError（fail-closed）。"""
    settings = get_settings()
    if not settings.jwt_secret:
        raise RuntimeError("JWT_SECRET not configured")
    if not settings.admin_password:
        raise RuntimeError("ADMIN_PASSWORD not configured")
    now = datetime.now(timezone.utc)
    exp = now + timedelta(hours=settings.jwt_expire_hours)
    payload = {"sub": username, "iat": now, "exp": exp}
    token = jwt.encode(payload, settings.jwt_secret, algorithm="HS256")
    return token, settings.jwt_expire_hours * 3600


def require_auth(
    credentials: HTTPAuthorizationCredentials | None = Security(_bearer_scheme),
) -> AuthUser:
    """接受 JWT 或 API_TOKEN（向后兼容脚本）。始终强制鉴权。"""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header. Provide Bearer <jwt|api_token>.",
        )

    token = credentials.credentials
    settings = get_settings()

    # 1) 先尝试 JWT
    if settings.jwt_secret:
        try:
            payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
            username = payload.get("sub")
            if username == settings.admin_username:
                return AuthUser(username=username, auth_method="jwt")
        except jwt.PyJWTError:
            pass  # 不是合法 JWT，回落到 API_TOKEN

    # 2) 回落到 API_TOKEN（向后兼容已有脚本）
    if settings.api_token and secrets.compare_digest(token, settings.api_token):
        return AuthUser(username="api-token", auth_method="api-token")

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid credentials",
    )
