import time
import random
import hashlib
import traceback

import requests
from bs4 import BeautifulSoup
from fastapi import FastAPI
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from elasticsearch import Elasticsearch
from elasticsearch import NotFoundError
import re


from elasticsearch_index.es_err_crawling import index_error_log
from logger import Logger
from datetime import datetime, timezone, timedelta
from kiwipiepy import Kiwi
from elasticsearch_index.es_raw import tokens, ensure_news_raw, ES_INDEX
import asyncio


app = FastAPI()
logger = Logger().get_logger(__name__)


# ---------- [설정] 엘라스틱서치 연결 ----------
# 엘라스틱서치 서버 주소 및 인덱스 이름 설정
ES_HOST = "http://localhost:9200"
ES_INDEX = "news_raw"
ES_USER = "elastic"
ES_PASS = "elastic"
es = Elasticsearch( # elasticsearch 연결 객체 생성
    ES_HOST,
    basic_auth=(ES_USER, ES_PASS),
    verify_certs=False,
    ssl_show_warn=False # type: ignore
)


# ---------- [설정] Selenium 드라이버 초기화 함수 ----------
def get_safe_driver():
    try:
        chrome_options = Options()
        # 1. 자동화 탐지 방지 설정 # '이 브라우저는 자동화 소프트웨어에 의해 제어되고 있습니다' 문구 제거
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        # 2. 실제 브라우저처럼 보이게 헤더 설정
        chrome_options.add_argument(
            "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36")
        chrome_options.add_argument("--window-size=1920,1080")  # 창 크기 고정
        # 3. 리소스 절약을 위해 headless 모드 권장 (필요시 주석 해제)
        # chrome_options.add_argument("--headless")

        # webdriver 속성을 undefined로 만들어 탐지 방지
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        })
        return driver
    except Exception as e:
        error_msg = f"Selenium 드라이버 초기화 실패:{e}"
        logger.error(error_msg)
        logger.error(traceback.format_exc())
        index_error_log(error_msg, "NAVER")
        return None


# ---------- 중복 확인 함수 (엘라스틱서치 조회) ----------
def id_dupl(news_id):
    try:
        if not es.ping():
            logger.error("ES 서버 연결 끊김")
            return True  # 안전을 위해 중복으로 간주하여 저장 시도 방지
        return es.exists(index=ES_INDEX, id=news_id)
    except Exception as e:
        error_msg = f"ES PK 중복 확인 중 에러 발생 (ID: {news_id}): {e}"
        logger.error(error_msg)
        index_error_log(error_msg, "NAVER")
        return False


