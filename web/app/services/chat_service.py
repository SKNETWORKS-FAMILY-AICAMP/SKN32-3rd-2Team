import logging
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from ..models import Chat, Chatroom
from .llm_client import ChatAPIError, generate_chatroom_name, get_chat_completion

# 명세: "이전 대화 3건" - 질문-응답을 한 쌍으로 보고, 최근 3쌍(=최대 6개 메시지)을 전달한다.
HISTORY_PAIRS = 3

# ---------------------------------------------------------------------------
# 타이밍 로그용 로거. llm_client.py에서 핸들러/레벨을 설정해두므로 여기서는 그냥
# 같은 이름으로 가져다 쓰기만 하면 된다. (자세한 이유는 llm_client.py의 주석 참고:
# uvicorn의 log_level 옵션이나 main.py의 __main__ 블록 설정에 기대지 않기 위함)
# ---------------------------------------------------------------------------
logger = logging.getLogger("chat_timing")


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


def _recent_history(db: Session, chatroom_id: str, pairs: int = HISTORY_PAIRS) -> list[dict]:
    """이 채팅방의 가장 최근 질문-응답 N쌍을 시간순(오래된 것 -> 최신)으로 반환한다.
    지금 막 들어온 사용자 질문을 저장하기 '전'에 호출해야 한다."""

    stmt = (
        select(Chat)
        .where(Chat.chatroom_id == chatroom_id)
        .order_by(desc(Chat.chat_id))
        .limit(pairs * 2)
    )
    recent = db.scalars(stmt).all()

    return [{"speaker": chat.speaker, "message": chat.message} for chat in reversed(recent)]


def send_message(db: Session, chatroom_id: str, user_id: str, message: str) -> dict:
    """사용자 메시지를 저장하고, Chat API로 답변을 생성해 저장한 뒤 화면 표시용 데이터를 반환한다.

    반환: {"answer": str, "sources": list[dict], "rag_degraded": bool}
    """

    # 동시에 여러 요청이 들어와도 로그를 서로 구분할 수 있도록 요청별 짧은 id를 붙인다.
    req_id = uuid.uuid4().hex[:8]
    t0 = time.perf_counter()

    def _mark(label: str, t_prev: float) -> float:
        now = time.perf_counter()
        logger.info("[timing][%s] %-32s %8.1fms", req_id, label, (now - t_prev) * 1000)
        return now

    chatroom = get_owned_chatroom(db, chatroom_id, user_id)
    t = _mark("get_owned_chatroom(DB)", t0)

    message = message.strip()
    if not message:
        raise ChatServiceError("메시지를 입력해주세요.")

    history = _recent_history(db, chatroom_id)
    t = _mark("recent_history(DB)", t)

    is_first_message = chatroom.chatroom_name == "새 대화"

    # 답변 생성(/v1/chat)과 제목 생성(/v1/chatroom-name)은 서로 의존관계가 없으므로
    # 첫 메시지일 때는 두 요청을 동시에 던져서 순차 실행 시 더해지던 지연을 없앤다.
    with ThreadPoolExecutor(max_workers=2) as executor:
        t_llm_start = time.perf_counter()
        chat_future = executor.submit(get_chat_completion, chatroom_id, message, history)
        name_future = executor.submit(generate_chatroom_name, message) if is_first_message else None

        try:
            result = chat_future.result()
        except ChatAPIError as e:
            # chat_future.result()는 name_future와 무관하게 /v1/chat 하나만의 소요시간이다.
            # (첫 메시지라도 name_future는 별도 스레드에서 병렬로 돌고 있을 뿐, 이 대기시간에 영향 없음)
            _mark("get_chat_completion(/v1/chat, FAILED)", t_llm_start)
            # 에러가 나도 대화 이력은 온전히 남긴다: 사용자 질문(topic=에러) + llm 쪽엔 에러 안내 문구.
            # 재접속해서 대화방을 다시 열어도 "다시 시도해주세요" 문구가 그대로 보이게 된다.
            db.add(Chat(chatroom_id=chatroom_id, speaker="user", message=message, topic="에러"))
            db.add(Chat(chatroom_id=chatroom_id, speaker="llm", message=e.message))
            db.commit()
            raise ChatServiceError(e.message, status_code=e.status_code)

        # 여기 찍히는 시간이 "브라우저 네트워크 탭 5초"의 실제 원인을 가장 잘 보여준다.
        # 이 값이 크면 -> LLM/RAG 서버 쪽이 느린 것 (웹 코드 문제 아님)
        # 이 값이 작은데도 전체(TOTAL)가 크면 -> DB나 이 파이썬 코드 쪽을 더 봐야 함
        t = _mark("get_chat_completion(/v1/chat)", t_llm_start)

        if name_future is not None:
            t_name_start = time.perf_counter()
            try:
                chatroom.chatroom_name = name_future.result()
            except ChatAPIError:
                # 제목 생성 실패는 대화 자체를 막을 이유가 없으므로, 조용히 기존 방식으로 대체한다.
                chatroom.chatroom_name = message[:30]
            # 참고용: 이 값은 위 get_chat_completion과 "동시에" 진행된 시간이라
            # TOTAL에는 (둘 중 더 오래 걸린 시간만) 반영된다. 즉 이 값이 커도 전체 응답이
            # 그만큼 느려지는 건 아니다 (get_chat_completion보다 짧은 한도 내에서는).
            _mark("generate_chatroom_name(/v1/chatroom-name, 병렬)", t_name_start)

    db.add(Chat(chatroom_id=chatroom_id, speaker="user", message=message, topic=result["topic"]))
    db.add(Chat(chatroom_id=chatroom_id, speaker="llm", message=result["answer"]))

    db.commit()
    t = _mark("db_insert+commit", t)

    logger.info("[timing][%s] %-32s %8.1fms", req_id, "TOTAL", (time.perf_counter() - t0) * 1000)

    return {
        "answer": result["answer"],
        "sources": result["sources"],
        "rag_degraded": result["rag_degraded"],
    }


def delete_chatroom(db: Session, chatroom_id: str, user_id: str) -> None:
    chatroom = get_owned_chatroom(db, chatroom_id, user_id)
    chatroom.is_deleted = True
    chatroom.deleted_at = datetime.now()
    db.commit()
