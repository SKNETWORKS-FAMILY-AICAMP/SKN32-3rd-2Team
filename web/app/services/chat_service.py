import uuid
from datetime import datetime

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from ..models import Chat, Chatroom
from .llm_client import classify_topic, generate_reply


class ChatServiceError(Exception):
    """대화방/메시지 처리 중 발생하는 오류. 라우터에서 status_code로 매핑해서 응답한다."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def create_chatroom(db: Session, user_id: str) -> Chatroom:
    chatroom = Chatroom(chatroom_id=str(uuid.uuid4()), user_id=user_id)
    db.add(chatroom)
    db.commit()
    db.refresh(chatroom)
    return chatroom


def list_chatrooms(db: Session, user_id: str) -> list[dict]:
    stmt = (
        select(Chatroom)
        .where(Chatroom.user_id == user_id, Chatroom.is_deleted == False)  # noqa: E712
        .order_by(desc(Chatroom.created_at))
    )
    rooms = db.scalars(stmt).all()

    return [
        {
            "chatroom_id": room.chatroom_id,
            "chatroom_name": room.chatroom_name,
            "created_at": room.created_at.strftime("%Y-%m-%d %H:%M") if room.created_at else "",
        }
        for room in rooms
    ]


def get_owned_chatroom(db: Session, chatroom_id: str, user_id: str) -> Chatroom:
    """대화방을 조회하고, 존재/소유자 여부를 함께 검증한다. 타 유저의 대화방 접근을 차단한다."""

    chatroom = db.get(Chatroom, chatroom_id)
    if chatroom is None or chatroom.is_deleted or chatroom.user_id != user_id:
        raise ChatServiceError("대화방을 찾을 수 없습니다.", status_code=404)
    return chatroom


def get_messages(db: Session, chatroom_id: str, user_id: str) -> list[dict]:
    get_owned_chatroom(db, chatroom_id, user_id)

    stmt = select(Chat).where(Chat.chatroom_id == chatroom_id).order_by(Chat.chat_id)
    chats = db.scalars(stmt).all()

    return [
        {
            "speaker": chat.speaker,
            "message": chat.message,
            "created_at": chat.created_at.strftime("%Y-%m-%d %H:%M") if chat.created_at else "",
        }
        for chat in chats
    ]


def send_message(db: Session, chatroom_id: str, user_id: str, message: str) -> str:
    """사용자 메시지를 저장하고, LLM 응답을 생성해 저장한 뒤 응답 텍스트를 반환한다."""

    chatroom = get_owned_chatroom(db, chatroom_id, user_id)

    message = message.strip()
    if not message:
        raise ChatServiceError("메시지를 입력해주세요.")

    topic = classify_topic(message)
    db.add(Chat(chatroom_id=chatroom_id, speaker="user", message=message, topic=topic))

    if chatroom.chatroom_name == "새 대화":
        chatroom.chatroom_name = message[:30]

    reply = generate_reply(message)
    db.add(Chat(chatroom_id=chatroom_id, speaker="llm", message=reply))

    db.commit()
    return reply


def delete_chatroom(db: Session, chatroom_id: str, user_id: str) -> None:
    chatroom = get_owned_chatroom(db, chatroom_id, user_id)
    chatroom.is_deleted = True
    chatroom.deleted_at = datetime.now()
    db.commit()
