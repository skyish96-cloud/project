from logger import Logger
from elasticsearch import Elasticsearch
from kiwipiepy import Kiwi

logger = Logger().get_logger(__name__)

ES_HOST = "http://localhost:9200"
ES_USER = "elastic"
ES_PASS = "elastic"
ES_INDEX = "news_aggr"

es = Elasticsearch( # elasticsearch 연결 객체 생성
    ES_HOST,
    basic_auth=(ES_USER, ES_PASS),
    verify_certs=False,
    ssl_show_warn=False # type: ignore
)

kiwi = Kiwi()

def ensure_news_aggr():
    body = {
        "mappings": {
            "properties": {
                "news_id": { "type": "keyword" },
                "tokens": {
                    "type": "nested",
                    "properties": {
                    "term": { "type": "keyword" },
                    "score": { "type": "float" }
                    }
                },
                "tag": {"type" :"keyword"},
                "timestamp": { "type": "date" },
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


def tokens_aggr(combined_text: str, kiwi: Kiwi):
    if not combined_text or not combined_text.strip():
        return ""

    # 1. Kiwi 토큰화
    tokens = kiwi.tokenize(combined_text)

    # 2. 제거할 품사 태그 정의 (튜플 형태)
    # J: 조사, E: 어미, S: 부호 및 숫자(SN 포함),
    # NNB: 의존명사, XP: 접두사, XS: 접미사
    exclude_tags = ('J', 'E', 'S', 'NNB', 'XP', 'XS')

    # 3. 필터링 및 정제
    # - 불용어 품사 제외
    # - 단어 길이가 2글자 이상인 것만 유지 (주제 분류 정확도 향상)
    filtered_tokens = [
        token.form for token in tokens
        if not token.tag.startswith(exclude_tags)
           # and len(token.form) > 1
    ]

    # 4. 공백으로 구분된 문자열로 결합
    tokens_list = " ".join(filtered_tokens)

    return tokens_list



if __name__ == "__main__": # 이 파일에서 직접 실행할 때만 아래 내용이 실행되도록 하는 조건문
    if es.ping(): # elasticsearch에 요청을 보냈을 때 응답이 오는지 확인하는 함수(es 연결 확인 -> True/False)
        logger.info(f"ES 연결 성공")
    else:
        logger.info(f"ES 연결 실패")
    ensure_news_aggr() # sample_index 생성 확인 (없으면 생성)
    try:
        # es.indices.delete(index=ES_INDEX)
        # logger.info(f'{ES_INDEX} 삭제 완료')
        cnt = es.count(index=ES_INDEX)["count"] # raw_news 데이터 수를 cnt 변수에 저장
        logger.info(f"문서 수 : {cnt}")
    except Exception as e:
        logger.info(f"문서 수 조회 오류 : {e}") # error 시 error log 출력