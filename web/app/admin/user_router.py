import os

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..auth import require_admin, require_admin_api
from ..database import get_db
from ..services.user_service import get_user_list_by_params

router = APIRouter(
    prefix="/admin/users",
    tags=["Admin Users"],
)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))


@router.get("", response_class=HTMLResponse)
def users_page(
    request: Request,
    page: int = 1,
    size: int = 20,
    db: Session = Depends(get_db),
):
    user, redirect = require_admin(request)
    if redirect:
        return redirect

    user_list = get_user_list_by_params(db, page=page, size=size)

    return templates.TemplateResponse(
        request,
        "admin/users.html",
        {"user": user, "user_list": user_list, "active": "admin_users"},
    )


@router.get("/api/list")
def list_users_api(
    request: Request,
    name: str | None = None,
    department: str | None = None,
    is_disabled: bool | None = None,
    is_admin: bool | None = None,
    page: int = 1,
    size: int = 20,
    db: Session = Depends(get_db),
):
    require_admin_api(request)

    return get_user_list_by_params(
        db,
        name=name,
        department=department,
        is_disabled=is_disabled,
        is_admin=is_admin,
        page=page,
        size=size,
    )