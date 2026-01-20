from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, Session
from logger import Logger
from sqlalchemy.ext.declarative import declarative_base

logger = Logger().get_logger(__name__)

DB_USER = "web_user"
DB_PASSWORD = "pass"
DB_NAME = "mynpti"
DB_HOST = "localhost"
DB_PORT = 3306
DATABASE_URL = (f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}")

# ORM 모델 작성을 위한 기본 클래스
Base = declarative_base()

_engine = None
_SessionLocal = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        logger.info("DB Engine 생성")
        _engine = create_engine(
            DATABASE_URL,
            pool_pre_ping=True,
            pool_recycle=3600,
        )
    return _engine


SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=get_engine(),
)

def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    except Exception as e:
        logger.error(f"DB 연결 실패 : {e}")
        raise
    finally:
        db.close()