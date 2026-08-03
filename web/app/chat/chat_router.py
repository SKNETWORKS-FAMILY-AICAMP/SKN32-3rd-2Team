import os

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..auth import require_login, require_login_api
from ..database import get_db
from ..services.chat_service import (
    ChatServiceError,
    create_chatroom,
    delete_chatroom,
    get_messages,
    get_owned_chatroom,
    list_chatrooms,
    send_message,
)

router = APIRouter(
    prefix="/chat",
    tags=["Chat"],
)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))


@router.get("/api/rooms")
def list_rooms_api(request: Request, db: Session = Depends(get_db)):
    user = require_login_api(request)
    return {"items": list_chatrooms(db, user["user_id"])}


@router.post("/api/rooms")
def create_room_api(request: Request, db: Session = Depends(get_db)):
    user = require_login_api(request)
    chatroom = create_chatroom(db, user["user_id"])
    return {"chatroom_id": chatroom.chatroom_id, "chatroom_name": chatroom.chatroom_name}


@router.get("/api/rooms/{chatroom_id}/messages")
def get_messages_api(request: Request, chatroom_id: str, db: Session = Depends(get_db)):
    user = require_login_api(request)

    try:
        items = get_messages(db, chatroom_id, user["user_id"])
    except ChatServiceError as e:
        return JSONResponse(status_code=e.status_code, content={"detail": e.message})

    return {"items": items}


@router.post("/api/rooms/{chatroom_id}/messages")
def send_message_api(
    request: Request,
    chatroom_id: str,
    message: str = Form(...),
    db: Session = Depends(get_db),
):
    user = require_login_api(request)

    try:
        reply = send_message(db, chatroom_id, user["user_id"], message)
    except ChatServiceError as e:
        return JSONResponse(status_code=e.status_code, content={"detail": e.message})

    # reply = {"answer": str, "sources": list[dict], "rag_degraded": bool}
    # sources/rag_degraded는 DB에 저장하지 않고 화면 표시(근거 문서 영역, 저하 안내)에만 쓴다.
    return {
        "message": reply["answer"],
        "sources": reply["sources"],
        "rag_degraded": reply["rag_degraded"],
    }


@router.delete("/api/rooms/{chatroom_id}")
def delete_room_api(request: Request, chatroom_id: str, db: Session = Depends(get_db)):
    user = require_login_api(request)

    try:
        delete_chatroom(db, chatroom_id, user["user_id"])
    except ChatServiceError as e:
        return JSONResponse(status_code=e.status_code, content={"detail": e.message})

    return {"detail": "삭제되었습니다."}


@router.get("/{chatroom_id}", response_class=HTMLResponse)
def chat_page(request: Request, chatroom_id: str, db: Session = Depends(get_db)):
    user, redirect = require_login(request)
    if redirect:
        return redirect

    try:
        chatroom = get_owned_chatroom(db, chatroom_id, user["user_id"])
    except ChatServiceError:
        return RedirectResponse(url="/main", status_code=303)

    return templates.TemplateResponse(
        request,
        "chat.html",
        {
            "user": user,
            "active": "chat_list",
            "chatroom_id": chatroom.chatroom_id,
            "chatroom_name": chatroom.chatroom_name,
        },
    )
