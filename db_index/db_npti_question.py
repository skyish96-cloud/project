from sqlalchemy.orm import Session
from logger import Logger
from pydantic import BaseModel
from datetime import datetime

logger = Logger().get_logger(__name__)


class npti_question_response(BaseModel):
    question_id: str
    question_text: str
    npti_axis: str
    target_type: int
    question_ratio: float
    score_rate: float
    created_at: datetime


def get_all_npti_questions(db: Session):
    sql = """
        select
            question_id,
            question_text,
            npti_axis,
            target_type,
            question_ratio,
            score_rate,
            created_at
        from npti_question
        order by question_id
    """
    return db.execute(sql).mappings().all()


def get_npti_questions_by_axis(db: Session, axis: str):
    sql = """
        select
            question_id,
            question_text,
            npti_axis,
            target_type,
            question_ratio,
            score_rate,
            created_at
        from npti_question
        where npti_axis = :axis
        order by question_id
    """
    return db.execute(sql, {"axis": axis}).mappings().all()
