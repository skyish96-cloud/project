from logger import Logger
from elasticsearch import Elasticsearch
from datetime import datetime, timezone

logger = Logger().get_logger(__name__)

ES_HOST = "http://localhost:9200"
ES_USER = "elastic"
ES_PASS = "elastic"
ES_INDEX = "err_crawling"

es = Elasticsearch( # elasticsearch 연결 객체 생성
    ES_HOST,
    basic_auth=(ES_USER, ES_PASS),
    verify_certs=False,
    ssl_show_warn=False # type: ignore
)


def index_error_log(error_message: str, error_site: str):
    """
    발생한 에러를 err_bigkinds 인덱스에 저장합니다.
    """
    try:
        # ISO 8601 형식의 현재 시간 생성
        timestamp = datetime.now(timezone.utc).isoformat(timespec='seconds')

        doc = {
            "error_timestamp": timestamp,
            "error_message": error_message,
            "error_site": error_site
        }

        res = es.index(index=ES_INDEX, document=doc)
        logger.info(f"에러 로그 저장 완료: {res['result']}")
    except Exception as e:
        logger.error(f"에러 로그 저장 실패: {e}")


def ensure_news_aggr():
    body = {
        "mappings": {
            "properties": {
                "error_timestamp": {
                    "type": "date",
                    "format": "strict_date_optional_time||epoch_millis"
                },
                "error_message": {
                    "type": "text",
                    "fields": {"keyword": { "type": "keyword" }}
                },
                "error_site": { "type": "keyword" }
            }
        }
    }

    if es.indices.exists(index=ES_INDEX):
        logger.info(f"이미 존재하는 index : {ES_INDEX}")
        cnt = es.count(index=ES_INDEX)["count"]  # raw_news 데이터 수를 cnt 변수에 저장
        logger.info(f"문서 수 : {cnt}")
        return None

    try:
        res = es.indices.create(index=ES_INDEX, body=body)
        if res.get("acknowledged"):
            logger.info(f"index 생성 완료 : {ES_INDEX}")
        else:
            logger.error(f"index 생성 실패 : {res}")
    except Exception as e:
        logger.error(f"index 생성 오류 : {e}")

def search_err():
    body = {
        "query": {
            "match_all": {}
        }
    }
    try:
        res = es.search(index=ES_INDEX, body=body)
        hits = res["hits"]["hits"]
        for hit in hits:
            error_site = hit["_source"]["error_site"]
            error_timestamp = hit["_source"]["error_timestamp"]
            error_message = hit["_source"]["error_message"]
            logger.info(f'error_site: {error_site}\nerror_timestamp: {error_timestamp}\nerror_message: {error_message}')

    except Exception as e:
        res = None
        logger.info(e)
    finally:
        return res

if __name__ == "__main__": # 이 파일에서 직접 실행할 때만 아래 내용이 실행되도록 하는 조건문
    if es.ping(): # elasticsearch에 요청을 보냈을 때 응답이 오는지 확인하는 함수(es 연결 확인 -> True/False)
        logger.info(f"ES 연결 성공")
    else:
        logger.info(f"ES 연결 실패")
    ensure_news_aggr() # sample_index 생성 확인 (없으면 생성)
    search_err()
    try:
        # es.indices.delete(index=ES_INDEX)
        # logger.info(f'{ES_INDEX} 삭제 완료')
        cnt = es.count(index=ES_INDEX)["count"] # raw_news 데이터 수를 cnt 변수에 저장
        logger.info(f"문서 수 : {cnt}")
    except Exception as e:
        logger.info(f"문서 수 조회 오류 : {e}") # error 시 error log 출력