################################################################################################################
# ---------- 기사 상세 feature 가지고 오기(본문,원문URL,언론사,발행일,발행시간,카테고리,기자,이미지URL,이미지캡션) ----------
def get_article_detail(url, category_name):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()  # 404, 500 에러 체크
        soup = BeautifulSoup(response.text, "lxml")

        # 6. URL(기사 원문)
        origin_link = soup.select_one("a.media_end_head_origin_link")
        URL = origin_link.get("href") if origin_link else None

        # 1. 본문
        content_area = soup.select_one("article#dic_area")
        if not content_area: return None

        # 1-1. 첫 번째 이미지 및 캡션 추출 (제거하기 전에 미리 저장)
        imgURL = None
        imgCap = None
        first_photo = content_area.select_one("span.end_photo_org")
        if first_photo:
            img_tag = first_photo.select_one("#img1")
            cap_tag = first_photo.select_one("em.img_desc")
            if img_tag:
                imgURL = img_tag.get("src") or img_tag.get("data-src")
            if cap_tag:
                imgCap = cap_tag.get_text(strip=True)

        # 1-2. 본문 정제 (광고, 캡션, 이미지, 표 등 불필요한 요소 통째로 삭제)
        for junk in content_area.select("table, .link_tagger, .script_tag, span.end_photo_org, div.ad_body_res"):
            junk.decompose()

        # 1-3. 순수 텍스트만 추출
        content = content_area.get_text("\n", strip=True)

        # 2. 발행일자(pubdate/pubtime 분리)
        date_tag = soup.select_one("span.media_end_head_info_datestamp_time")

        pubdate = None
        pubtime = None

        if date_tag:
            text_date = date_tag.get_text(strip=True)
            # 예: "2025.12.19. 오전 10:16"

            # 날짜 추출

            date_match = re.search(r"(\d{4})\.(\d{1,2})\.(\d{1,2})", text_date)
            if date_match:
                y, m, d = date_match.groups()
                pubdate = f"{y}-{m.zfill(2)}-{d.zfill(2)}"

            # 시간 추출
            time_match = re.search(r"(오전|오후)\s*(\d{1,2}):(\d{2})(?::(\d{2}))?", text_date)
            if time_match:
                ampm, h, m, *_ = time_match.groups()
                h = int(h)
                if ampm == "오후" and h != 12:
                    h += 12
                if ampm == "오전" and h == 12:
                    h = 0
                pubtime = f"{str(h).zfill(2)}:{m}"

        # 3. 기자명
        writer_tag = soup.select_one("span.byline_s") or soup.select_one("em.media_end_head_journalist_name")
        writer = writer_tag.get_text(strip=True).replace("기자","").strip() if writer_tag else None

        # 4. 카테고리
        category_tag = soup.select_one("em.media_end_categorize_item") or soup.select_one("a._current")
        category = category_tag.get_text(strip=True) if category_tag else category_name
        if "생활/문화" in category_name:
            category = "생활/문화"

        # 5. 언론사
        media = None
        media_tag = soup.select_one("span.media_end_head_top_logo_text") or soup.select_one(
            "img.media_end_head_top_logo_img")
        if media_tag:
            # img 태그면 alt를, 아니면 text를 가져옴
            media = media_tag.get("alt") if media_tag.name == "img" else media_tag.get_text(strip=True)

        return {
            "content": content.strip(),
            "URL": URL,
            "media": media,
            "pubdate": pubdate,
            "pubtime": pubtime,
            "writer": writer,
            "imgURL": imgURL,
            "imgCap": imgCap,
            "category": category
        }
    except Exception as e:
        error_msg =f"일반기사 상세 수집 실패 ({url}): {e}"
        logger.error(error_msg)
        index_error_log(error_msg, "NAVER")
        return None


################################################################################################################
# ---------- [스포츠/연예]기사 상세 feature 가지고 오기(본문,원문URL,언론사,발행일,발행시간,카테고리,기자,이미지URL,이미지캡션) ----------
def get_sports_article_detail(url, category_name):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36'}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, "lxml")

        # 동영상 영역 존재 여부 확인
        video_element = soup.select_one("div.video_area, div[id^='video_area_']")
        if video_element:
            logger.info(f"[NAVER SKIP] 동영상이 포함된 기사입니다: {url}")
            return None

        # 본문
        content_area = soup.select_one("#comp_news_article ._article_content")
        if not content_area: return None

        # 첫 번째 이미지 및 캡션 추출
        imgURL = None
        imgCap = None
        img_wrap = soup.select_one("span[class*='ArticleImage_image_wrap']")
        if img_wrap:
            img_tag = img_wrap.select_one("img")
            if img_tag: imgURL = img_tag.get("src")
            cap_tag = img_wrap.find_next(["em", "p"], class_=lambda x: x and ("img_desc" in x or "caption" in x))
            if cap_tag: imgCap = cap_tag.get_text(strip=True)

        # 2. 본문 정제
        for junk in content_area.select("div[class*='ArticleImage_image_wrap'], em.img_desc, p.caption, div.ad_area"):
            junk.decompose()

        content = content_area.get_text("\n", strip=True)

        # 원문 URL
        origin_link = soup.select_one("#content a[class*='DateInfo_link_origin_article']")
        URL = origin_link.get("href") if origin_link else None

        # 언론사
        media = ""
        media_tag = soup.select_one("a.link_media img, #content a[class*='PressLogo'] img")
        if media_tag:
            media = media_tag.get("alt", "").strip()

        if not media:
            media_text_tag = soup.select_one("em[class*='JournalistCard_press_name']")
            if media_text_tag:
                media = media_text_tag.get_text(strip=True)

        # 날짜 추출
        date_tag = soup.select_one("em.date")
        pubdate = None
        pubtime = None

        if date_tag:
            text_date = date_tag.get_text(strip=True)
            # 예: "2025.12.19. 오전 10:16"

            # 날짜 추출
            date_match = re.search(r"(\d{4})\.(\d{1,2})\.(\d{1,2})", text_date)
            if date_match:
                y, m, d = date_match.groups()
                pubdate = f"{y}-{m.zfill(2)}-{d.zfill(2)}"

            # 시간 추출
            time_match = re.search(r"(오전|오후)\s*(\d{1,2}):(\d{2})(?::(\d{2}))?", text_date)
            if time_match:
                ampm, h, m, *_ = time_match.groups()
                h = int(h)
                if ampm == "오후" and h != 12:
                    h += 12
                if ampm == "오전" and h == 12:
                    h = 0
                pubtime = f"{str(h).zfill(2)}:{m}"

        # 기자명 추출
        writer_tag = soup.select_one("em[class*='JournalistCard_name']")
        if writer_tag:
            writer = writer_tag.get_text(strip=True).replace("기자", "").strip()
        else:
            writer = ""  # None 대신 빈 문자열 할당

        return {
            "content": content,
            "URL": URL,
            "media": media,
            "pubdate": pubdate,
            "pubtime": pubtime,
            "writer": writer,
            "imgURL": imgURL,
            "imgCap": imgCap,
            "category": "스포츠"
        }
    except Exception as e:
        error_msg =f"스포츠 기사 상세 수집 실패 ({url}): {e}"
        logger.error(error_msg)
        index_error_log(error_msg, "NAVER")
        return None

