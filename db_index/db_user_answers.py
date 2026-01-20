from typing import List
from sqlalchemy.orm import Session
from sqlalchemy import text
from logger import Logger
from pydantic import BaseModel
from datetime import datetime

logger = Logger().get_logger(__name__)

# =========================
# Response Model
# =========================
class UserAnswerResponse(BaseModel):
    user_id: str
    question_no: int
    answer_value: int
    updated_at: datetime  # 다른 테이블과 명칭 통일


# =========================
# 조회 (특정 유저의 가장 최근 진단 답변 12개 가져오기)
# =========================
def get_latest_user_answers(db: Session, user_id: str):
    logger.info(f"최근 user_answer 조회: {user_id}")

    # 가장 최근의 updated_at을 가진 답변 12개를 가져오는 쿼리
    sql = text("""
        SELECT user_id, question_no, answer_value, updated_at
        FROM user_answer
        WHERE user_id = :user_id 
          AND updated_at = (
              SELECT MAX(updated_at) 
              FROM user_answer 
              WHERE user_id = :user_id
          )
        ORDER BY question_no ASC
    """)

    return db.execute(sql, {"user_id": user_id}).mappings().all()


# =========================
# 저장 (진단 완료 시마다 새로운 이력 생성)
# =========================
def insert_user_answers(db: Session, user_id: str, answers: List[dict]):
    """
    answers = [{"question_no": 1, "answer_value": 3}, ...]
    """
    logger.info(f"새로운 user_answer 이력 저장: {user_id}")

    # 동일 회차의 12개 질문이 정확히 같은 시간을 갖도록 설정
    now = datetime.now()

    sql = text("""
        INSERT INTO user_answer (
            user_id,
            question_no,
            answer_value,
            updated_at
        )
        VALUES (
            :user_id,
            :question_no,
            :answer_value,
            :updated_at
        )
    """)

    params = [
        {
            "user_id": user_id,
            "question_no": ans['question_no'],
            "answer_value": ans['answer_value'],
            "updated_at": now
        } for ans in answers
    ]

    try:
        db.execute(sql, params)
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"user_answer 저장 중 오류 발생: {e}")
        raise e