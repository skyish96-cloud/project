from collections import defaultdict

from logger import Logger
from elasticsearch import Elasticsearch,helpers

logger = Logger().get_logger(__name__)

ES_HOST = "http://localhost:9200"
ES_USER = "elastic"
ES_PASS = "elastic"
ES_INDEX = "user_behavior"

es = Elasticsearch( # elasticsearch 연결 객체 생성
    ES_HOST,
    basic_auth=(ES_USER, ES_PASS),
    verify_certs=False,
    ssl_show_warn=False # type: ignore
)

def ensure_index():
    body = {
        "mappings": {
            "properties": {
                "user_id": {"type": "keyword"},
                "news_id": {"type": "keyword"},
                "MMF_X_inf": {"type": "float"},
                "MMF_Y_inf": {"type": "float"},
                "MSF_Y_inf": {"type": "float"},
                "mouseX": {"type": "float"},
                "mouseY": {"type": "float"},
                "timestamp": {"type": "integer"},
                "baseline" :{"type": "float"},
                "stored_time": {"type": "date", "format": "strict_date_optional_time||epoch_millis"},
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

def index_user_behavior(behavior_list:list): # raw_news 데이터를 indexing하는 함수
    if not behavior_list:
        return 0

    # Bulk Insert를 위한 데이터 구조 생성
    # _id를 지정하지 않으면 ES가 자동으로 UUID를 생성합니다. (로그 데이터는 자동 생성 권장)
    actions = [
        {
            "_index": ES_INDEX,
            "_source": doc
        }
        for doc in behavior_list
    ]

    try:
        success_count, errors = helpers.bulk(es, actions)
        if errors:
            logger.error(f"ES Bulk Insert 일부 에러 발생: {errors}")
        logger.info(f"ES 데이터 적재 성공: {success_count}건")
        return success_count
    except Exception as e:
        logger.error(f"ES Indexing 실패: {e}")
        return 0

def search_user_behavior(user_id: str, start_timestamp):
    body = {
        "query": {
            "bool": {
                "filter": [
                    # 1. user_id 일치 (keyword 타입이므로 term 사용)
                    {"term": {"user_id": user_id}},

                    # 2. timestamp가 start_timestamp 이상 (gte)
                    {"range": {"stored_time": {"gte": start_timestamp}}}
                ]
            }
        },
        # 3. 시간 순서대로 정렬 (오름차순)
        "sort": [
            {"stored_time": {"order": "asc"}},
            {"news_id": {"order": "asc"}},
            {"timestamp":{"order":"asc"}}
        ],
        "size": 10000
    }
    try:
        response = es.search(index="user_behavior", body=body)

        # 검색된 문서들의 _source만 리스트로 반환
        hits = response['hits']['hits']
        logs = [hit['_source'] for hit in hits]

        grouped_dict = defaultdict(list) #
        for log in logs:
            n_id = log.get('news_id')
            if n_id:
                grouped_dict[n_id].append(log)
        grouped_logs = list(grouped_dict.values())
        print(f'[검색 완료] User: {user_id} | Total logs: {len(logs)} | Groups: {len(grouped_logs)}')
        return grouped_logs


    except Exception as e:
        print(f"[검색 실패] {e}")
        return []

if __name__ == "__main__": # 이 파일에서 직접 실행할 때만 아래 내용이 실행되도록 하는 조건문
    if es.ping(): # elasticsearch에 요청을 보냈을 때 응답이 오는지 확인하는 함수(es 연결 확인 -> True/False)
        logger.info(f"ES 연결 성공")
    else:
        logger.info(f"ES 연결 실패")
    ensure_index()
    try:
        # es.indices.delete(index=ES_INDEX)
        # logger.info(f'{ES_INDEX} 삭제 완료')
        cnt = es.count(index=ES_INDEX)["count"] # raw_news 데이터 수를 cnt 변수에 저장
        logger.info(f"문서 수 : {cnt}")
        logs = search_user_behavior(user_id="admin")
        print(logs)
    except Exception as e:
        logger.info(f"문서 수 조회 오류 : {e}") # error 시 error log 출력