################################################################################################################
# pubdate 업데이트 확인 함수
def pubtime_update(news_id):
    try:
        res = es.get(index=ES_INDEX, id=news_id)
        source = res.get('_source', {})
        if not source.get('pubtime'):
            return "UPDATE_NEEDED"
        return "ALREADY_EXISTS"
    except NotFoundError:
        return "NEW_DOC"
    except Exception as e:
        # 401(인증), 500(서버에러) 등 실제 에러만 기록
        logger.error(f"B->N pubtime_update 중 실제 장애 발생: {e}")
        return "NEW_DOC"

################################################################################################################
# Semaphore(접속 수 제한:3)
#sem = asyncio.Semaphore(3)

async def process_article(item, cat_name, kiwi, sem):
    async with sem:
        try:
            link_tag = item.select_one("a")
            title_tag = item.select_one("strong")

            if not title_tag: return
            title = title_tag.get_text(strip=True)

            if not link_tag: return
            naver_url = link_tag.get("href")
            if naver_url.startswith("/"): naver_url = f"https://news.naver.com{naver_url}"

            # 상세 페이지 접근
            detail = await asyncio.to_thread(get_article_detail, naver_url, cat_name)

            if not detail or not detail.get("URL"): return

            # PK(news_id) 생성 및 중복 확인
            news_id = hashlib.sha256(detail["URL"].encode()).hexdigest()
            # id_dupl도 ES 조회(네트워크)이므로 스레드에서 실행
            status = await asyncio.to_thread(pubtime_update, news_id)

            if status == "ALREADY_EXISTS":
                return

            content = detail.get("content")
            if not content: return

            token = tokens({"title": title, "content": content}, kiwi)

            doc = {
                "news_id": news_id,
                "tag": "breaking" if "[속보]" in title else "normal",
                "title": title.replace("[속보]", "").replace('\\', '').strip(),
                "title_tokens": token["title_tokens"],
                "content": content,
                "content_tokens": token["content_tokens"],
                "link": detail.get("URL"),
                "media": (detail.get("media") or "").replace('\\', ''),
                "pubdate": detail.get("pubdate"),
                "pubtime": detail.get("pubtime"),
                "category": detail.get("category"),
                "writer": (detail.get("writer") or "").replace('\\', ''),
                "img": detail.get("imgURL"),
                "imgCap": detail.get("imgCap"),
                "timestamp": datetime.now(timezone(timedelta(hours=9))).isoformat(timespec='seconds'),
                "classified": False
            }

            # 엘라스틱서치 저장
            await asyncio.to_thread(es.index, index=ES_INDEX, id=news_id, document=doc)

            # status가 "NEW_DOC"(신규)이거나 "UPDATE_NEEDED"(pubtime 보완)인 경우 진행
            if status == "UPDATE_NEEDED":
                logger.info(f"Big->Naver(pubtime 보완): {title[:15]}")
            # 너무 빠르지 않게 미세한 대기
            await asyncio.sleep(random.uniform(0.3, 0.7))
            return True

        except Exception as e:
            error_msg =f"비동기 기사 처리 중 에러: {e}"
            logger.error(error_msg)
            index_error_log(error_msg, "NAVER")
            return False

