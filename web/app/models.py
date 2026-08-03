from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.sql import func

from .database import Base


class User(Base):
    __tablename__ = "user"

    user_id = Column(String(20), primary_key=True)
    passwd = Column(String(255), nullable=False)
    name = Column(String(50), nullable=False)
    department = Column(String(100), nullable=False)
    is_admin = Column(Boolean, nullable=False, default=False)
    is_disabled = Column(Boolean, nullable=False, default=False)
    is_deleted = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime, nullable=True)


class UserLoginHistory(Base):
    __tablename__ = "user_login_history"

    history_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(20), ForeignKey("user.user_id"), nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())


class Chatroom(Base):
    __tablename__ = "chatroom"

    chatroom_id = Column(String(36), primary_key=True)
    user_id = Column(String(20), ForeignKey("user.user_id"), nullable=False)
    chatroom_name = Column(String(100), nullable=False, default="새 대화")
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    is_deleted = Column(Boolean, nullable=False, default=False)
    deleted_at = Column(DateTime, nullable=True)


class Chat(Base):
    __tablename__ = "chat"

    chat_id = Column(Integer, primary_key=True, autoincrement=True)
    chatroom_id = Column(String(36), ForeignKey("chatroom.chatroom_id"), nullable=False)
    speaker = Column(Enum("user", "llm", name="speaker_enum"), nullable=False)
    message = Column(Text, nullable=False)
    topic = Column(String(100), nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())


class ChatSource(Base):
    """채팅 답변(LLM 응답) 하단에 표시되는 근거 문서 목록이다.
    채팅 1건(LLM 응답)에 대해 근거 문서를 N건까지 저장할 수 있다.

    doc_id는 document.doc_id를 참조하는 값이지만,
    외부 Chat API에서 전달받은 값을 그대로 저장하는 구조이므로 강한 Foreign Key(FK)는 설정하지 않는다.
    이는 두 시스템 간 문서 ID 동기화가 일시적으로 불일치하더라도 채팅 데이터 저장이 실패하지 않도록 하기 위함이다.

    file_name과 page는 응답 생성 시점의 스냅샷 정보를 저장한다.
    따라서 이후 원본 문서가 변경되거나 삭제되더라도, 당시 사용자에게 제공된 근거 문서 정보는 그대로 유지된다."""

    __tablename__ = "chat_source"

    source_id = Column(Integer, primary_key=True, autoincrement=True)
    chat_id = Column(Integer, ForeignKey("chat.chat_id"), nullable=False)
    doc_id = Column(Integer, nullable=True)
    file_name = Column(String(255), nullable=False)
    page = Column(Integer, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())