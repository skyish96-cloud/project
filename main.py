from fastapi import FastAPI, Depends, Query, Request, Body, HTTPException
from fastapi.responses import FileResponse
from starlette.responses import JSONResponse, RedirectResponse, HTMLResponse
from starlette.staticfiles import StaticFiles
import pandas as pd
import asyncio
from algorithm.user_NPTI import model_predict_proba
from bigkinds_crawling.scheduler import sch_start, result_queue
from bigkinds_crawling.sample import sample_crawling, get_sample
from logger import Logger
from typing import Optional
from bigkinds_crawling.news_raw import news_crawling, get_news_raw, search_article
from bigkinds_crawling.news_aggr_grouping import news_aggr, related_news
from sqlalchemy.orm import Session
from database import get_db
from db_index.db_npti_type import get_all_npti_type, get_npti_type_by_group, npti_type_response, NptiTypeTable
from db_index.db_npti_code import get_all_npti_codes, get_npti_code_by_code, npti_code_response, NptiCodeTable
from db_index.db_npti_question import get_all_npti_questions, get_npti_questions_by_axis, npti_question_response
from db_index.db_user_info import UserCreateRequest, insert_user, authenticate_user, deactivate_user, get_my_page_data, \
    UserInfo, verify_password, UserUpdate, hash_password, get_user_info
from db_index.db_user_npti import get_user_npti_info, finalize_score
from sqlalchemy import text
from starlette.middleware.sessions import SessionMiddleware
from elasticsearch import Elasticsearch, ConnectionError as ESConnectionError
from datetime import timedelta, datetime, timezone
from db_index.db_user_answers import insert_user_answers
from db_index.db_user_npti import insert_user_npti
import json
from elasticsearch_index.es_user_behavior import index_user_behavior, search_user_behavior
from db_index.db_user_npti import UserNPTITable, UserNPTIResponse
from elasticsearch_index.es_raw import ES_INDEX, search_news_condition
from db_index.db_articles_NPTI import ArticlesNPTI
import math
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware


app = FastAPI()
logger = Logger().get_logger(__name__)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # 프론트엔드 주소 허용
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/view",StaticFiles(directory="view"), name="view")
app.add_middleware(
    SessionMiddleware,
    secret_key="npti-secret-key",
    # max_age=60 * 60 * 24, #1일
    max_age=int(timedelta(minutes=60).total_seconds()),
    same_site="lax"         # 기본 보안 옵션
)

@app.get("/")
def main():
    return FileResponse("view/html/main.html")


# 개별 기사 페이지 -----------------------------------------------------------------
@app.get("/article")
async def view_page():
    return FileResponse("view/html/view.html")

@app.get("/article/{news_id}")
async def get_article(news_id:str):
    news_info = search_article(news_id)
    related = related_news(news_info["title"], news_id, news_info["category"])
    news_info["related_news"] = related
    print(f"related : {related}")
    if news_info:
        return JSONResponse(content=news_info,  status_code=200)
    else:
        return JSONResponse(content=None, status_code=404)


# JS의 sendBeacon('/log/behavior') 경로와 일치시킴
@app.post("/log/behavior")
async def collect_behavior_log(request: Request):
    try:
        # 1. Body 데이터를 Dictionary로 변환 (await 필수)
        data = await request.json()

        # 2. 데이터 확인 (터미널 출력)
        # JS에서 보낸 payload 구조: { news_id, user_id, session_end_time, total_logs, logs }
        news_id = data.get("news_id")
        user_id = data.get("user_id")
        log_count = data.get("total_logs")
        raw_logs = data.get("logs", [])
        stored_time = datetime.now(timezone(timedelta(hours=9))).isoformat(timespec='seconds')

        processed_docs = []
        for log in raw_logs:
            # JS 변수명 -> ES 매핑 변수명 변환
            doc = {
                "user_id": user_id,
                "news_id": news_id,
                "MMF_X_inf": log.get("MMF_X", 0.0),  # JS: MMF_X -> ES: MMF_X_inf
                "MMF_Y_inf": log.get("MMF_Y", 0.0),  # JS: MMF_Y -> ES: MMF_Y_inf
                "MSF_Y_inf": log.get("MSF_Y", 0.0),  # JS: MSF_Y -> ES: MSF_Y_inf
                "mouseX": log.get("mouseX", 0.0),
                "mouseY": log.get("mouseY", 0.0),
                "timestamp": int(log.get("elapsedMs", 0)),
                "baseline": log.get("baseline", 0.0),
                "stored_time": stored_time
            }
            processed_docs.append(doc)

        # 4. [저장] ES 인덱싱
        if processed_docs:
            count = index_user_behavior(processed_docs)
            print(f"[Log] User:{user_id} | News:{news_id} | {count} 개 데이터 저장 완료")
            return {"status": "ok", "message": f"{count}개 로그 저장"}
        else:
            return {"status": "ok", "message": "저장할 로그 없음"}

    except Exception as e:
        print(f"[에러 발생] {e}")
        return {"status": "error", "message": str(e)}

# 기사 npti 분류 정답 데이터 수집 ----------------------------------------------------
@app.get("/sample")
def sample(max_pages: int = 90):
    logger.info(f"API 호출: 크롤링 시작 (최대 {max_pages} 페이지)")
    try:
        # 비즈니스 로직 호출
        result = sample_crawling(max_pages=max_pages)
        return {"status": "success","count": len(result),"data": result}
    except Exception as e:
        logger.error(f"API 실행 오류: {e}")
        return {"status": "error", "message": str(e)}


@app.get("/sample_csv")
def sample_csv(q: Optional[str] = None):
    logger.info(f"ES 데이터 요청 수신 (query: {q})")
    try:
        result = get_sample(q)
        if result is None:
            return {"status": "error", "message": "데이터를 가져올 수 없습니다."}
        return result
    except Exception as e:
        logger.error(f"API 실행 오류: {e}")
        return {"status": "error", "message": str(e)}


@app.get("/news_raw")
def news_raw(max_pages: int = 5):
    logger.info(f"크롤링 시작: 최대 {max_pages} 페이지")
    try:
        # sample.py의 crawling 함수 호출
        result = news_crawling(max_pages=max_pages)
        return {"status": "success","count": len(result),"data": result}
    except Exception as e:
        logger.error(f"API 실행 중 오류 발생: {e}")
        return {"status": "error", "message": str(e)}

sch = sch_start()
@app.get("/scheduler_start") # scheduler 수동 시작
async def scheduler_start():
    if not sch.running:
        sch.start()
        return {'msg': 'scheduler 실행 시작!'}
    else:
        return {'msg': '이미 실행 중입니다.'}

@app.get("/news_aggr")
def news_aggr_start():
    tfid = news_aggr()
    return tfid


@app.get("/read_news_raw")
def read_news_raw(q: Optional[str] = None):
    logger.info(f"ES 데이터 조회 요청: query={q}")
    try:
        news_list = get_news_raw(q)
        if news_list is None:
            return {"status": "error", "message": "데이터를 가져올 수 없습니다."}
        return news_list
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/test")
async def get_test_page(request: Request):
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login")
    return FileResponse("view/html/test.html")


@app.get("/npti/q")
async def get_questions(request: Request, db: Session = Depends(get_db)):
    if not request.session.get("user_id"):
        return JSONResponse(status_code=401, content={"message": "로그인 필요"})

    query = text("SELECT question_id, question_text, npti_axis, question_ratio FROM npti_question")
    result = db.execute(query).fetchall()
    return [dict(row._mapping) for row in result]


