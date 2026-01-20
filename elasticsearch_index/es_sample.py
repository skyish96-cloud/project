# <elasticsearch의 raw_news 생성 & index에 데이터를 추가, 삭제하는 함수 정의>
from logger import Logger
from elasticsearch import Elasticsearch
from kiwipiepy import Kiwi

kiwi = Kiwi()

logger = Logger().get_logger(__name__)

ES_HOST = "http://localhost:9200"
ES_USER = "elastic"
ES_PASS = "elastic"
ES_INDEX = "sample_index"

es = Elasticsearch( # elasticsearch 연결 객체 생성
    ES_HOST,
    basic_auth=(ES_USER, ES_PASS),
    verify_certs=False,
    ssl_show_warn=False # type: ignore
)


def ensure_index():
    body = {
        "settings": {
            "analysis": {
                "analyzer": {
                    "korean_whitespace": {
                        "type": "custom",
                        "tokenizer": "whitespace",
                        "filter": ["trim"]
                    }
                }
            }
        },
        "mappings": {
            "properties": {  # raw_news field(항목)과 각 항목의 데이터 타입 설정
                "news_id": {"type": "keyword"},
                "title": {"type": "text", "analyzer": "korean_whitespace"},
                "media": {"type": "text"},
                "category": {"type": "text"},
                "content": {"type": "text", "fields": {"keyword": {"type": "keyword"}},
                            "analyzer": "korean_whitespace"},
                "timestamp": {"type": "date", "format": "strict_date_optional_time||epoch_millis"},
                "title_tokens": {
                    "type": "text", "analyzer": "korean_whitespace"
                },
                "content_tokens": {
                    "type": "text", "analyzer": "korean_whitespace"
                }
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


def tokens(row:dict, kiwi: Kiwi):
    def analyze_token(text:str):
        text = row.get(text,"")
        if not text.strip():
            return []

        tokens = kiwi.tokenize(text)
        tokens_list = " ".join([token.form for token in tokens])
        return tokens_list

    return {"title_tokens": analyze_token('title'),
        "content_tokens": analyze_token('content')}

def index_sample_row(row:dict): # raw_news 데이터를 indexing하는 함수
    es.index(index=ES_INDEX, id=row["news_id"], document=row, refresh="wait_for")

# def delete_news_from_index(id_:str): # raw_news id에 해당하는 데이터를 삭제하는 함수
#     es.delete(index=ES_INDEX,id=id_, ignore=[404], refresh="wait_for")

def search_news_row(id_:str):
    try:
        result = es.exists(index=ES_INDEX, id=id_)  # ✅ exists() 사용 (더 빠름)
        logger.info(f"ES 중복 확인 - {id_} : {'기존' if result else '신규'}")
        return result
    except Exception as e:
        logger.error(f"ES 중복 확인 실패 {id_}: {e}")
        return False

if __name__ == "__main__": # 이 파일에서 직접 실행할 때만 아래 내용이 실행되도록 하는 조건문
    if es.ping(): # elasticsearch에 요청을 보냈을 때 응답이 오는지 확인하는 함수(es 연결 확인 -> True/False)
        logger.info("ES 연결 성공")
    else:
        logger.info("ES 연결 실패")
    ensure_index() # sample_index 생성 확인 (없으면 생성)
    try:
        # es.indices.delete(index=ES_INDEX)
        # logger.info(f'{ES_INDEX} 삭제 완료')
        cnt = es.count(index=ES_INDEX)["count"] # raw_news 데이터 수를 cnt 변수에 저장
        logger.info(f"문서 수 : {cnt}")
    except Exception as e:
        logger.info(f"문서 수 조회 오류 : {e}") # error 시 error log 출력