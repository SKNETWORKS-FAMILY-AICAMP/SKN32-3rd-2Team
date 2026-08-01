import os
import re

from dotenv import load_dotenv

load_dotenv()

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from .auth import (
    SESSION_MAX_AGE_SECONDS,
    clear_session,
    create_session,
    get_current_user,
    hash_password,
    require_login,
    verify_password,
)
from .database import get_db
from .models import User
from .services.user_service import record_login
from app.admin.stats_router import router as stats_router
from app.admin.user_router import router as users_router
from app.chat.chat_router import router as chat_router

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


app = FastAPI(title="RAG 챗봇")

app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET_KEY", "dev-secret-change-me"),
    max_age=SESSION_MAX_AGE_SECONDS,
    same_site="lax",
)

app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
app.include_router(users_router)
app.include_router(stats_router)
app.include_router(chat_router)
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

USER_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{4,20}$")


@app.get("/", response_class=HTMLResponse)
def root(request: Request):
    user = get_current_user(request)
    if user:
        return RedirectResponse(url="/main", status_code=303)
    return RedirectResponse(url="/login", status_code=303)


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    user = get_current_user(request)
    if user:
        return RedirectResponse(url="/main", status_code=303)
    return templates.TemplateResponse(request, "login.html", {"error": None})


@app.post("/auth/login")
def login_submit(
    request: Request,
    user_id: str = Form(...),
    passwd: str = Form(...),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)

    if user is None or not verify_password(passwd, user.passwd):
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "아이디 또는 비밀번호가 올바르지 않습니다."},
            status_code=401,
        )

    if user.is_disabled:
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "비활성화된 계정입니다. 관리자에게 문의하세요."},
            status_code=403,
        )

    create_session(request, user.user_id, user.name, user.is_admin)
    record_login(db, user.user_id)
    return RedirectResponse(url="/main", status_code=303)


@app.post("/auth/signup")
def signup_submit(
    request: Request,
    user_id: str = Form(...),
    passwd: str = Form(...),
    passwd_confirm: str = Form(...),
    name: str = Form(...),
    department: str = Form(...),
    db: Session = Depends(get_db),
):
    if not USER_ID_PATTERN.match(user_id):
        return JSONResponse(
            status_code=400,
            content={"detail": "아이디는 영문/숫자 4~20자로 입력해주세요."},
        )

    if len(passwd) < 8:
        return JSONResponse(
            status_code=400,
            content={"detail": "비밀번호는 8자 이상이어야 합니다."},
        )

    if passwd != passwd_confirm:
        return JSONResponse(
            status_code=400,
            content={"detail": "비밀번호가 일치하지 않습니다."},
        )

    if db.get(User, user_id) is not None:
        return JSONResponse(
            status_code=409,
            content={"detail": "이미 사용 중인 아이디입니다."},
        )

    new_user = User(
        user_id=user_id,
        passwd=hash_password(passwd),
        name=name,
        department=department,
        is_admin=False,
        is_disabled=False,
    )
    db.add(new_user)
    db.commit()

    return JSONResponse(status_code=201, content={"detail": "회원가입이 완료되었습니다. 로그인해주세요."})


@app.post("/auth/logout")
def logout(request: Request):
    clear_session(request)
    return RedirectResponse(url="/login", status_code=303)


@app.get("/main", response_class=HTMLResponse)
def main_page(request: Request):
    user, redirect = require_login(request)
    if redirect:
        return redirect

    if user.get("is_admin"):
        return RedirectResponse(url="/admin/stats", status_code=303)

    return templates.TemplateResponse(request, "main.html", {"user": user, "active": "chat_new"})