################################################################################################################
# 전체 크롤링 함수
def crawler_naver():
    logger.info("=====NAVER 크롤링 프로세스 시작=====")

    # ES 인덱스 생성
    try:
        ensure_news_raw()
    except Exception as e:
        error_msg =f"ES 인덱스 초기화 실패 (ensure_news_raw): {e}"
        logger.error(error_msg)
        index_error_log(error_msg, "NAVER")
        return
    #run_fast_crawl() #서버시작시 시작

def run_fast_crawl():
    driver = get_safe_driver()
    if not driver:
        logger.error("드라이버 로드 실패로 FAST 크롤링 중단")
        return

    try:
        fast_categories = {
            "정치": "100", "경제": "101",
            "사회": "102", "세계": "104"
        }
        logger.info("==========[FAST] 정경사세 수집 시작==========")
        crawling_general_news(driver, fast_categories)

    except Exception as e:
        logger.error(traceback.format_exc())
        index_error_log(f"FAST 크롤링 에러: {e}", "NAVER")

    finally:
        driver.quit()

def run_slow_crawl():
    driver = get_safe_driver()
    if not driver:
        logger.error("드라이버 로드 실패로 SLOW 크롤링 중단")
        return

    try:
        logger.info("==========[SLOW] 30분 주기 수집 시작==========")

        slow_categories = {"생활/문화(건강)": "103/241","생활/문화(자동차)": "103/239","생활/문화(도로)": "103/240",
                           "생활/문화(여행)": "103/237","생활/문화(음식)": "103/238","생활/문화(패션)": "103/376",
                           "생활/문화(공연)": "103/242","생활/문화(책)": "103/243","생활/문화(종교)": "103/244",
                           "생활/문화(일반)": "103/245","IT/과학": "105"}
        crawling_general_news(driver, slow_categories)
        crawling_sports_news(driver)
        crawling_enter_news(driver)

    except Exception as e:
        logger.error(traceback.format_exc())
        index_error_log(f"SLOW 크롤링 에러: {e}", "NAVER")

    finally:
        driver.quit()

