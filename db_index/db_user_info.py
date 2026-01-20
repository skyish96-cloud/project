from sqlalchemy.orm import Session
from sqlalchemy import text, Column, String, Integer, SmallInteger
import hashlib
from pydantic import BaseModel, EmailStr
from datetime import date
from logger import Logger
from database import Base

logger = Logger().get_logger(__name__)

# =========================
# Pydantic Model
# =========================
class UserInfo(Base):
    __tablename__ = "user_info"
    user_id = Column(String(50), primary_key=True)
    user_pw = Column(String(255))
    user_name = Column(String(50))
    user_birth = Column(String(20))
    user_age = Column(Integer)
    user_gender = Column(SmallInteger) # 0: 남자, 1: 여자
    user_email = Column(String(100))
    activation = Column(SmallInteger, default=1)

class UserCreateRequest(BaseModel):
    user_id: str
    user_pw: str
    user_name: str
    user_birth: date
    user_age: int
    user_gender: bool
    user_email: EmailStr
    activation: bool = True

class UserUpdate(BaseModel):
    user_id: str
    user_name: str
    current_password: str  # 사용자가 입력한 현재 비번
    new_password: str      # 새롭게 바꿀 비번
    user_birth: str
    user_age: int
    user_gender: str
    user_email: EmailStr
    activation: bool = True


# =========================
# Password Helpers
# =========================
def hash_password(raw_pw: str) -> str:
    """비밀번호 해시 (회원가입 / 로그인 공용)"""
    return hashlib.sha256(raw_pw.encode()).hexdigest()


def verify_password(raw_pw: str, hashed_pw: str) -> bool:
    """입력 비밀번호와 DB 비밀번호 비교"""
    return hash_password(raw_pw) == hashed_pw


# =========================
# Signup Logic
# =========================
def insert_user(db: Session, params: dict):
    logger.info(f"[SIGNUP] try user_id={params.get('user_id')}")

    params["user_pw"] = hash_password(params["user_pw"])

    sql = text("""
        INSERT INTO user_info (
            user_id, user_pw, user_name, user_birth,
            user_age, user_gender, user_email, activation
        )
        VALUES (
            :user_id, :user_pw, :user_name, :user_birth,
            :user_age, :user_gender, :user_email, :activation
        )
    """)
    db.execute(sql, params)

    logger.info(f"[SIGNUP SUCCESS] user_id={params.get('user_id')}")


# =========================
# Login Logic
# =========================
def authenticate_user(db: Session, user_id: str, user_pw: str) -> bool:
    logger.info(f"[LOGIN] attempt user_id={user_id}")

    sql = text("""
        SELECT user_pw, activation
        FROM user_info
        WHERE user_id = :user_id
    """)
    user = db.execute(sql, {"user_id": user_id}).fetchone()

    if not user:
        logger.warning(f"[LOGIN FAIL] user not found: {user_id}")
        return False

    if not user.activation:
        logger.warning(f"[LOGIN FAIL] deactivated user: {user_id}")
        return False

    if not verify_password(user_pw, user.user_pw):
        logger.warning(f"[LOGIN FAIL] password mismatch: {user_id}")
        return False

    logger.info(f"[LOGIN SUCCESS] user_id={user_id}")
    return True


# =========================
# User Info Fetch Logic (Basic)
# =========================
def get_user_by_id(db: Session, user_id: str):
    """
    [내부용] ID로 DB의 원본 데이터를 조회합니다.
    """
    logger.info(f"[PROFILE] fetch raw data for user_id={user_id}")

    sql = text("""
        SELECT user_id, user_name, user_email, user_birth, user_age, user_gender
        FROM user_info
        WHERE user_id = :user_id
    """)

    result = db.execute(sql, {"user_id": user_id}).fetchone()
    return result


# =========================================================
# [NEW] Service Logic for MyPage (Controller Support)
# =========================================================
def get_my_page_data(db: Session, user_id: str):
    """
    [Main.py용] DB 데이터를 조회한 뒤, 프론트엔드가 바로 쓸 수 있게
    성별(Boolean -> String) 및 날짜(Date -> String) 변환을 수행하여 반환합니다.
    """

    # 1. 위의 기본 조회 함수 재사용
    user = get_user_by_id(db, user_id)

    # 2. 데이터가 없으면 None 반환
    if not user:
        return None

    # 3. 데이터 가공 (Logic 처리)
    # DB에는 True(1) 또는 False(0)로 저장되어 있으므로 문자열로 변환
    gender_str = "여자" if user.user_gender else "남자"

    # 날짜 객체(date)를 문자열(YYYY-MM-DD)로 변환
    birth_str = str(user.user_birth)

    # 4. JSON으로 내보내기 좋은 딕셔너리(dict) 형태로 포장
    return {
        "userId": user.user_id,
        "name": user.user_name,
        "email": user.user_email,
        "birth": birth_str,
        "age": user.user_age,
        "gender": gender_str
    }

def deactivate_user(db: Session, user_id: str):
    """
    유저 탈퇴 처리: activation 컬럼을 0(비활성)으로 변경
    """
    sql = text("UPDATE user_info SET activation = 0 WHERE user_id = :user_id")
    db.execute(sql, {"user_id": user_id})
    db.commit()

def get_user_info(db: Session, user_id: str):
    return db.query(UserInfo).filter(UserInfo.user_id == user_id).first()