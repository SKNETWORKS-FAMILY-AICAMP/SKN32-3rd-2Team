import time

import bcrypt
from fastapi import Request, HTTPException, status
from fastapi.responses import RedirectResponse

# 세션 유효 시간: 3시간
SESSION_MAX_AGE_SECONDS = 3 * 60 * 60


def hash_password(raw_password: str) -> str:
    hashed = bcrypt.hashpw(raw_password.encode("utf-8"), bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(raw_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(raw_password.encode("utf-8"), hashed_password.encode("utf-8"))


def create_session(request: Request, user_id: str, name: str, is_admin: bool) -> None:
    request.session["user_id"] = user_id
    request.session["name"] = name
    request.session["is_admin"] = is_admin
    request.session["login_at"] = time.time()


def clear_session(request: Request) -> None:
    request.session.clear()


def get_current_user(request: Request):
    """세션에 로그인 정보가 있고, 3시간 이내라면 사용자 정보를 반환한다.
    없거나 만료되었으면 None을 반환한다."""
    user_id = request.session.get("user_id")
    login_at = request.session.get("login_at")

    if not user_id or not login_at:
        return None

    if time.time() - login_at > SESSION_MAX_AGE_SECONDS:
        request.session.clear()
        return None

    return {
        "user_id": user_id,
        "name": request.session.get("name"),
        "is_admin": request.session.get("is_admin", False),
    }


def require_login(request: Request):
    """페이지 라우트에서 로그인 여부를 검사하고, 미로그인 시 로그인 화면으로 리다이렉트한다."""
    user = get_current_user(request)
    if user is None:
        return None, RedirectResponse(url="/login", status_code=303)
    return user, None

def require_login_api(request: Request):
    """API 라우트에서 로그인 여부를 검사하고, 미로그인 시 401을 반환한다."""
    user = get_current_user(request)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="로그인이 필요합니다."
        )

    return user


def require_admin(request: Request):
    """관리자 전용 페이지 라우트에서 로그인 및 관리자 권한을 검사한다.
    미로그인 시 로그인 화면으로, 관리자가 아니면 메인 화면으로 리다이렉트한다."""
    user = get_current_user(request)
    if user is None:
        return None, RedirectResponse(url="/login", status_code=303)
    if not user.get("is_admin"):
        return None, RedirectResponse(url="/main", status_code=303)
    return user, None


def require_admin_api(request: Request):
    """관리자 전용 API 라우트에서 로그인 및 관리자 권한을 검사한다.
    미로그인 시 401, 관리자가 아니면 403을 반환한다."""
    user = require_login_api(request)
    if not user.get("is_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="관리자만 접근할 수 있습니다."
        )
    return user