################################################################################################################
# 일반기사 크롤링 함수
def crawling_general_news(driver, categories):
    kiwi = Kiwi()
    # categories = {
    # "정치": "100", "경제": "101", "사회": "102", "세계": "104", "IT/과학": "105",
    # "생활/문화(건강)": "103/241","생활/문화(자동차)": "103/239","생활/문화(도로)": "103/240","생활/문화(여행)": "103/237","생활/문화(음식)": "103/238",
    # "생활/문화(패션)": "103/376","생활/문화(공연)": "103/242","생활/문화(책)": "103/243","생활/문화(종교)": "103/244","생활/문화(일반)": "103/245"
    # }

    for cat_name, cat_id in categories.items():
        start_time = time.time()

        try:
            if "/" in cat_id:
                url = f"https://news.naver.com/breakingnews/section/{cat_id}"
            else:
                url = f"https://news.naver.com/section/{cat_id}"
            logger.info(f"======[일반/{cat_name}] 수집 시작======")
            driver.get(url)

            # 더보기 클릭 (2회)
            for i in range(2):
                try:
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(random.uniform(1.0, 1.5))
                    more_btn_xpath = "//a[contains(@class, 'section_more_inner') or contains(text(), '더보기')]"
                    more_btn = WebDriverWait(driver, 7).until(
                        EC.presence_of_element_located((By.XPATH, more_btn_xpath))
                    )
                    driver.execute_script("arguments[0].scrollIntoView(true);", more_btn)
                    time.sleep(random.uniform(1.5, 2.5))

                    driver.execute_script("arguments[0].click();", more_btn)

                    logger.info(f"[{cat_name}] 더보기 버튼 클릭 성공 ({i + 1}/2)")
                    time.sleep(random.uniform(2.0, 3.0))
                except:
                    logger.debug(f"[{cat_name}] 더보기 버튼 없음/종료")
                    break

            soup = BeautifulSoup(driver.page_source, "lxml")
            items = soup.select("div.section_latest ul li")

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            sem = asyncio.Semaphore(3)

            tasks = [process_article(item, cat_name, kiwi, sem) for item in items]
            results = loop.run_until_complete(asyncio.gather(*tasks))
            loop.close()

            end_time = time.time()
            duration = end_time - start_time
            saved_count = len([r for r in results if r is True])
            logger.info(f"[카테고리 - {cat_name}] 수집: 신규 기사: {saved_count}건 / {duration:.2f}초 소요 ")

        except Exception as e:
            error_msg =f"crawling_general_news - [{cat_name}] 카테고리 수집 중 에러: {e}"
            logger.error(error_msg)
            index_error_log(error_msg, "NAVER")
            continue

        # 다음 카테고리로 넘어가기 전 대기(IP 차단 방지)
        time.sleep(random.uniform(2.0, 5.0))

    logger.info("일반기사 수집 프로세스 종료")

