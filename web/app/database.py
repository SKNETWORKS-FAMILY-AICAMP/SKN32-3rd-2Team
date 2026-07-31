import os
from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# 운영 환경에서는 MySQL 8.0 연결 문자열을 환경변수로 주입한다.
DATABASE_URL = os.getenv("DATABASE_URL")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
