import sys, os
sys.path.append(os.path.dirname(os.path.abspath(os.path.dirname(__file__))))

import joblib
from datetime import datetime, timezone, timedelta
from logger import Logger
from elasticsearch import Elasticsearch, helpers

from database import Base, get_engine, SessionLocal
import warnings
from sqlalchemy.exc import IntegrityError
from db_index.db_articles_NPTI import ArticlesNPTI

logger = Logger().get_logger(__name__)

# 엘라스틱
ES_HOST = "http://localhost:9200"
ES_USER = "elastic"
ES_PASS = "elastic"
ES_INDEX = "news_raw"

es = Elasticsearch( # elasticsearch 연결 객체 생성
    ES_HOST,
    basic_auth=(ES_USER, ES_PASS),
    verify_certs=False,
    ssl_show_warn=False # type: ignore
)

warnings.filterwarnings(
    "ignore",
    message="X does not have valid feature names"
)

# 테이블 생성 함수
def add_db():
    engine = get_engine()
    Base.metadata.create_all(bind=engine, tables=[ArticlesNPTI.__table__])

# 에러 메세지 ES저장 함수
def err_article(news_id, error_message):
    doc = {
        "news_id": news_id,
        "error_message": str(error_message),
        "error_timestamp": datetime.now(timezone(timedelta(hours=9))).isoformat()
    }
    try:
        es.index(index="err_article", document=doc)
        logger.info(f"[news_NPTI.py] 에러 정보 ES 저장 완료: {news_id}")
    except Exception as e:
        logger.error(f"[news_NPTI.py] ES 에러 로그 저장 중 추가 오류 발생: {e}")

# joblib 로드
base_dir = os.path.dirname(os.path.abspath(__file__))
model_dir = os.path.join(base_dir, "saved_models")
_models = None
def load_joblib():
    global _models
    if _models is None:
        logger.info("joblib 모델 및 벡터 로드 시작")
        _models = {
            "ct": (
                joblib.load(os.path.join(model_dir, "model_ct.joblib")),
                joblib.load(os.path.join(model_dir, "tfidf_ct.joblib")),
            ),
            "fi": (
                joblib.load(os.path.join(model_dir, "model_fi.joblib")),
                joblib.load(os.path.join(model_dir, "tfidf_fi.joblib")),
            ),
            "pn": (
                joblib.load(os.path.join(model_dir, "model_pn.joblib")),
                joblib.load(os.path.join(model_dir, "tfidf_pn.joblib")),
            ),
        }
        logger.info("joblib 모델 및 벡터 로드 완료")
    return _models


def init_npti():
    logger.info("[NPTI INIT] DB 테이블 및 모델 초기화 시작")
    add_db()
    load_joblib()
    logger.info("[NPTI INIT] 초기화 완료")


# NPTI 라벨링 함수(joblib 모델 활용)
def classify_npti_fast():
    db = SessionLocal()

    try:
        models = load_joblib()
        model_ct, tfidf_ct = models["ct"]
        model_fi, tfidf_fi = models["fi"]
        model_pn, tfidf_pn = models["pn"]

        now = datetime.now(timezone(timedelta(hours=9)))

        query = {
            "query": {"term": {"classified": False}},
            "_source": ["content"]
        }

        rows = helpers.scan(es, index=ES_INDEX, query=query)
        count = 0

        for row in rows:
            news_id = row["_id"]
            content = row["_source"].get("content")

            if not content:
                es.update(
                    index=ES_INDEX,
                    id=news_id,
                    body={"doc": {"classified": True, "classified_reason": "empty_content"}}
                )
                continue

            exists = (
                db.query(ArticlesNPTI)
                .filter(ArticlesNPTI.news_id == news_id)
                .first()
            )
            if exists:
                logger.info(f"[기사 분류 스킵] 이미 존재: {news_id}")
                continue

            try:
                length_type = "L" if len(content) >= 1000 else "S"
                ct = model_ct.predict(tfidf_ct.transform([content]))[0].upper()
                fi = model_fi.predict(tfidf_fi.transform([content]))[0].upper()
                pn = model_pn.predict(tfidf_pn.transform([content]))[0].upper()

                npti_code = length_type + ct + fi + pn

                record = ArticlesNPTI(
                    news_id=news_id,
                    length_type=length_type,
                    article_type=ct,
                    info_type=fi,
                    view_type=pn,
                    NPTI_code=npti_code,
                    updated_at=now
                )

                db.add(record)
                db.commit()
                count += 1

                es.update(
                    index=ES_INDEX,
                    id=news_id,
                    body={
                        "doc": {
                            "classified": True,
                            "npti": npti_code
                        }
                    }
                )

            except IntegrityError as e:
                db.rollback()
                logger.warning(f"[중복 기사] news_id={news_id}")
                es.update(
                    index=ES_INDEX,
                    id=news_id,
                    body={"doc": {"classified": True, "classified_reason": "duplicate"}}
                )
                continue

            except Exception as e:
                db.rollback()
                logger.error(f"[기사 분류 실패] news_id={news_id} / {e}")
                err_article(news_id, e)
                logger.info(f"기사 분류 실패 에러로그 저장 완료 - {news_id}")
                es.update(
                    index=ES_INDEX,
                    id=news_id,
                    body={
                        "doc": {
                            "classified": True,
                            "classified_reason": "error"
                        }
                    }
                )
                continue
        if count > 0:
            logger.info(f"NPTI 신규 기사 {count}건 분류 완료")

    except Exception as e:
        logger.error(f"[news_NPTI.py] 기사 NPTI 전체 프로세스(joblib) 에러: {e}")
        err_article(news_id if 'news_id' in locals() else "BATCH", e)
        logger.info(f"[news_NPTI.py] 에러 로그 저장 완료")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    print("NPTI 분류(joblib) 테스트 시작")
    classify_npti_fast()