from __future__ import annotations

import datetime as dt

import jwt
from fastapi import Request, HTTPException, status

from config.settings import settings

ALGORITHM = "HS256"
COOKIE_NAME = "admin_session"
TOKEN_TTL_HOURS = 12


def create_token(username: str, role: str = "owner") -> str:
    payload = {
        "sub": username,
        "role": role,
        "exp": dt.datetime.utcnow() + dt.timedelta(hours=TOKEN_TTL_HOURS),
    }
    return jwt.encode(payload, settings.ADMIN_PANEL_SECRET, algorithm=ALGORITHM)


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.ADMIN_PANEL_SECRET, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None


def get_current_admin(request: Request) -> dict:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/admin/login"})
    data = decode_token(token)
    if not data:
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/admin/login"})
    return data


def require_role(*roles: str):
    def dep(admin: dict = None):
        return admin
    return dep
