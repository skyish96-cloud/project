from sqlalchemy.orm import Session
from logger import Logger
from pydantic import BaseModel
from sqlalchemy import text, Column, String
from database import Base

logger = Logger().get_logger(__name__)

class npti_code_response(BaseModel):
    npti_code: str
    length_type: str
    article_type: str
    information_type: str
    view_type: str
    type_nick: str | None
    type_de: str | None

class NptiCodeTable(Base):
    __tablename__ = "npti_code"

    npti_code = Column(String, primary_key=True)
    type_nick = Column(String)
    length_type = Column(String)
    article_type = Column(String)
    information_type = Column(String)
    view_type = Column(String)

def get_all_npti_codes(db: Session):
    logger.info("npti_code 전체 조회")

    sql = text("""
        select
            npti_code,
            length_type,
            article_type,
            info_type AS information_type,
            view_type,
            type_nick,
            type_de
        from npti_code
        order by npti_code
    """)
    return db.execute(sql).mappings().all()


def get_npti_code_by_code(db: Session, code: str):
    logger.info(f"npti_code 단일 조회: {code}")

    sql = text("""
        select
            npti_code,
            length_type,
            article_type,
            info_type AS information_type,
            view_type,
            type_nick,
            type_de
        from npti_code
        where npti_code = :code
    """)
    return db.execute(sql, {"code": code}).mappings().first()
