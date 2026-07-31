from sqlalchemy import Boolean, Column, DateTime, String
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
    created_at = Column(DateTime, nullable=False, server_default=func.now())
