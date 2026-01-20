from sqlalchemy.orm import Session
from logger import Logger
from pydantic import BaseModel
from sqlalchemy import text, Column, String
from database import Base

logger = Logger().get_logger(__name__)

class npti_type_response(BaseModel):
    npti_type: str
    npti_group: str
    npti_kor: str

class NptiTypeTable(Base):
    __tablename__ = "npti_type"

    NPTI_type = Column(String, primary_key=True)
    npti_kor = Column(String)

def get_all_npti_type(db: Session):
    logger.info("npti_type 전체 조회")

    sql = text("""
            select
                npti_type,
                npti_group,
                npti_kor
            from npti_type
            order by npti_group, npti_type
        """)
    return db.execute(sql).mappings().all()

def get_npti_type_by_group(db: Session, group: str):
    logger.info(f"npti_type 그룹 조회: {group}")

    sql = text("""
            select
                npti_type,
                npti_group,
                npti_kor
            from npti_type
            where npti_group = :group
            order by npti_type
        """)
    return db.execute(sql, {"group": group}).mappings().all()

def get_npti_questions_placeholder():
    return []