################################################################################################################
# 스포츠기사 크롤링 함수
def crawling_sports_news(driver):
    kiwi = Kiwi()
    sports_categories = {
        "국내야구": "kbaseball","해외야구": "wbaseball","국내축구": "kfootball","해외축구": "wfootball",
        "농구": "basketball","배구": "volleyball","일반": "general","골프": "golf"
        }

    for s_name, s_id in sports_categories.items():
        start_time = time.time()
        saved_count = 0
        duplicate_count = 0
        stop_current_category = False

        try:
            url = f"https://m.sports.naver.com/{s_id}/news"
            logger.info(f"======[스포츠/{s_name}] 수집 시작======")
            driver.get(url)
            time.sleep(random.uniform(2.5, 3.5))

            for page_num in range(1, 4):
                if stop_current_category:
                    break

                try:
                    # 페이지 하단으로 스크롤
                    for i in range(3):
                        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                        time.sleep(1.0)
                    logger.info(f"[스포츠/{s_name}] {page_num}페이지 데이터 및 버튼 로드 중")
                    time.sleep(1.5)

                    if page_num > 1:
                        page_btn_xpath = f"//div[contains(@class, 'Pagination_pagination')]//button[text()='{page_num}']"
                        try:
                            page_button = WebDriverWait(driver, 10).until(
                                    EC.element_to_be_clickable((By.XPATH, page_btn_xpath))
                                )
                            driver.execute_script("arguments[0].scrollIntoView(true);", page_button)
                            time.sleep(0.5)
                            driver.execute_script("arguments[0].click();", page_button)
                            logger.info(f"[{s_name}] {page_num}페이지로 이동 중")
                            time.sleep(random.uniform(2.0, 3.0))

                            # 페이지 이동 후 스크롤
                            driver.execute_script("window.scrollTo(0, 0);")
                            time.sleep(1.0)
                            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                            time.sleep(1.5)

                        except Exception as e:
                            error_msg =f"[{s_name}] {page_num}페이지 버튼 클릭 실패: {e}"
                            logger.error(error_msg)
                            index_error_log(error_msg, "NAVER")
                            break  # 다음 페이지 버튼을 못 찾으면 해당 종목 종료
                except Exception as e:
                    error_msg =f"[스포츠/{s_name}] {page_num} 이동 중 에러: {e}"
                    logger.error(error_msg)
                    index_error_log(error_msg, "NAVER")
                    break

                soup = BeautifulSoup(driver.page_source, "lxml")
                items = soup.select("ul[class*='NewsList_news_list'] li")
                if not items: break

                for item in items:
                    link_tag = item.select_one("a") or item.select_one("a.link_news")
                    title_tag = item.select_one("em[class*='NewsItem_title']") or item.select_one("strong")

                    if not title_tag or not link_tag:
                        continue

                    title = title_tag.get_text(strip=True)
                    naver_url = link_tag.get("href")

                    if naver_url.startswith("/"):
                        naver_url = f"https://m.sports.naver.com{naver_url}"
                    elif not naver_url.startswith("http"):
                        continue

                    # 상세 페이지 접근
                    detail = get_sports_article_detail(naver_url, f"스포츠/{s_name}")

                    if not detail:
                        logger.info(f"[NAVER SKIP] 상세 페이지 접속 실패: {naver_url}")
                        continue

                    news_id = hashlib.sha256(detail["URL"].encode()).hexdigest()
                    if id_dupl(news_id):
                        duplicate_count += 1
                        if duplicate_count >= 5:
                            logger.info(f"[{s_name}] 5회 연속 중복 발생. 해당 종목 종료.")
                            stop_current_category = True
                            break
                        continue
                    duplicate_count = 0

                    required_fields = {
                        "content": detail.get("content"),
                        "media": detail.get("media"),
                        "URL": detail.get("URL")
                        }

                    # 하나라도 없으면 건너뜀
                    if not all(required_fields.values()):
                        missing_names = [k for k, v in required_fields.items() if not v]
                        logger.warning(f"[NAVER SKIP] 필수 정보 누락({', '.join(missing_names)}): {naver_url}")
                        continue


                    token = tokens({"title": title, "content": detail.get("content")}, kiwi)

                    doc = {
                        "news_id": news_id,
                        "tag": "breaking" if "[속보]" in title else "normal",
                        "title": title.replace("[속보]", "").replace('\\', '').strip(),
                        "title_tokens": token["title_tokens"],
                        "content": detail.get("content", ""),
                        "content_tokens": token["content_tokens"],
                        "writer": (detail.get("writer") or "").replace('\\', ''),
                        "media": (detail.get("media") or "").replace('\\', ''),
                        "pubdate": detail.get("pubdate"),
                        "pubtime": detail.get("pubtime"),
                        "category": "스포츠",
                        "img": detail.get("imgURL"),
                        "imgCap": detail.get("imgCap"),
                        "link": detail.get("URL"),
                        "timestamp": datetime.now(timezone(timedelta(hours=9))).isoformat(timespec='seconds'),
                        "classified": False
                    }
                    es.index(index=ES_INDEX, id=news_id, document=doc)
                    saved_count += 1
                    time.sleep(random.uniform(0.5, 1.0))

            duration = time.time() - start_time
            logger.info(f"[스포츠/{s_name}] 완료 : {saved_count}건 / {duration:.2f}초 소요")
            time.sleep(random.uniform(0.8, 1.5))

        except Exception as e:
            error_msg =f"crawling_sports_news - 스포츠/{s_name} 수집 중 에러: {e}"
            logger.error(error_msg)
            index_error_log(error_msg, "NAVER")
            continue

    logger.info("스포츠 기사 수집 프로세스 종료")


