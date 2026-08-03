import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from .auth import SESSION_MAX_AGE_SECONDS, get_current_user, require_login
from .auth_router import router as auth_router
from .database import warm_up as warm_up_db
from app.admin.stats_router import router as stats_router
from app.admin.user_router import router as users_router
from app.chat.chat_router import router as chat_router
from app.services.llm_client import ChatAPIError, warm_up as warm_up_chat_api

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@asynccontextmanager
async def lifespan(app: FastAPI):
    # DB는 로그인을 포함한 거의 모든 기능이 의존하는 필수 자원이라, 여기서 실패하면
    # 예외를 그대로 올려서 서버 기동 자체를 실패시킨다 (조용히 넘어가면 첫 요청에서야
    # DB가 안 된다는 걸 알게 되므로, 기동 시점에 바로 아는 게 낫다).
    warm_up_db()

    # Chat API httpx.Client를 미리 만들어둔다. 여기서 못 만들어도(CHAT_API_BASE_URL 미설정 등)
    # 서버 자체는 정상적으로 떠야 하므로 조용히 넘어간다 - 실제 호출 시점에 다시 시도된다.
    try:
        warm_up_chat_api()
    except ChatAPIError:
        pass

    yield

app = FastAPI(title="RAG 챗봇", lifespan=lifespan)

app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET_KEY", "dev-secret-change-me"),
    max_age=SESSION_MAX_AGE_SECONDS,
    same_site="lax",
)

app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(stats_router)
app.include_router(chat_router)
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))


@app.get("/", response_class=HTMLResponse)
def root(request: Request):
    user = get_current_user(request)
    if user:
        return RedirectResponse(url="/main", status_code=303)
    return RedirectResponse(url="/login", status_code=303)


@app.get("/main", response_class=HTMLResponse)
def main_page(request: Request):
    user, redirect = require_login(request)
    if redirect:
        return redirect

    if user.get("is_admin"):
        return RedirectResponse(url="/admin/stats", status_code=303)

    return templates.TemplateResponse(request, "main.html", {"user": user, "active": "chat_new"})