@app.post("/test")
async def save_test_result(request: Request, payload: dict = Body(...), db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if not user_id:
        return JSONResponse(status_code=401, content={"success": False, "message": "로그인이 필요합니다."})

    try:
        # 개별 답변 데이터 가공 및 저장 (insert_user_answers 호출)
        answers_list = [
            {"question_no": int(str(q_id).replace('q', '')), "answer_value": val}
            for q_id, val in payload.get("answers", {}).items()
        ]
        insert_user_answers(db, user_id, answers_list)

        # NPTI 결과 데이터 가공 (insert_user_npti 호출)
        scores = payload.get("scores", {})
        updated_at = datetime.now(timezone(timedelta(hours=9))).strftime('%Y-%m-%d %H:%M:%S')
        npti_params = {
            "user_id": user_id,
            "npti_code": payload.get("npti_result"),
            "long_score": scores.get('long'),
            "short_score": scores.get('short'),
            "content_score": scores.get('content'),
            "tale_score": scores.get('tale'),
            "fact_score": scores.get('fact'),
            "insight_score": scores.get('insight'),
            "positive_score": scores.get('positive'),
            "negative_score": scores.get('negative'),
            "updated_at": updated_at
        }
        insert_user_npti(db, npti_params)

        db.commit()  # 최종 커밋
        request.session['hasNPTI']=True
        request.session['npti_result'] = payload.get("npti_result")
        return {"success": True, "message": "저장 완료"}

    except Exception as e:
        db.rollback()
        return JSONResponse(status_code=500, content={"success": False, "message": str(e)})

@app.get("/result")
async def get_result_page(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login")
    user_data = get_user_npti_info(db, user_id)
    if user_id and not user_data:
        return RedirectResponse(url="/test")
    return FileResponse("view/html/result.html")

@app.post("/result")
def api_get_result_data(request: Request, db: Session = Depends(get_db)):
    try:
        user_id = request.session.get("user_id")
        # user_name = request.session.get("user_name", "독자")

        if not user_id:
            return {"isLoggedIn": False, "hasNPTI": False}

        # 1. 최신 데이터 조회 (일반 함수 호출)
        user_data = get_user_npti_info(db, user_id)

        if not user_data:
            return {"isLoggedIn": True, "hasNPTI": False, "user_id": user_id}

        # 2. 날짜 직렬화 (JSON 에러 방지 핵심)
        if user_data.get('updated_at') and isinstance(user_data['updated_at'], datetime):
            user_data['updated_at'] = user_data['updated_at'].strftime('%Y-%m-%d %H:%M:%S')

        # 3. 통합 데이터 반환 (컬럼명 이슈 해결을 위해 별칭을 사용하는 함수들)
        return {
            "isLoggedIn": True,
            "hasNPTI": True,
            "user_id": user_id,
            # "user_name": user_name,
            "user_npti": user_data,
            "code_info": get_npti_code_by_code(db, user_data['npti_code']), # 여기서 에러 해결됨
            "all_types": get_all_npti_type(db) # 여기서도 info_type AS information_type 적용 필요
        }
    except Exception as e:
        print(f"서버 에러 상세: {str(e)}")
        return JSONResponse(status_code=500, content={"message": str(e)})


@app.get("/search")
def main():
    return FileResponse("view/html/search.html")


es = Elasticsearch(
    "http://localhost:9200",
    basic_auth=("elastic", "elastic"),
    verify_certs=False
)

FIELD_MAP = {
    "title": "title_tokens",
    "content": "content_tokens",
    "media": "media",
    "category": "category"
}

@app.post("/search")
def search_news(payload: dict = Body(...)):
    # 1. 요청 데이터 추출
    query_obj = payload.get("query", {}).get("multi_match", {})
    q = query_obj.get("query", "")
    fields = query_obj.get("fields", ["title", "content", "media", "category"])

    from_idx = payload.get("from", 0)
    size = payload.get("size", 20)
    sort_option = payload.get("sort", ["_score"])

    # 검색어 공백 방어
    if not q.strip():
        return {"hits": {"total": {"value": 0}, "hits": []}}

    # 2. 필드 매핑 및 검색 Body 구성 (FIELD_MAP을 통해 실제 토큰 필드명으로 변환)
    field_list = [FIELD_MAP.get(f, f) for f in fields]

    search_condition = {
        "query": {
            "multi_match": {
                "query": q,
                "fields": field_list,
                "operator": "or"
            }
        },
        "from": from_idx,
        "size": size,
        "sort": sort_option
    }

    try:
        # 3. ES 검색 실행 (JS 렌더링에 필요한 필드들을 _source에 명시)
        res = es.search(
            index="news_raw",
            body=search_condition,
            _source=["title", "content", "media", "category", "img", "pubdate"]
        )
        return res  # Elasticsearch 응답 구조 그대로 반환

    except ESConnectionError as e:
        logger.error(f"ES 연결 실패: {e}")
        return {"hits": {"total": {"value": 0}, "hits": []}}
    except Exception as e:
        logger.error(f"검색 오류: {e}")
        return {"hits": {"total": {"value": 0}, "hits": []}}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
    # ----------------------------------------------------------------------------
@app.get("/npti/types", response_model=list[npti_type_response])
def npti_type_list(db: Session = Depends(get_db)):
    try:
        return get_all_npti_type(db)
    except Exception as e:
        logger.error(f"실행 중 오류 발생: {e}")


@app.get("/npti/types/group", response_model=list[npti_type_response])
def npti_type_by_group(group: str = Query(...), db: Session = Depends(get_db)):
    try:
        return get_npti_type_by_group(db, group)
    except Exception as e:
        logger.error(f"실행 중 오류 발생: {e}")


@app.get("/npti/codes", response_model=list[npti_code_response])
def npti_code_list(db: Session = Depends(get_db)):
    try:
        return get_all_npti_codes(db)
    except Exception as e:
        logger.error(f"실행 중 오류 발생: {e}")

@app.get("/npti/codes/{code}", response_model=npti_code_response)
def npti_code_detail(code: str, db: Session = Depends(get_db)):
    try:
        result = get_npti_code_by_code(db, code)
        if not result:
            return {'msg': 'npti_code를 찾을 수 없습니다.'}
        return result
    except Exception as e:
        logger.error(f"실행 중 오류 발생: {e}")

# 관리자
@app.get("/npti/questions", response_model=list[npti_question_response])
def npti_question_list(db: Session = Depends(get_db)):
    try:
        return get_all_npti_questions(db)
    except Exception as e:
        logger.error(f"실행 중 오류 발생: {e}")

# 사용자
@app.get("/npti/questions/axis", response_model=list[npti_question_response])
def npti_question_by_axis(axis: str = Query(...), db: Session = Depends(get_db)):
    try:
        return get_npti_questions_by_axis(db, axis)
    except Exception as e:
        logger.error(f"실행 중 오류 발생: {e}")

# 가입용
@app.get("/signup")
async def get_signup_page(request: Request):
    # isLoggedIn 대신 보통 로그인 시 저장한 user_id 등으로 체크합니다.
    user_id = request.session.get("user_id")
    # 이미 로그인된 사용자가 가입 페이지에 접근하면 메인으로 튕겨냄
    if user_id:
        return RedirectResponse(url="/")
    # 로그인 안 된 사용자에게만 회원가입 파일 전송
    return FileResponse("view/html/signup.html")

# 2. [POST] 회원가입 데이터 처리하기
@app.post("/signup")
def create_user(req: UserCreateRequest, db: Session = Depends(get_db)):
    # DB에 사용자 저장
    insert_user(db, req.model_dump())
    db.commit()
    return {"success":True}

@app.get("/users/check-id")
def check_user_id(user_id: str, db: Session = Depends(get_db)):
    sql = """
        SELECT 1
        FROM user_info
        WHERE user_id = :user_id
        LIMIT 1
    """
    exists = db.execute(text(sql), {"user_id": user_id}).first() is not None
    return {"exists": exists}

# 로그인
@app.get("/login")
def page_login(request: Request):
    user_id = request.session.get("user_id")
    if user_id:
        return RedirectResponse(url="/")
    return FileResponse("view/html/login.html")

@app.post("/login")
def login(req: dict, request: Request, db: Session = Depends(get_db)):
    user_id = req.get("user_id")
    user_pw = req.get("user_pw")

    # 1. 인증 확인
    if not authenticate_user(db, user_id, user_pw):
        return {"success": False, "message": "ID 또는 비밀번호가 틀립니다."}

    # 2. DB에서 데이터 가져오기
    raw_data = get_user_npti_info(db, user_id)

    # 3. 세션 저장
    request.session["user_id"] = user_id


    if raw_data: # 유저 NPTI가 있을 경우
        # 💡 핵심: 복잡한 객체 전체를 넣지 말고,
        # 필요한 'npti_code'(문자열)만 딱 골라서 넣습니다.
        # 이렇게 하면 RowMapping이나 날짜 에러가 전혀 발생하지 않습니다.
        request.session["npti_result"] = raw_data["npti_code"]
        request.session["hasNPTI"] = True
    else:# 유저 NPTI가 없을 경우
        request.session["npti_result"] = None
        request.session["hasNPTI"] = False

    return {"success": True}

@app.post("/users/withdraw")
async def withdraw(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if not user_id:
        return JSONResponse(status_code=401, content={"success": False})

    # 1. DB 상태 변경 (비활성화)
    deactivate_user(db, user_id)

    # 2. 세션 삭제 (로그아웃 처리)
    request.session.clear()
    return {"success": True}

#로그인 상태를 확인
@app.get("/auth/me")
def auth_me(request: Request):
    session = request.session

    user_id = session.get("user_id")
    npti_result = session.get("npti_result")
    logger.info(npti_result)

    return {
        # 로그인 여부
        "isLoggedIn": bool(user_id),

        # 세션 유효성 (이 요청에 도달했으면 True)
        "isSessionValid": True,

        # 부가 정보
        "user_id": user_id,
        "hasNPTI": bool(npti_result),
        "nptiResult": npti_result
    }

@app.post("/logout")
def logout(request: Request):
    request.session.clear()
    return {
        "success": True
    }

@app.get("/api/about")
def get_about(db: Session = Depends(get_db)):

    # 1. NPTI 기준 (npti_type)
    type_rows = db.execute("""
        SELECT npti_group, npti_type, npti_kor
        FROM npti_type
        ORDER BY npti_group, npti_type
    """).fetchall()

    grouped = {}
    for r in type_rows:
        grouped.setdefault(r.npti_group, []).append(r)

    criteria = []
    for group, items in grouped.items():
        if len(items) == 2:
            left, right = items
            criteria.append({
                "title": group.capitalize(),
                "left": f"{left.npti_type} - {left.npti_kor}",
                "right": f"{right.npti_type} - {right.npti_kor}"
            })

    # 2. NPTI 성향 (npti_code)
    code_rows = db.execute("""
        SELECT npti_code, type_nick, type_de,
               length_type, article_type, info_type, view_type
        FROM npti_code
        ORDER BY npti_code
    """).fetchall()

    guides = []
    for r in code_rows:
        guides.append({
            "code": r.npti_code,
            "name": r.type_nick,
            "desc": r.type_de,
            "pref": "",  # 또는 실제 선호 설명 컬럼
            "types": [
                r.length_type,
                r.article_type,
                r.info_type,
                r.view_type
            ]
        })

    return {
        "intro": {
            "title": "NPTI란?",
            "content": "NPTI는 뉴스 소비 성향을 분석해 개인에게 맞는 뉴스 경험을 제공하는 지표입니다."
        },
        "criteria": criteria,
        "guides": guides
    }

@app.post("/mypage")
async def get_my_profile(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if not user_id:
        return JSONResponse(status_code=401, content={"message": "로그인 필요"})

    # 도구 사용
    user = get_my_page_data(db, user_id)

    if not user:
        return JSONResponse(status_code=404, content={"message": "사용자 정보를 찾을 수 없습니다."})

    # [중요] db_user_info.py에서 정의한 'userId' 키값을 사용해야 함
    return {
        "userId": user['userId'],
        "name": user['name'],
        "email": user['email'],
        "birth": user['birth'],
        "age": user['age'],
        "gender": user['gender']
    }


@app.get("/mypage")
async def get_mypage(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")

    # 1. 로그인 체크 먼저 (DB 조회 낭비 방지)
    if not user_id:
        return RedirectResponse(url="/login")

    # 2. DB 조회 (scalar 사용 추천)
    param = {"user_id": user_id}
    sql = text("select admin from user_info where user_id = :user_id")
    # scalar()를 쓰면 result[0] 할 필요 없이 바로 값이 나옴 (없으면 None)
    admin_value = db.execute(sql, param).scalar()

    # 3. 권한 체크
    if admin_value == 0:  # 관리자면 대시보드로
        return RedirectResponse(url="/dashboard")

    # 4. 일반 회원이면 마이페이지 표시
    return FileResponse("view/html/mypage.html")

@app.get("/curation")
def curation_page(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login")
    user_npti = get_user_npti_info(db, user_id)
    if user_id and not user_npti:
        return RedirectResponse(url="/test")
    return FileResponse("view/html/curation.html")

@app.get("/user/npti/me")
async def get_user_npti(request: Request,db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")

    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # user_npti와 npti_code 테이블 조인 (기본 정보 및 별칭 조회)
    result = db.query(
        UserNPTITable,
        NptiCodeTable.type_nick
    ).join(
        NptiCodeTable, UserNPTITable.npti_code == NptiCodeTable.npti_code
    ).filter(
        UserNPTITable.user_id == user_id
    ).order_by(
        UserNPTITable.updated_at.desc()
    ).first()

    # 유저는 있으나 NPTI 없음 → 404
    if not result:
        raise HTTPException(status_code=404, detail="NPTI data not found")

    user_data, type_nick = result
    npti_code_str = user_data.npti_code

    # 각 알파벳에 매칭되는 npti_kor 값 가져오기 (npti_type 테이블 조회)
    # npti_type 테이블에서 NPTI_type 컬럼이 코드에 포함된 것들만 조회
    chars = list(npti_code_str)
    type_items = db.query(NptiTypeTable) \
        .filter(NptiTypeTable.NPTI_type.in_(chars)) \
        .all()

    # 순서(S-T-F-N)에 맞게 딕셔너리로 맵핑 생성
    kor_map = {item.NPTI_type: item.npti_kor for item in type_items}
    # 최종 리스트 생성 (예: ["짧은", "이야기형", "객관적", "비판적"])
    npti_kor_list = [kor_map.get(c, "") for c in chars]

    return {
        "npti_code": npti_code_str,
        "type_nick": type_nick,
        "npti_kor_list": npti_kor_list,
        "updated_at": user_data.updated_at
    }


@app.get("/curated/news")
async def get_curated_news(
        npti: str = Query(...),
        category: str = "all",
        sort_type: str = "accuracy",
        page: int = 1,
        db: Session = Depends(get_db)
):

    ITEMS_PER_PAGE = 20  # 한 페이지에 기사 20개
    offset = (page - 1) * ITEMS_PER_PAGE

    # DB에서 해당 NPTI_code를 가진 news_id 리스트를 먼저 가져옴
    news_ids = db.query(ArticlesNPTI.news_id).filter(
        ArticlesNPTI.NPTI_code == npti
    ).all()

    id_list = [id[0] for id in news_ids]
    if not id_list:
        return {"articles": [], "total": 0}

    # ES 쿼리 작성
    body = {
        "track_total_hits": True,
        "from": offset,
        "size": ITEMS_PER_PAGE,
        "query": {
            "bool": {
                "must": [{"terms": {"news_id": id_list}}]
            }
        }
    }

    if category != "all":
        body["query"]["bool"]["filter"] = [
            {"match": {"category": category}}  #term 쓰려면 ES 매핑 수정해야함
        ]

    # 3. 정렬 조건 처리
    if sort_type == "latest":
        body["sort"] = [{"pubdate": {"order": "desc"}}]
    else:
        body["sort"] = [{"_score": {"order": "desc"}}]

    try:
        res = es.search(index=ES_INDEX, body=body)
        hits = res["hits"]["hits"]

        # 3. 기존 search_article의 데이터 가공 방식을 그대로 활용
        articles = []
        for hit in hits:
            src = hit["_source"]
            articles.append({
                "id": src.get("news_id", ""),
                "title": src.get("title", ""),
                "summary": src.get("content", "")[:150] + "...",
                "publisher": src.get("media", ""),
                "date": src.get("pubdate", ""),
                "thumbnail": src.get("img", ""),
                "category": src.get("category", "")
            })

        total_count = res["hits"]["total"]["value"]
        return {
            "articles": articles,
            "total": total_count,
            "sort":body["sort"][0]
        }
    except Exception as e:
        logger.error(f"큐레이션 뉴스 검색 오류: {e}")
        return {"articles": [], "total": 0}

@app.get("/update_user_npti")
def update_user_npti(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    latest_user_npti = get_user_npti_info(db, user_id)
    long_score = latest_user_npti.get("long_score")
    short_score = latest_user_npti.get("short_score")
    content_score = latest_user_npti.get("content_score")
    tale_score = latest_user_npti.get("tale_score")
    fact_score = latest_user_npti.get("fact_score")
    insight_score = latest_user_npti.get("insight_score")
    positive_score = latest_user_npti.get("positive_score")
    negative_score = latest_user_npti.get("negative_score")
    latest_update_time = latest_user_npti.get('timestamp')
    behavior_log_per_news = search_user_behavior(user_id, latest_update_time) # [[{},{}],[{},{},{},],[{}]] 형태
    for behavior_log in behavior_log_per_news: # [{},{}]
        if not behavior_log:
            continue
        result = model_predict_proba(behavior_log)# {userid:, news_id:, dwell time:, final_read_time:, reading_efficiency: } 같은 dictionary
        reading_efficiency = result.get('reading_efficiency')
        id = result.get('news_id')
        body = {"query": {"term": {"news_id": id}},"_source": ["content"]}
        response = search_news_condition(body)
        n_word = 0
        if response and response['hits']['hits']:
            source_data = response['hits']['hits'][0]['_source']
            content = source_data.get('content',"")
            if content :
                n_word = len(content.split())
                print(f"news_id : {id} | n_word : {n_word}")
        interest_score = min(1, reading_efficiency * (math.log(n_word+1) / math.log(501)))*10
        result = db.query(ArticlesNPTI).filter(ArticlesNPTI.news_id == id).first()
        news_length_type = result.length_type
        news_article_type = result.article_type
        news_info_type = result.info_type
        news_view_type = result.view_type
        # user_npti 점수에 interest_score 반영하는 로직 !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!! (까먹으면 안됨)
        if news_length_type == "L":
            long_score += interest_score
            short_score -= interest_score
        else:
            short_score += interest_score
            long_score -= interest_score
        if news_article_type == "C":
            content_score += interest_score
            tale_score -= interest_score
        else:
            tale_score += interest_score
            content_score -= interest_score
        if news_info_type == "F":
            fact_score += interest_score
            insight_score -= interest_score
        else:
            insight_score += interest_score
            fact_score -= interest_score
        if news_view_type == "P":
            positive_score += interest_score
            negative_score -= interest_score
        else:
            negative_score += interest_score
            positive_score -= interest_score
    final_long_score = finalize_score(long_score)
    final_short_score = 100 - final_long_score
    final_tale_score = finalize_score(tale_score)
    final_content_score = 100 - final_tale_score
    final_insight_score = finalize_score(insight_score)
    final_fact_score = 100 - final_insight_score
    final_negative_score = finalize_score(negative_score)
    final_positive_score = 100 - final_negative_score
    final_length_type = "L" if final_long_score > final_short_score else "S"
    final_article_type = "T" if final_tale_score > final_content_score else "C"
    final_info_type = "I" if final_insight_score > final_fact_score else "F"
    final_view_type = "N" if final_negative_score > final_positive_score else "P"
    final_user_npti = final_length_type+final_article_type+final_info_type+final_view_type
    updated_at = datetime.now(timezone(timedelta(hours=9))).strftime('%Y-%m-%d %H:%M:%S')
    query = text("SELECT type_nick, type_de FROM npti_code WHERE npti_code = :code")
    description = db.execute(query, {"code": final_user_npti}).fetchone()
    params = {
        "latest_update_time":latest_update_time,
        "user_id": user_id,
        "npti_code": final_user_npti,
        "type_nick" : description[0],
        "type_de" : description[1],
        "long_score": final_long_score,
        "short_score": final_short_score,
        "content_score": final_content_score,
        "tale_score": final_tale_score,
        "fact_score": final_fact_score,
        "insight_score": final_insight_score,
        "positive_score": final_positive_score,
        "negative_score": final_negative_score,
        "updated_at": updated_at
    }
    insert_user_npti(db, params)
    # long, content, insight, positive
    request.session['user_npti'] = final_user_npti
    request.session['nptiResult'] = final_user_npti
    request.session['npti_result'] = final_user_npti
    print("회원 npti 정보가 성공적으로 업데이트 되었습니다!!!")

    return params

async def update_state_loop():
    while True:
        if not result_queue.empty():
            latest_breaking = result_queue.get()
            if isinstance(latest_breaking, dict) and "final_group" in latest_breaking:
                app.state.breaking_news = latest_breaking
                print("New breaking news data updated!")
        await asyncio.sleep(1)

@app.on_event("startup")
async def startup_event():
    if not sch.running:
        sch.start()
    app.state.breaking_news = {'msg':'스케쥴러 가동 중 - 데이터 준비 중'} # 초기값
    asyncio.create_task(update_state_loop())

@app.get("/render_breaking")
def render_breaking():
    grouping_result = getattr(app.state, "breaking_news", {"msg": "데이터가 아직 없습니다."})
    breaking_topic = grouping_result.get('final_group') # None or ['news_id1', 'news_id2']
    if not breaking_topic:
        return {"breaking_news": None, "msg":"데이터 없음"}
    id_title_list = []
    for topic in breaking_topic:
        query = {"size": 1,"_source": ["news_id", "title", "timestamp"],
          "query": {"terms": {"news_id": topic}},
          "sort": [{"timestamp": {"order": "desc"}}]}
        res = search_news_condition(query)
        if res and res.get("hits") and res["hits"]["hits"]:
            first_hit = res["hits"]["hits"][0]["_source"]
            id_title = {"id":first_hit["news_id"], "title":first_hit["title"]}
            id_title_list.append(id_title)

    return {"breaking_news": id_title_list, "msg":"데이터 있음"}

@app.get("/render_general")
def render_general(category:str):
    news_list = []
    if category == "전체" or category == 'all':
        cate_list = ["정치", "경제", "사회", "생활/문화", "IT/과학", "세계", "스포츠","연예","지역"]
        for category in cate_list:
            query = {"query": {"match":{"category":category}}, "sort": [{"pubdate": {"order": "desc"}}],
                     "size": 1, "_source": ["news_id", "title", "content", "img"]}
            res = search_news_condition(query)
            src = res["hits"]["hits"][0]["_source"]
            news_item = {"news_id": src.get("news_id", ""),
                         "title": src.get("title", ""),
                         "desc": src.get("content", ""),
                         "img": src.get("img", ""),
                         "link": f"/article?news_id={src['news_id']}"}
            news_list.append(news_item)
    else :
        query = {"query": {"match":{"category":category}}, "sort": [{"pubdate": {"order": "desc"}}],
                 "size": 9, "_source": ["news_id", "title", "content", "img"]}
        res = search_news_condition(query)
        for hit in res["hits"]["hits"]:
            src = hit["_source"]
            news_item = {"news_id": src.get("news_id", ""),
                         "title": src.get("title", ""),
                         "desc": src.get("content", ""),
                         "img": src.get("img", ""),
                         "link": f"/article?news_id={src['news_id']}"}
            news_list.append(news_item)
    return news_list

@app.get("/render_general_npti")
def render_general(category:str, npti_code:str, db: Session = Depends(get_db)):
    news_list = []
    sql = text("select news_id from articles_npti where npti_code = :code")
    params = {"code":npti_code}
    news_ids = db.execute(sql, params).scalars().fetchall()
    if not news_ids:
        return []
    if category == "전체" or category == 'all':
        cate_list = ["정치", "경제", "사회", "생활/문화", "IT/과학", "세계", "스포츠", "연예", "지역"]
        for category in cate_list:
            query = {"size": 1,"_source": ["news_id", "title", "content", "img"],"sort": [{"pubdate": {"order": "desc"}}],
                    "query": {"bool": {"must": {"match":{"category":category}},"filter": [{"terms": {"news_id": news_ids}}]}}}
            res = search_news_condition(query)
            if res["hits"]["hits"]:
                src = res["hits"]["hits"][0]["_source"]
                news_item = {"news_id": src.get("news_id", ""),
                             "title": src.get("title", ""),
                             "desc": src.get("content", ""),
                             "img": src.get("img", ""),
                             "link": f"/article?news_id={src['news_id']}"}
                news_list.append(news_item)
    else :
        query = {"size": 9,"_source": ["news_id", "title", "content", "img"],"sort": [{"pubdate": {"order": "desc"}}],
            "query": {"bool": {"must": {"match":{"category":category}},"filter": [{"terms": {"news_id": news_ids}}]}}}
        res = search_news_condition(query)
        for hit in res["hits"]["hits"]:
            src = hit["_source"]
            news_item = {"news_id": src.get("news_id", ""),
                         "title": src.get("title", ""),
                         "desc": src.get("content", ""),
                         "img": src.get("img", ""),
                         "link": f"/article?news_id={src['news_id']}"}
            news_list.append(news_item)
    return news_list

@app.get("/profile-edit")
async def get_profile_edit_page(request: Request):
    user_id = request.session.get("user_id")
    if not user_id:
        # 로그인 안 됐으면 HTML조차 보여주지 않고 즉시 리다이렉트
        return RedirectResponse(url="/")
    return FileResponse("view/html/profile-edit.html")

@app.get("/users/profile")
async def get_user_profile(user_id: str = Query(...), db: Session = Depends(get_db)):
    """가공된 프로필 데이터를 반환하는 API"""
    user_data = get_my_page_data(db, user_id)
    if not user_data:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    return user_data


@app.post("/users/verify-password")
async def verify_password_check(data:dict, db:Session = Depends(get_db)):
    user_id = data.get("user_id")
    current_pw = data.get("current_password")

    user = db.query(UserInfo).filter(UserInfo.user_id == user_id).first()
    if user and user.user_pw and verify_password(current_pw, user.user_pw):
        return {"success": True, "message": "현재 비밀번호와 일치합니다."}

    return {"success": False, "message": "현재 비밀번호와 일치하지 않습니다."}

@app.post("/users/check-new-password")
def check_new_password_api(data: dict, db: Session = Depends(get_db)):
    user_id = data.get("user_id")
    new_password = data.get("new_password")

    user = db.query(UserInfo).filter(UserInfo.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")

    is_same = verify_password(new_password, user.user_pw)
    return {"is_same": is_same}

@app.post("/users/update")
async def update_user(data: UserUpdate, db: Session = Depends(get_db)):
    try:
        user = db.query(UserInfo).filter(UserInfo.user_id == data.user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")

        # 현재 비밀번호 검증 (sha256 해시 비교)
        if not verify_password(data.current_password, user.user_pw):
            raise HTTPException(status_code=400, detail="현재 비밀번호와 일치하지 않습니다.")

        # 데이터 업데이트
        user.user_name = data.user_name
        user.user_age = data.user_age
        user.user_email = data.user_email
        if data.user_gender:
            user.user_gender = 1 if "female" in data.user_gender else 0

        try:
            if data.user_birth:
                # 문자열 "YYYY-MM-DD"를 파이썬 date 객체로 변환
                user.user_birth = datetime.strptime(data.user_birth, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="생년월일 형식이 올바르지 않습니다. (YYYY-MM-DD)")

        if data.new_password and data.new_password.strip():
            user.user_pw = hash_password(data.new_password)

        db.commit()
        return {"success": True}

    except Exception as e:
        db.rollback()
        logger.info(f'유저 프로필 업데이트 중 서버 에러 발생: {str(e)}')
        raise HTTPException(status_code=500, detail=f"서버 내부 오류: {str(e)}")


@app.get("/dashboard")
def dashboard(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")

    # 1. 로그인 체크 먼저
    if not user_id:
        return RedirectResponse(url="/login")

    # 2. DB 조회
    param = {"user_id": user_id}
    sql = text("select admin from user_info where user_id = :user_id")
    admin_value = db.execute(sql, param).scalar()

    # 3. 권한 체크
    if admin_value == 0: # 관리자만 통과
        return FileResponse("view/html/dashboard.html")
    else: # 일반 회원은 메인으로 추방
        return RedirectResponse(url="/")


@app.get("/members_statistics")
def members_statistics(db: Session = Depends(get_db)):
    today_str = datetime.now(timezone(timedelta(hours=9))).strftime('%Y-%m-%d')
    today = datetime.now(timezone(timedelta(hours=9)))
    this_monday = today - timedelta(days=today.weekday())
    this_monday_str = this_monday.strftime('%Y-%m-%d')
    this_month_start = today.replace(day=1)
    this_month_str = this_month_start.strftime('%Y-%m-%d')

    print(f'데이터 추출 시작')

    # [Helper 함수] DB 결과를 딕셔너리 리스트로 변환
    def rows_to_dict(result_proxy):
        return [dict(row._asdict()) for row in result_proxy]

    # [Helper 함수] 단일 행(1 row) 결과를 딕셔너리로 변환
    def row_to_dict(row):
        return dict(row._asdict()) if row else {}

    try:
        # =========================================================
        # 1. NPTI 회원 분포 (Pie Chart용)
        # =========================================================

        # 1-1) NPTI 코드별 비율 -------------------------------- 쿼리 검증 완료
        sql1_1 = text("""
            WITH LatestUserNPTI AS (
                SELECT 
                    user_id,  
                    npti_code,
                    ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY updated_at DESC) as rn
                FROM user_npti
            )
            SELECT 
                IFNULL(L.npti_code, '미진단') AS npti_code, 
                COUNT(*) as count 
            FROM user_info U
            LEFT JOIN LatestUserNPTI L 
                ON U.user_id = L.user_id AND L.rn = 1 
            WHERE U.activation = 1 AND U.admin = 1
            GROUP BY IFNULL(L.npti_code, '미진단')
            ORDER BY count DESC;
        """)
        result1_1 = rows_to_dict(db.execute(sql1_1).fetchall())
        print('result1_1 완료')


        # 1-2) 연령대별 비율 ----------------------------------- 쿼리 검증 완료
        sql1_2 = text("""
            SELECT 
                CASE 
                    WHEN user_age < 20 THEN '10대 이하' 
                    WHEN user_age >= 20 AND user_age < 30 THEN '20대'
                    WHEN user_age >= 30 AND user_age < 40 THEN '30대' 
                    WHEN user_age >= 40 AND user_age < 50 THEN '40대'
                    WHEN user_age >= 50 AND user_age < 60 THEN '50대' 
                    ELSE '60대 이상' 
                END AS age_group, 
                COUNT(*) AS count
            FROM user_info 
            WHERE activation = 1 and admin = 1
            GROUP BY age_group 
            ORDER BY age_group;
        """)
        # DB 실행 결과
        result1_2_1 = rows_to_dict(db.execute(sql1_2).fetchall())
        # [후처리] 모든 연령대 카테고리 정의
        all_groups = ['10대 이하', '20대', '30대', '40대', '50대', '60대 이상']
        # 딕셔너리로 변환하여 매핑 (예: {'20대': 50, '10대 이하': 15 ...})
        result_map = {row['age_group']: row['count'] for row in result1_2_1}
        # 빈 카테고리는 0으로 채워서 최종 리스트 생성
        result1_2 = [
            {'age_group': group, 'count': result_map.get(group, 0)}
            for group in all_groups
        ]
        print(result1_2) # 결과: 모든 연령대가 순서대로 존재하며, 없는 그룹은 count: 0으로 보장됨

        # 1-3) 성별 비율 --------------------------------------- 쿼리 검증 완료
        sql1_3 = text("""SELECT user_gender, COUNT(*) as count FROM user_info 
            WHERE activation = 1 and admin = 1 GROUP BY user_gender;""")

        # 1. DB 결과 가져오기 (데이터가 있는 성별만 나옴)
        result1_3_raw = rows_to_dict(db.execute(sql1_3).fetchall())

        # 2. [후처리] 0값 채우기
        # 보장해야 할 키값 목록 (0과 1)
        target_genders = [0, 1]

        # 검색 속도를 위해 DB 결과를 딕셔너리로 변환 ( {0: 15, 1: 20} 형태 )
        gender_map = {row['user_gender']: row['count'] for row in result1_3_raw}

        # 타겟 리스트(0, 1)를 순회하며 데이터가 없으면 count: 0으로 설정
        result1_3 = [
            {'user_gender': g, 'count': gender_map.get(g, 0)}
            for g in target_genders
        ]

        print('result1_3 (성별 0, 1 포함) 완료')

        # =========================================================
        # 2. NPTI 코드별 변화 추이 (Line Graph용)
        # =========================================================

        # 2-1) 일별 누적 (최근 7일 날짜별 모든 유저의 최종 상태) --------------- 쿼리 검증 완료
        sql2_1 = text(f"""
            WITH RECURSIVE Past7Days AS (
                -- 1. [타임라인] 최근 7일 날짜 생성
                SELECT '{today_str}' - INTERVAL 6 DAY AS date_period
                UNION ALL
                SELECT date_period + INTERVAL 1 DAY
                FROM Past7Days
                WHERE date_period < '{today_str}'
            ),
            AllNPTICodes AS (
                -- 2. [코드 목록] 존재하는 모든 NPTI 코드 가져오기 (16개 유형 등)
                -- (npti_code 테이블이 있다고 가정, 만약 없다면 DISTINCT npti_code FROM user_npti 사용)
                SELECT npti_code FROM npti_code
            ),
            DateCodeGrid AS (
                -- 3. [그리드 생성] (7일 날짜) x (모든 NPTI 코드) 조합 생성
                -- 데이터가 없어도 이 조합은 무조건 존재해야 함
                SELECT d.date_period, c.npti_code
                FROM Past7Days d
                CROSS JOIN AllNPTICodes c
            ),
            DailySnapshot AS (
                -- 4. [실제 데이터] 유저별 일자별 최종 상태 계산
                SELECT 
                    d.date_period,
                    u.npti_code,
                    ROW_NUMBER() OVER (
                        PARTITION BY d.date_period, u.user_id 
                        ORDER BY u.updated_at DESC
                    ) as rn
                FROM Past7Days d
                LEFT JOIN user_npti u
                    ON u.updated_at < d.date_period + INTERVAL 1 DAY
                JOIN user_info ui
                    ON u.user_id = ui.user_id
                WHERE ui.activation = 1 AND ui.admin = 1
            )
            SELECT 
                G.date_period, 
                G.npti_code, 
                -- 5. 그리드(G)를 기준으로 데이터(S)를 붙여서 카운트
                COUNT(CASE WHEN S.rn = 1 THEN 1 END) as user_count
            FROM DateCodeGrid G
            LEFT JOIN DailySnapshot S
              ON G.date_period = S.date_period 
              AND G.npti_code = S.npti_code
            GROUP BY G.date_period, G.npti_code
            ORDER BY G.date_period ASC, G.npti_code ASC;
        """)

        result2_1 = rows_to_dict(db.execute(sql2_1).fetchall())
        print('result2_1 (최근 7일 누적 - 0포함) 완료')

        # 2-2) 주별 누적 (해당 주차 기준, 모든 유저의 최종 상태) --------------- 쿼리 검증 완료
        sql2_2 = text(f"""
            WITH RECURSIVE Past4Weeks AS (
                -- 1. [타임라인] 최근 4주 월요일 날짜 생성
                SELECT '{this_monday_str}' AS week_start
                UNION ALL
                SELECT week_start - INTERVAL 1 WEEK
                FROM Past4Weeks
                WHERE week_start > '{this_monday_str}' - INTERVAL 3 WEEK
            ),
            AllNPTICodes AS (
                -- 2. [코드 목록] 모든 NPTI 코드 가져오기 (16개 유형)
                SELECT npti_code FROM npti_code
            ),
            WeekCodeGrid AS (
                -- 3. [그리드 생성] (4주) x (모든 NPTI 코드) 조합
                -- 데이터 유무와 상관없이 무조건 존재하는 뼈대
                SELECT w.week_start, c.npti_code
                FROM Past4Weeks w
                CROSS JOIN AllNPTICodes c
            ),
            WeeklySnapshot AS (
                -- 4. [실제 데이터] 주차별 유저의 최종 상태 스냅샷
                SELECT 
                    w.week_start,
                    u.npti_code,
                    ROW_NUMBER() OVER (
                        PARTITION BY w.week_start, u.user_id 
                        ORDER BY u.updated_at DESC
                    ) as rn
                FROM Past4Weeks w
                LEFT JOIN user_npti u
                    -- 해당 주차 일요일 밤(다음주 월요일 0시)까지의 누적 기록
                    ON u.updated_at < w.week_start + INTERVAL 1 WEEK
                JOIN user_info ui
                    ON u.user_id = ui.user_id
                WHERE ui.activation = 1 AND ui.admin = 1
            )
            SELECT 
                -- 날짜를 'YYYY-MM-DD ~ YYYY-MM-DD' 형태로 변환
                CONCAT(G.week_start, '\n~ ', DATE_ADD(G.week_start, INTERVAL 6 DAY)) AS date_period,

                G.npti_code, 

                -- 5. 그리드(G)에 데이터(S)를 매핑하여 카운트 (없으면 0)
                COUNT(CASE WHEN S.rn = 1 THEN 1 END) as user_count
            FROM WeekCodeGrid G
            LEFT JOIN WeeklySnapshot S
              ON G.week_start = S.week_start 
              AND G.npti_code = S.npti_code
            GROUP BY G.week_start, G.npti_code
            ORDER BY G.week_start ASC, G.npti_code ASC;
        """)

        result2_2 = rows_to_dict(db.execute(sql2_2).fetchall())
        print('result2_2 (주간 기간 표시 - 0포함) 완료')

        # 2-3) 월별 누적 (해당 월 기준, 모든 유저의 최종 상태) ------------- 쿼리 검증 완료
        sql2_3 = text(f"""
            WITH RECURSIVE Past6Months AS (
                -- 1. [타임라인] 최근 6개월 '매월 1일' 생성
                SELECT '{this_month_str}' AS month_start
                UNION ALL
                SELECT month_start - INTERVAL 1 MONTH
                FROM Past6Months
                WHERE month_start > '{this_month_str}' - INTERVAL 5 MONTH
            ),
            AllNPTICodes AS (
                -- 2. [코드 목록] 모든 NPTI 코드 가져오기 (16개 유형)
                SELECT npti_code FROM npti_code
            ),
            MonthCodeGrid AS (
                -- 3. [그리드 생성] (6개월) x (모든 NPTI 코드) 조합
                -- 데이터가 없어도 무조건 존재해야 하는 뼈대
                SELECT m.month_start, c.npti_code
                FROM Past6Months m
                CROSS JOIN AllNPTICodes c
            ),
            MonthlySnapshot AS (
                -- 4. [실제 데이터] 월별 유저의 최종 상태 스냅샷
                SELECT 
                    m.month_start,
                    u.npti_code,
                    ROW_NUMBER() OVER (
                        PARTITION BY m.month_start, u.user_id 
                        ORDER BY u.updated_at DESC
                    ) as rn
                FROM Past6Months m
                LEFT JOIN user_npti u
                    -- 해당 월의 말일(다음달 1일 0시 전)까지의 누적 기록
                    ON u.updated_at < m.month_start + INTERVAL 1 MONTH
                JOIN user_info ui
                    ON u.user_id = ui.user_id
                WHERE ui.activation = 1 AND ui.admin = 1
            )
            SELECT 
                -- 날짜를 'YYYY-MM' 형태로 변환
                DATE_FORMAT(G.month_start, '%Y-%m') AS date_period,

                G.npti_code, 

                -- 5. 그리드(G)에 데이터(S)를 매핑하여 카운트 (없으면 0)
                COUNT(CASE WHEN S.rn = 1 THEN 1 END) as user_count
            FROM MonthCodeGrid G
            LEFT JOIN MonthlySnapshot S
              ON G.month_start = S.month_start 
              AND G.npti_code = S.npti_code
            GROUP BY G.month_start, G.npti_code
            ORDER BY G.month_start ASC, G.npti_code ASC;
        """)

        result2_3 = rows_to_dict(db.execute(sql2_3).fetchall())
        print('result2_3 (최근 6개월 누적 - 0포함) 완료')

        # =========================================================
        # 3. NPTI 8개 속성별 분포 (Bar Chart용) ---------------------------------- 쿼리 검증 완료
        # =========================================================
        sql3 = text("""
            WITH LatestUserSnapshot AS (
                SELECT 
                    u.user_id,
                    u.npti_code,
                    -- 유저별 가장 최신 기록 순위 매기기
                    ROW_NUMBER() OVER (PARTITION BY u.user_id ORDER BY u.updated_at DESC) as rn
                FROM user_npti u
            )
            SELECT 
                COUNT(CASE WHEN C.length_type = 'L' THEN 1 END) AS L_count,
                COUNT(CASE WHEN C.length_type = 'S' THEN 1 END) AS S_count,

                COUNT(CASE WHEN C.article_type = 'C' THEN 1 END) AS C_count,
                COUNT(CASE WHEN C.article_type = 'T' THEN 1 END) AS T_count,

                COUNT(CASE WHEN C.info_type = 'I' THEN 1 END) AS I_count,
                COUNT(CASE WHEN C.info_type = 'F' THEN 1 END) AS F_count,

                COUNT(CASE WHEN C.view_type = 'P' THEN 1 END) AS P_count,
                COUNT(CASE WHEN C.view_type = 'N' THEN 1 END) AS N_count
            FROM LatestUserSnapshot S
            -- [핵심 수정] user_info 테이블과 조인하여 회원 상태 확인
            JOIN user_info UI ON S.user_id = UI.user_id
            -- NPTI 속성(L/S, C/T...) 정보를 가져오기 위해 조인
            JOIN npti_code C ON S.npti_code = C.npti_code
            WHERE S.rn = 1                 -- 최신 기록만
              AND UI.activation = 1        -- 활성화된 회원만
              AND UI.admin = 1;            -- 일반 회원만
        """)
        result3 = row_to_dict(db.execute(sql3).fetchone())
        print('result3 완료')

        # =========================================================
        # 4. NPTI 8개 속성별 변화 추이 (Line Graph용)
        # =========================================================

        # 4-1) 일별 (누적 기준)
        sql4_1 = text(f"""
            WITH RECURSIVE Past7Days AS (
                -- 1. [타임라인] 최근 7일 날짜 생성
                SELECT '{today_str}' - INTERVAL 6 DAY AS date_period
                UNION ALL
                SELECT date_period + INTERVAL 1 DAY
                FROM Past7Days
                WHERE date_period < '{today_str}'
            ),
            DailySnapshot AS (
                -- 2. [스냅샷] 날짜별 유저들의 최종 상태
                SELECT 
                    d.date_period,
                    u.npti_code,
                    ROW_NUMBER() OVER (
                        PARTITION BY d.date_period, u.user_id 
                        ORDER BY u.updated_at DESC
                    ) as rn
                FROM Past7Days d
                LEFT JOIN user_npti u
                    ON u.updated_at < d.date_period + INTERVAL 1 DAY
                JOIN user_info ui
                    ON u.user_id = ui.user_id
                WHERE ui.activation = 1 AND ui.admin = 1
            )
            SELECT 
                P.date_period,

                -- 4. 유효한 데이터(rn=1)가 있을 때만 카운트, 없으면 0
                COUNT(CASE WHEN S.rn = 1 AND C.length_type = 'L' THEN 1 END) AS L_count,
                COUNT(CASE WHEN S.rn = 1 AND C.length_type = 'S' THEN 1 END) AS S_count,

                COUNT(CASE WHEN S.rn = 1 AND C.article_type = 'C' THEN 1 END) AS C_count,
                COUNT(CASE WHEN S.rn = 1 AND C.article_type = 'T' THEN 1 END) AS T_count,

                COUNT(CASE WHEN S.rn = 1 AND C.info_type = 'I' THEN 1 END) AS I_count,
                COUNT(CASE WHEN S.rn = 1 AND C.info_type = 'F' THEN 1 END) AS F_count,

                COUNT(CASE WHEN S.rn = 1 AND C.view_type = 'P' THEN 1 END) AS P_count,
                COUNT(CASE WHEN S.rn = 1 AND C.view_type = 'N' THEN 1 END) AS N_count

            FROM Past7Days P  -- [핵심] 기준이 되는 타임라인을 먼저 둡니다.
            LEFT JOIN DailySnapshot S
                ON P.date_period = S.date_period 
            LEFT JOIN npti_code C 
                ON S.npti_code = C.npti_code
            GROUP BY P.date_period
            ORDER BY P.date_period ASC;
        """)

        result4_1 = rows_to_dict(db.execute(sql4_1).fetchall())
        print('result4_1 (최근 7일 상세 분포 - 0포함) 완료')

        # 4-2) 주별 (누적 기준)
        sql4_2 = text(f"""
            WITH RECURSIVE Past4Weeks AS (
                -- 1. [타임라인] 최근 4주 월요일 날짜 생성
                SELECT '{this_monday_str}' AS week_start
                UNION ALL
                SELECT week_start - INTERVAL 1 WEEK
                FROM Past4Weeks
                WHERE week_start > '{this_monday_str}' - INTERVAL 3 WEEK
            ),
            WeeklySnapshot AS (
                -- 2. [스냅샷] 주차별 유저들의 최종 상태
                SELECT 
                    w.week_start,
                    u.npti_code,
                    ROW_NUMBER() OVER (
                        PARTITION BY w.week_start, u.user_id 
                        ORDER BY u.updated_at DESC
                    ) as rn
                FROM Past4Weeks w
                LEFT JOIN user_npti u
                    ON u.updated_at < w.week_start + INTERVAL 1 WEEK
                JOIN user_info ui
                    ON u.user_id = ui.user_id
                WHERE ui.activation = 1 AND ui.admin = 1
            )
            SELECT 
                -- 날짜를 'YYYY-MM-DD ~ YYYY-MM-DD' 형태로 변환
                CONCAT(P.week_start, '\n~ ', DATE_ADD(P.week_start, INTERVAL 6 DAY)) AS date_period,

                -- 4. 유효한 데이터(rn=1)가 있을 때만 카운트, 없으면 0
                COUNT(CASE WHEN S.rn = 1 AND C.length_type = 'L' THEN 1 END) AS L_count,
                COUNT(CASE WHEN S.rn = 1 AND C.length_type = 'S' THEN 1 END) AS S_count,

                COUNT(CASE WHEN S.rn = 1 AND C.article_type = 'C' THEN 1 END) AS C_count,
                COUNT(CASE WHEN S.rn = 1 AND C.article_type = 'T' THEN 1 END) AS T_count,

                COUNT(CASE WHEN S.rn = 1 AND C.info_type = 'I' THEN 1 END) AS I_count,
                COUNT(CASE WHEN S.rn = 1 AND C.info_type = 'F' THEN 1 END) AS F_count,

                COUNT(CASE WHEN S.rn = 1 AND C.view_type = 'P' THEN 1 END) AS P_count,
                COUNT(CASE WHEN S.rn = 1 AND C.view_type = 'N' THEN 1 END) AS N_count

            FROM Past4Weeks P -- [핵심] 기준이 되는 타임라인을 먼저 둡니다.
            LEFT JOIN WeeklySnapshot S
                ON P.week_start = S.week_start
            LEFT JOIN npti_code C 
                ON S.npti_code = C.npti_code
            GROUP BY P.week_start
            ORDER BY P.week_start ASC;
        """)

        result4_2 = rows_to_dict(db.execute(sql4_2).fetchall())
        print('result4_2 (최근 4주 성향 상세 - 0포함) 완료')

        # 4-3) 월별 (누적 기준)
        sql4_3 = text(f"""
            WITH RECURSIVE Past6Months AS (
                -- 1. [타임라인] 최근 6개월 '매월 1일' 생성
                SELECT '{this_month_str}' AS month_start
                UNION ALL
                SELECT month_start - INTERVAL 1 MONTH
                FROM Past6Months
                WHERE month_start > '{this_month_str}' - INTERVAL 5 MONTH
            ),
            MonthlySnapshot AS (
                -- 2. [스냅샷] 월별 유저들의 최종 상태
                SELECT 
                    m.month_start,
                    u.npti_code,
                    ROW_NUMBER() OVER (
                        PARTITION BY m.month_start, u.user_id 
                        ORDER BY u.updated_at DESC
                    ) as rn
                FROM Past6Months m
                LEFT JOIN user_npti u
                    ON u.updated_at < m.month_start + INTERVAL 1 MONTH
                JOIN user_info ui
                    ON u.user_id = ui.user_id
                WHERE ui.activation = 1 AND ui.admin = 1
            )
            SELECT 
                -- 날짜를 'YYYY-MM' 형태로 변환
                DATE_FORMAT(P.month_start, '%Y-%m') AS date_period,

                -- 4. 유효한 데이터(rn=1)가 있을 때만 카운트, 없으면 0
                COUNT(CASE WHEN S.rn = 1 AND C.length_type = 'L' THEN 1 END) AS L_count,
                COUNT(CASE WHEN S.rn = 1 AND C.length_type = 'S' THEN 1 END) AS S_count,

                COUNT(CASE WHEN S.rn = 1 AND C.article_type = 'C' THEN 1 END) AS C_count,
                COUNT(CASE WHEN S.rn = 1 AND C.article_type = 'T' THEN 1 END) AS T_count,

                COUNT(CASE WHEN S.rn = 1 AND C.info_type = 'I' THEN 1 END) AS I_count,
                COUNT(CASE WHEN S.rn = 1 AND C.info_type = 'F' THEN 1 END) AS F_count,

                COUNT(CASE WHEN S.rn = 1 AND C.view_type = 'P' THEN 1 END) AS P_count,
                COUNT(CASE WHEN S.rn = 1 AND C.view_type = 'N' THEN 1 END) AS N_count

            FROM Past6Months P -- [핵심] 기준이 되는 타임라인을 먼저 둡니다.
            LEFT JOIN MonthlySnapshot S
                ON P.month_start = S.month_start
            LEFT JOIN npti_code C 
                ON S.npti_code = C.npti_code
            GROUP BY P.month_start
            ORDER BY P.month_start ASC;
        """)

        result4_3 = rows_to_dict(db.execute(sql4_3).fetchall())
        print('result4_3 (최근 6개월 성향 상세 - 0포함) 완료')

        time_now = datetime.now(timezone(timedelta(hours=9))).strftime('%Y-%m-%d %H:%M:%S')

        # =========================================================
        # 5. 최종 리턴 (JSON)
        # =========================================================
        return {
            "result1_npti_code": result1_1,
            "result1_age": result1_2,
            "result1_gender": result1_3,

            "result2_day": result2_1,
            "result2_week": result2_2,
            "result2_month": result2_3,

            "result3_npti_type": result3,

            "result4_day": result4_1,
            "result4_week": result4_2,
            "result4_month": result4_3,
            "time_now": time_now
        }

    except Exception as e:
        print(f"Error fetching statistics: {e}")
        return JSONResponse(status_code=500, content={"message": "통계 데이터를 불러오는 중 오류가 발생했습니다."})


@app.get("/articles_statistics")
def articles_statistics(db: Session = Depends(get_db)):
    try:
        today_str = datetime.now(timezone(timedelta(hours=9))).strftime('%Y-%m-%d')
        today = datetime.now(timezone(timedelta(hours=9)))
        this_monday = today - timedelta(days=today.weekday())
        this_monday_str = this_monday.strftime('%Y-%m-%d')
        this_month_start = today.replace(day=1)
        this_month_str = this_month_start.strftime('%Y-%m-%d')
        print(f'데이터 추출 시작')

        # [Helper 함수] DB 결과를 딕셔너리 리스트로 변환
        def rows_to_dict(result_proxy):
            return [dict(row._asdict()) for row in result_proxy]

        # [Helper 함수] 단일 행(1 row) 결과를 딕셔너리로 변환
        def row_to_dict(row):
            return dict(row._asdict()) if row else {}

        start_date = today - timedelta(days=6)
        start_date_str = start_date.strftime('%Y-%m-%d')
        TARGET_KEYS = ["정치", "경제", "사회", "생활/문화", "IT/과학", "세계", "스포츠", "연예", "지역"]

        # 1. category별 수집 기사 추이(es)
        # 1-1) 필드 : 일
        query1_1 = {
            "size": 0,
            "runtime_mappings": {
                "category_runtime": {
                    "type": "keyword",
                    "script": {
                        # _source에서 값을 꺼내와 임시 keyword 필드로 만듦
                        "source": "if (params['_source'].containsKey('category')) { emit(params['_source']['category'].toString()) }"
                    }
                }
            },
            "query": {
                "range": {
                    "pubdate": {
                        "gte": start_date_str,
                        "lte": today_str,
                        "format": "yyyy-MM-dd"
                    }
                }
            },
            "aggs": {
                "per_day": {
                    "date_histogram": {
                        "field": "pubdate",
                        "calendar_interval": "day",
                        "format": "yyyy-MM-dd",
                        "min_doc_count": 0,
                        "extended_bounds": {
                            "min": start_date_str,
                            "max": today_str
                        }
                    },
                    "aggs": {
                        "by_category": {
                            "terms": {
                                # 위에서 정의한 runtime 필드를 사용
                                "field": "category_runtime",
                                "size": 100,
                                "min_doc_count": 0
                            }
                        }
                    }
                }
            }
        }

        # 3. 검색 함수 실행
        response = search_news_condition(query1_1)

        # 4. [후처리] Grid 생성 (7일 x 16개 코드 = 0값 채우기)
        result1_1 = []

        if response:
            # ES 결과를 조회하기 편한 Map 형태로 변환
            # 구조: {'2026-01-08': {'ISTJ': 5}, ...}
            daily_buckets = response['aggregations']['per_day']['buckets']
            data_map = {}

            for day_bucket in daily_buckets:
                d_key = day_bucket['key_as_string']
                cat_map = {}
                for cat_bucket in day_bucket['by_category']['buckets']:
                    cat_map[cat_bucket['key']] = cat_bucket['doc_count']
                data_map[d_key] = cat_map

            # 7일 날짜 순회
            for i in range(7):
                # 6일 전부터 오늘까지 날짜 생성
                calc_date = today - timedelta(days=6 - i)
                date_key = calc_date.strftime('%Y-%m-%d')

                # 16개 코드 순회
                for key in TARGET_KEYS:
                    # 데이터가 있으면 count, 없으면 0
                    count = data_map.get(date_key, {}).get(key, 0)

                    result1_1.append({
                        "date_period": date_key,
                        "category": key,  # category 값을 npti_code로 매핑
                        "count": count
                    })

            # 결과 확인
            print('ES result (최근 7일 NPTI code별 집계 - 0포함) 완료')
        else:
            print("ES Search Failed")

        # 1-2) 필드 : 주
        week_npti_start_date = this_monday - timedelta(weeks=3)
        week_npti_start_str = week_npti_start_date.strftime('%Y-%m-%d')

        query1_2 = {
            "size": 0,
            "runtime_mappings": {
                "category_runtime": {
                    "type": "keyword",
                    "script": {
                        "source": "if (params['_source'].containsKey('category')) { emit(params['_source']['category'].toString()) }"
                    }
                }
            },
            "query": {
                "range": {
                    "pubdate": {
                        "gte": week_npti_start_str,
                        "lte": today_str,
                        "format": "yyyy-MM-dd"
                    }
                }
            },
            "aggs": {
                "per_week": {
                    "date_histogram": {
                        "field": "pubdate",
                        "calendar_interval": "week",
                        "format": "yyyy-MM-dd",
                        "min_doc_count": 0,
                        "extended_bounds": {
                            "min": week_npti_start_str,
                            "max": today_str
                        }
                    },
                    "aggs": {
                        "by_category": {
                            "terms": {
                                "field": "category_runtime",
                                "size": 100,
                                "min_doc_count": 0
                            }
                        }
                    }
                }
            }
        }

        # 4. 검색 실행
        # 변수명 변경: response -> es_resp_week_npti
        es_resp_week_npti = search_news_condition(query1_2)

        # 5. [후처리] Grid 생성
        # 변수명 변경: final_result -> result_week_npti_list
        result1_2 = []

        if es_resp_week_npti:
            # ES 결과 매핑용 딕셔너리
            # 변수명 충돌 방지를 위해 내부 변수도 유니크하게 사용
            week_buckets = es_resp_week_npti['aggregations']['per_week']['buckets']
            week_data_map = {}

            for _bucket in week_buckets:
                _d_key = _bucket['key_as_string']
                _cat_map = {}
                for _c_bucket in _bucket['by_category']['buckets']:
                    _cat_map[_c_bucket['key']] = _c_bucket['doc_count']
                week_data_map[_d_key] = _cat_map

            # 4주치 순회 (3주전 -> 2주전 -> 1주전 -> 이번주)
            for _i in range(3, -1, -1):
                _w_start = this_monday - timedelta(weeks=_i)
                _w_start_str = _w_start.strftime('%Y-%m-%d')
                _w_end = _w_start + timedelta(days=6)

                # 기간 문자열 생성
                _period_str = f"{_w_start_str}\n~ {_w_end.strftime('%Y-%m-%d')}"

                # 16개 코드 순회
                for _code in TARGET_KEYS:
                    # 안전하게 값 가져오기 (없으면 0)
                    _cnt = week_data_map.get(_w_start_str, {}).get(_code, 0)

                    result1_2.append({
                        "date_period": _period_str,
                        "category": _code,
                        "count": _cnt
                    })
            # 결과 확인
            print('result_week_npti_list (최근 4주 NPTI code별 집계 - 0포함) 완료')
        else:
            print("ES Search Failed (Week NPTI)")

        # 1-3) 필드 : 월
        _y, _m = this_month_start.year, this_month_start.month
        _m -= 5
        while _m <= 0:
            _y -= 1
            _m += 12
        month_npti_start_date = this_month_start.replace(year=_y, month=_m, day=1)
        month_npti_start_str = month_npti_start_date.strftime('%Y-%m-%d')
        month_bounds_str = month_npti_start_date.strftime('%Y-%m')
        today_bounds_str = today.strftime('%Y-%m')

        query1_3 = {
            "size": 0,
            "runtime_mappings": {
                "category_runtime": {
                    "type": "keyword",
                    "script": {
                        # _source에서 category 값을 꺼내 임시 keyword 필드로 변환
                        "source": "if (params['_source'].containsKey('category')) { emit(params['_source']['category'].toString()) }"
                    }
                }
            },
            "query": {
                "range": {
                    "pubdate": {
                        "gte": month_npti_start_str,
                        "lte": today_str,
                        "format": "yyyy-MM-dd"
                    }
                }
            },
            "aggs": {
                "per_month": {
                    "date_histogram": {
                        "field": "pubdate",
                        "calendar_interval": "month",
                        "format": "yyyy-MM",
                        "min_doc_count": 0,
                        # 6개월치 버킷 강제 생성
                        "extended_bounds": {
                            "min": month_bounds_str,
                            "max": today_bounds_str
                        }
                    },
                    "aggs": {
                        "by_category": {
                            "terms": {
                                "field": "category_runtime",
                                "size": 100,
                                "min_doc_count": 0
                            }
                        }
                    }
                }
            }
        }

        # 4. 검색 실행 (변수명 구분)
        es_resp_month_npti = search_news_condition(query1_3)

        # 5. [후처리] Grid 생성 (6개월 x 16개 코드 = 0값 채우기)
        result1_3 = []

        if es_resp_month_npti:
            # 5-1. ES 결과를 조회하기 편한 Map 형태로 변환
            _month_buckets = es_resp_month_npti['aggregations']['per_month']['buckets']
            _month_data_map = {}

            for _bucket in _month_buckets:
                _d_key = _bucket['key_as_string']  # "YYYY-MM" 형태
                _cat_map = {}
                for _c_bucket in _bucket['by_category']['buckets']:
                    _cat_map[_c_bucket['key']] = _c_bucket['doc_count']
                _month_data_map[_d_key] = _cat_map

            # 5-2. 6개월치 날짜 순회 (5달 전 ~ 이번 달)
            for _i in range(5, -1, -1):
                # 날짜 계산 (역순으로 월 빼기)
                _cy, _cm = this_month_start.year, this_month_start.month
                _cm -= _i
                while _cm <= 0:
                    _cy -= 1
                    _cm += 12
                _target_month_date = this_month_start.replace(year=_cy, month=_cm, day=1)
                _date_key = _target_month_date.strftime('%Y-%m')  # Key: YYYY-MM

                # 16개 코드 순회
                for _code in TARGET_KEYS:
                    # 안전하게 값 가져오기 (없으면 0)
                    _cnt = _month_data_map.get(_date_key, {}).get(_code, 0)

                    result1_3.append({
                        "date_period": _date_key,
                        "category": _code,
                        "count": _cnt
                    })
            # 결과 확인
            print('result_month_npti_list (최근 6개월 NPTI code별 집계 - 0포함) 완료')
        else:
            print("ES Search Failed (Month NPTI)")

        # 2. NPTI별 수집 기사 추이 - linear graph
        # 2-1) 필드 : 일
        sql2_1 = text(f"""
            WITH RECURSIVE Past7Days AS (
                -- 1. [타임라인] 최근 7일 날짜 생성
                SELECT '{today_str}' - INTERVAL 6 DAY AS date_period
                UNION ALL
                SELECT date_period + INTERVAL 1 DAY
                FROM Past7Days
                WHERE date_period < '{today_str}'
            ),
            AllNPTICodes AS (
                -- 2. [코드 목록] npti_code 테이블에서 모든 코드(16개) 가져오기
                SELECT npti_code FROM npti_code
            ),
            DateCodeGrid AS (
                -- 3. [그리드 생성] (7일) x (16개 코드) = 112개 행 생성
                -- 기사가 한 건도 없는 날이나 코드라도 이 뼈대는 무조건 존재함
                SELECT d.date_period, c.npti_code
                FROM Past7Days d
                CROSS JOIN AllNPTICodes c
            )
            SELECT 
                G.date_period,
                G.npti_code,
                -- 5. 실제 기사 데이터 카운트 (없으면 0)
                COUNT(A.news_id) as article_count
            FROM DateCodeGrid G
            LEFT JOIN articles_npti A
                -- 4. [데이터 매핑] 그리드에 실제 기사 조인
                ON G.npti_code = A.npti_code
                AND A.updated_at >= G.date_period 
                AND A.updated_at < G.date_period + INTERVAL 1 DAY
            GROUP BY G.date_period, G.npti_code
            ORDER BY G.date_period ASC, G.npti_code ASC;
        """)
        result2_1 = rows_to_dict(db.execute(sql2_1).fetchall())
        print('result_articles (최근 7일 기사 수집 현황 - 0포함) 완료')

        # 2-2) 필드 : 주
        # 1. 쿼리 작성
        sql_articles_week = text(f"""
            WITH RECURSIVE Past4Weeks AS (
                -- 1. [타임라인] 최근 4주(이번 주 포함)의 월요일 생성
                SELECT '{this_monday_str}' AS week_start
                UNION ALL
                SELECT week_start - INTERVAL 1 WEEK
                FROM Past4Weeks
                WHERE week_start > '{this_monday_str}' - INTERVAL 3 WEEK
            ),
            AllNPTICodes AS (
                -- 2. [코드 목록] 16개 NPTI 코드 가져오기
                SELECT npti_code FROM npti_code
            ),
            WeekCodeGrid AS (
                -- 3. [그리드 생성] (4주) x (16개 코드) = 64개 행
                -- 데이터 유무와 상관없이 무조건 존재하는 뼈대
                SELECT w.week_start, c.npti_code
                FROM Past4Weeks w
                CROSS JOIN AllNPTICodes c
            )
            SELECT 
                -- 날짜를 'YYYY-MM-DD ~ YYYY-MM-DD' 형태로 변환 (예: 2026-01-05 ~ 2026-01-11)
                CONCAT(G.week_start, '\n~ ', DATE_ADD(G.week_start, INTERVAL 6 DAY)) AS date_period,
    
                G.npti_code,
    
                -- 5. 실제 기사 매핑 카운트 (없으면 0)
                COUNT(A.news_id) as article_count
            FROM WeekCodeGrid G
            LEFT JOIN articles_npti A
                -- 4. [데이터 매핑] 해당 주차 기간 내에 수집된 기사 조인
                ON G.npti_code = A.npti_code
                AND A.updated_at >= G.week_start 
                AND A.updated_at < G.week_start + INTERVAL 1 WEEK
            GROUP BY G.week_start, G.npti_code
            ORDER BY G.week_start ASC, G.npti_code ASC;
        """)
        result2_2 = rows_to_dict(db.execute(sql_articles_week).fetchall())
        print('result_articles_week (최근 4주 기사 수집 현황 - 0포함) 완료')

        # 2-3) 필드 : 월
        # 1. 쿼리 작성
        sql2_3 = text(f"""
            WITH RECURSIVE Past6Months AS (
                -- 1. [타임라인] 최근 6개월(이번 달 포함) '매월 1일' 생성
                SELECT '{this_month_str}' AS month_start
                UNION ALL
                SELECT month_start - INTERVAL 1 MONTH
                FROM Past6Months
                WHERE month_start > '{this_month_str}' - INTERVAL 5 MONTH
            ),
            AllNPTICodes AS (
                -- 2. [코드 목록] 16개 NPTI 코드 가져오기
                SELECT npti_code FROM npti_code
            ),
            MonthCodeGrid AS (
                -- 3. [그리드 생성] (6개월) x (16개 코드) = 96개 행
                -- 데이터 유무와 상관없이 무조건 존재하는 뼈대
                SELECT m.month_start, c.npti_code
                FROM Past6Months m
                CROSS JOIN AllNPTICodes c
            )
            SELECT 
                -- 날짜를 'YYYY-MM' 형태로 변환 (예: 2025-08)
                DATE_FORMAT(G.month_start, '%Y-%m') AS date_period,
    
                G.npti_code,
    
                -- 5. 실제 기사 매핑 카운트 (없으면 0)
                COUNT(A.news_id) as article_count
            FROM MonthCodeGrid G
            LEFT JOIN articles_npti A
                -- 4. [데이터 매핑] 해당 월 기간 내에 수집된 기사 조인
                -- (해당 월 1일 0시 ~ 다음 달 1일 0시 전까지)
                ON G.npti_code = A.npti_code
                AND A.updated_at >= G.month_start 
                AND A.updated_at < G.month_start + INTERVAL 1 MONTH
            GROUP BY G.month_start, G.npti_code
            ORDER BY G.month_start ASC, G.npti_code ASC;
        """)
        result2_3 = rows_to_dict(db.execute(sql2_3).fetchall())
        print('result_articles_month (최근 6개월 기사 수집 현황 - 0포함) 완료')

        # 3. NPTI 기준별 수집 기사 추이 - bar chart
        # 3-1) 필드 : 일
        # 1. 쿼리 작성
        sql3_1 = text(f"""
            WITH RECURSIVE Past7Days AS (
                -- 1. [타임라인] 최근 7일 날짜 생성
                SELECT '{today_str}' - INTERVAL 6 DAY AS date_period
                UNION ALL
                SELECT date_period + INTERVAL 1 DAY
                FROM Past7Days
                WHERE date_period < '{today_str}'
            ),
            DailyArticles AS (
                -- 2. [데이터 매핑] 타임라인(P)을 기준으로 '해당 일'에 수집된 기사만 매핑
                -- (누적 아님: updated_at이 해당 일 00시 ~ 다음날 00시 전까지)
                SELECT 
                    P.date_period,
                    A.length_type,
                    A.article_type,
                    A.info_type,
                    A.view_type
                FROM Past7Days P
                LEFT JOIN articles_npti A
                    ON A.updated_at >= P.date_period 
                    AND A.updated_at < P.date_period + INTERVAL 1 DAY
            )
            SELECT 
                -- 날짜 그대로 출력 (YYYY-MM-DD)
                date_period,
    
                -- 3. 8가지 속성별 카운트 집계 (데이터가 없으면 0)
                COUNT(CASE WHEN length_type = 'L' THEN 1 END) AS L_count,
                COUNT(CASE WHEN length_type = 'S' THEN 1 END) AS S_count,
    
                COUNT(CASE WHEN article_type = 'C' THEN 1 END) AS C_count,
                COUNT(CASE WHEN article_type = 'T' THEN 1 END) AS T_count,
    
                COUNT(CASE WHEN info_type = 'I' THEN 1 END) AS I_count,
                COUNT(CASE WHEN info_type = 'F' THEN 1 END) AS F_count,
    
                COUNT(CASE WHEN view_type = 'P' THEN 1 END) AS P_count,
                COUNT(CASE WHEN view_type = 'N' THEN 1 END) AS N_count
    
            FROM DailyArticles
            GROUP BY date_period
            ORDER BY date_period ASC;
        """)
        result3_1 = rows_to_dict(db.execute(sql3_1).fetchall())
        print('result_articles_type_day (최근 7일 기사 성향 상세 - 0포함) 완료')


        # 3-2) 필드 : 주
        # 1. 쿼리 작성
        sql3_2 = text(f"""
            WITH RECURSIVE Past4Weeks AS (
                -- 1. [타임라인] 최근 4주(이번 주 포함)의 월요일 생성
                SELECT '{this_monday_str}' AS week_start
                UNION ALL
                SELECT week_start - INTERVAL 1 WEEK
                FROM Past4Weeks
                WHERE week_start > '{this_monday_str}' - INTERVAL 3 WEEK
            ),
            WeeklyArticles AS (
                -- 2. [데이터 매핑] 타임라인(P)을 기준으로 '해당 주'에 수집된 기사만 매핑
                -- (누적 아님: updated_at이 해당 주 월~일 범위 내에 있는 것만)
                SELECT 
                    P.week_start,
                    A.length_type,
                    A.article_type,
                    A.info_type,
                    A.view_type
                FROM Past4Weeks P
                LEFT JOIN articles_npti A
                    ON A.updated_at >= P.week_start 
                    AND A.updated_at < P.week_start + INTERVAL 1 WEEK
            )
            SELECT 
                -- 날짜를 'YYYY-MM-DD ~ YYYY-MM-DD' 형태로 변환 (예: 2026-01-05 ~ 2026-01-11)
                CONCAT(week_start, '\n~ ', DATE_ADD(week_start, INTERVAL 6 DAY)) AS date_period,
    
                -- 3. 8가지 속성별 카운트 집계 (데이터가 없으면 0)
                COUNT(CASE WHEN length_type = 'L' THEN 1 END) AS L_count,
                COUNT(CASE WHEN length_type = 'S' THEN 1 END) AS S_count,
    
                COUNT(CASE WHEN article_type = 'C' THEN 1 END) AS C_count,
                COUNT(CASE WHEN article_type = 'T' THEN 1 END) AS T_count,
    
                COUNT(CASE WHEN info_type = 'I' THEN 1 END) AS I_count,
                COUNT(CASE WHEN info_type = 'F' THEN 1 END) AS F_count,
    
                COUNT(CASE WHEN view_type = 'P' THEN 1 END) AS P_count,
                COUNT(CASE WHEN view_type = 'N' THEN 1 END) AS N_count
    
            FROM WeeklyArticles
            GROUP BY week_start
            ORDER BY week_start ASC;
        """)
        result3_2 = rows_to_dict(db.execute(sql3_2).fetchall())
        print('result_articles_type_week (최근 4주 기사 성향 상세 - 0포함) 완료')


        # 3-3) 필드 : 월
        sql3_3 = text(f"""
            WITH RECURSIVE Past6Months AS (
                -- 1. [타임라인] 최근 6개월(이번 달 포함) '매월 1일' 생성
                SELECT '{this_month_str}' AS month_start
                UNION ALL
                SELECT month_start - INTERVAL 1 MONTH
                FROM Past6Months
                WHERE month_start > '{this_month_str}' - INTERVAL 5 MONTH
            ),
            MonthlyArticles AS (
                -- 2. [데이터 매핑] 타임라인(P)을 기준으로 해당 월에 작성된 기사(A)를 붙임
                SELECT 
                    P.month_start,
                    A.length_type,
                    A.article_type,
                    A.info_type,
                    A.view_type
                FROM Past6Months P
                LEFT JOIN articles_npti A
                    ON A.updated_at >= P.month_start 
                    AND A.updated_at < P.month_start + INTERVAL 1 MONTH
            )
            SELECT 
                -- 날짜를 'YYYY-MM' 형태로 변환
                DATE_FORMAT(month_start, '%Y-%m') AS date_period,
    
                -- 3. 8가지 속성별 카운트 집계 (데이터 없으면 0)
                COUNT(CASE WHEN length_type = 'L' THEN 1 END) AS L_count,
                COUNT(CASE WHEN length_type = 'S' THEN 1 END) AS S_count,
    
                COUNT(CASE WHEN article_type = 'C' THEN 1 END) AS C_count,
                COUNT(CASE WHEN article_type = 'T' THEN 1 END) AS T_count,
    
                COUNT(CASE WHEN info_type = 'I' THEN 1 END) AS I_count,
                COUNT(CASE WHEN info_type = 'F' THEN 1 END) AS F_count,
    
                COUNT(CASE WHEN view_type = 'P' THEN 1 END) AS P_count,
                COUNT(CASE WHEN view_type = 'N' THEN 1 END) AS N_count
    
            FROM MonthlyArticles
            GROUP BY month_start
            ORDER BY month_start ASC;
        """)
        result3_3 = rows_to_dict(db.execute(sql3_3).fetchall())
        print('result_articles_type_month (최근 6개월 기사 성향 상세 - 0포함) 완료')
        time_now = datetime.now(timezone(timedelta(hours=9))).strftime('%Y-%m-%d %H:%M:%S')

        return {
            "result1_day": result1_1,
            "result1_week": result1_2,
            "result1_month": result1_3,

            "result2_day": result2_1,
            "result2_week": result2_2,
            "result2_month": result2_3,

            "result3_day": result3_1,
            "result3_week": result3_2,
            "result3_month": result3_3,
            "time_now": time_now
        }
    except Exception as e:
        print(f'Error 발생 : {e}')
        return JSONResponse(status_code=500, content = {"msg":"기사 통계 데이터 로드 중 오류가 발생했습니다."})