################################################################################################################
# 연예 기사 크롤링 함수
def crawling_enter_news(driver):
    kiwi = Kiwi()
    start_time = time.time()
    saved_count = 0
    duplicate_count = 0
    stop_process = False

    try:
        url = "https://m.entertain.naver.com/now"
        logger.info("[======[연예] 수집 시작======")
        driver.get(url)
        time.sleep(random.uniform(2.5, 3.5))

        for page_num in range(1, 4):
            if stop_process: break

            try:
                for i in range(3):
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                logger.info(f"[연예] {page_num}페이지 로드 중({i}/3)")
                time.sleep(2.0)

                if page_num > 1:
                    page_btn_xpath = f"//div[contains(@class, 'Pagination_pagination')]//button[text()='{page_num}']"

                    try:
                        page_button = WebDriverWait(driver, 10).until(
                            EC.element_to_be_clickable((By.XPATH, page_btn_xpath))
                        )
                        # 일반 클릭이 안 될 경우를 대비해 스크립트 실행 방식으로 클릭
                        driver.execute_script("arguments[0].click();", page_button)
                        logger.info(f"[연예] {page_num}페이지로 이동 중")
                        time.sleep(random.uniform(2.5, 3.5))

                        # 페이지 이동 후 스크롤
                        driver.execute_script("window.scrollTo(0, 0);")
                        time.sleep(1.0)
                        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                        time.sleep(1.5)

                    except Exception as e:
                        error_msg =f"[연예] {page_num}페이지 버튼 찾기 실패: {e}"
                        logger.error(error_msg)
                        index_error_log(error_msg, "NAVER")
                        break

                soup = BeautifulSoup(driver.page_source, "lxml")
                items = soup.select("ul[class*='NewsList_news_list'] li")
                if not items:
                    #logger.info(f"[연예] {page_num}페이지에 기사 없음")
                    break

                for item in items:
                    link_tag = item.select_one("a[class*='NewsItem_link_news']") or item.select_one("a")
                    title_tag = item.select_one("em[class*='NewsItem_title']") or item.select_one("strong")

                    if not title_tag or not link_tag:
                        continue

                    title = title_tag.get_text(strip=True)
                    naver_url = link_tag.get("href")

                    if naver_url.startswith("/"):
                        naver_url = f"https://m.entertain.naver.com{naver_url}"
                    elif not naver_url.startswith("http"):
                        continue

                    # 상세 페이지 접근
                    detail = get_sports_article_detail(naver_url, "연예")

                    if not detail:
                        logger.warning(f"[NAVER SKIP] 상세 페이지 접속 실패: {naver_url}")
                        continue

                    news_id = hashlib.sha256(detail["URL"].encode()).hexdigest()
                    if id_dupl(news_id):
                        duplicate_count += 1
                        if duplicate_count >= 5:
                            logger.info("[연예] 5회 연속 중복 발생. 수집 종료.")
                            stop_process = True
                            break
                        continue
                    duplicate_count = 0

                    # 필수 필드 체크
                    required_fields = {
                        "본문": detail.get("content"),
                        "언론사": detail.get("media"),
                        "원문URL": detail.get("URL")
                    }

                    if not all(required_fields.values()):
                        missing_names = [k for k, v in required_fields.items() if not v]
                        logger.warning(f"[NAVER SKIP] 필수 정보 누락({', '.join(missing_names)}): {naver_url}")
                        continue


                    token = tokens({"title": title, "content": detail.get("content")}, kiwi)

                    doc = {
                        "news_id": news_id,
                        "tag": "breaking" if "[속보]" in title else "normal",
                        "title": title.replace("[속보]", "").replace('\\', '').strip(),
                        "title_tokens": token["title_tokens"],
                        "content": detail.get("content", ""),
                        "content_tokens": token["content_tokens"],
                        "writer": (detail.get("writer") or "").replace('\\', ''),
                        "media": (detail.get("media") or "").replace('\\', ''),
                        "pubdate": detail.get("pubdate"),
                        "pubtime": detail.get("pubtime"),
                        "category": "연예",
                        "img": detail.get("imgURL"),
                        "imgCap": detail.get("imgCap"),
                        "link": detail.get("URL"),
                        "timestamp": datetime.now(timezone(timedelta(hours=9))).isoformat(timespec='seconds'),
                        "classified": False
                    }

                    # ES 저장
                    es.index(index=ES_INDEX, id=news_id, document=doc)
                    saved_count += 1
                    time.sleep(random.uniform(0.8, 1.2))

                logger.info(f"[연예] {page_num}페이지 완료 (누적 {saved_count}건)")

            except Exception as e:
                error_msg =f"[연예] {page_num}페이지 수집 중 에러: {e}"
                logger.error(error_msg)
                index_error_log(error_msg, "NAVER")
                continue

        duration = time.time() - start_time
        logger.info(f"[연예 뉴스] 전체 완료 : {saved_count}건 / {duration:.2f}초 소요")

    except Exception as e:
        error_msg =f"crawling_enter_news - 수집 중 에러: {e}"
        logger.error(error_msg)
        index_error_log(error_msg, "NAVER")

    logger.info("연예 기사 수집 프로세스 종료")



# 수동 크롤링 실행용
if __name__ == "__main__":
    crawler_naver()
