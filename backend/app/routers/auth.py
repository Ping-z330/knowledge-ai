"""认证端点：登录签发 JWT、获取当前用户。"""

import secrets

from fastapi import APIRouter, Depends, HTTPException

from ..auth import create_access_token, require_auth
from ..config import get_settings
from ..schemas import AuthUser, LoginRequest, TokenResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest) -> dict:
    settings = get_settings()
    if not settings.admin_password:
        raise HTTPException(
            status_code=400,
            detail="管理员密码未配置，请联系管理员设置 ADMIN_PASSWORD。",
        )
    if not settings.jwt_secret:
        raise HTTPException(
            status_code=500,
            detail="JWT_SECRET 未配置，无法签发令牌。",
        )
    # 用户名普通比较，密码用常量时间比较
    if payload.username != settings.admin_username or not secrets.compare_digest(
        payload.password, settings.admin_password
    ):
        raise HTTPException(
            status_code=401,
            detail="用户名或密码错误。",
        )
    token, expires_in = create_access_token(settings.admin_username)
    return {"access_token": token, "token_type": "bearer", "expires_in": expires_in}


@router.get("/me", response_model=AuthUser)
def me(current: AuthUser = Depends(require_auth)) -> AuthUser:
    return current
