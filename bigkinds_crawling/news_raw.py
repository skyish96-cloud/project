import hashlib
import pandas as pd
import time
from selenium import webdriver
from selenium.webdriver.chromium.options import ChromiumOptions
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as ec
from kiwipiepy import Kiwi
from typing import Optional
from elasticsearch_index.es_raw import es, ES_INDEX
from datetime import datetime, timezone
from logger import Logger
from elasticsearch_index.es_raw import (
    ensure_news_raw, index_sample_row, search_news_row, tokens
)
from elasticsearch_index.es_err_crawling import index_error_log
from sklearn.feature_extraction.text import TfidfVectorizer
from elasticsearch import helpers

logger = Logger().get_logger(__name__)

# 셀레니움 옵션 설정
options = ChromiumOptions()
options.add_argument('--remote-allow-origins=*')
options.add_argument('--start-maximized')

############################################################################### 각 컬럼 값 크롤링하기 전에 초기화
def news_crawling(max_pages: int):
    ensure_news_raw()
    service = Service()
    driver = webdriver.Chrome(service=service, options=options)
    driver.get('https://www.bigkinds.or.kr/v2/news/recentNews.do')
    wait = WebDriverWait(driver, 30)
    kiwi = Kiwi()

    total_samples = []
    page = 1

    try:
        while page <= max_pages:
            sample = []
            wait.until(ec.presence_of_element_located((By.CSS_SELECTOR, "#news-results")))
            wait.until(ec.presence_of_all_elements_located((By.CSS_SELECTOR, "#news-results div.news-item")))
            news_items = driver.find_elements(By.CSS_SELECTOR, "#news-results div.news-item")

            logger.info(f'bigkinds {page}페이지 {len(news_items)}개 시작')

            for i, news_item in enumerate(news_items):
                logger.info(f'bigkinds {page} 페이지 {i+1}번째 기사')
                try:
                    # 모달 초기화 스크립트 실행
                    driver.execute_script("""
                        jQuery('.modal').modal('hide');
                        document.querySelectorAll('.modal.show, #news-detail-modal').forEach(m => m.remove());
                        document.querySelectorAll('.modal-backdrop').forEach(b => b.remove());
                        jQuery('body').removeClass('modal-open');
                    """)
                    time.sleep(1)

                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", news_item)
                    time.sleep(1)

                    # link 및 news_id 추출
                    link_elem = news_item.find_elements(By.CSS_SELECTOR, "div.info a")
                    if len(link_elem) > 0:
                        link = link_elem[0].get_attribute("href")
                        news_id = hashlib.sha256(link.split('//', 1)[1].encode()).hexdigest()
                    else:
                        logger.info(f"bigkinds 원문 링크(news_id)없음 - 스킵")
                        continue

                    if search_news_row(news_id):
                        continue

                    # 데이터 파싱 로직 (기존과 동일)
                    title_elem = news_item.find_element(By.CSS_SELECTOR, "div.cont.news-detail strong.title")
                    title = title_elem.text.strip()
                    tag = "속보" if title.startswith("[속보]") else "일반"
                    if tag == "속보": title = title[4:].strip()

                    media_elem = news_item.find_element(By.CSS_SELECTOR, "div.info div > *:not(span.bullet-keyword)")
                    media = media_elem.text.strip()

                    category_elem = news_item.find_element(By.CSS_SELECTOR, "div.info span.bullet-keyword")
                    category_text = category_elem.text.strip()
                    if category_text == '미분류' or '날씨' in category_text:
                        logger.info(f"bigkinds {category_text} - 스킵")
                        continue

                    category = category_text.split('>')[0].strip()
                    category_mapping = {'국제': '세계', '문화': '생활/문화', 'IT_과학': 'IT/과학'}
                    category = category_mapping.get(category, category)

                    writer_elem = news_item.find_element(By.CSS_SELECTOR, "div.info p.name")
                    writer = writer_elem.text.strip()

                    # 상세 페이지 클릭 및 데이터 수집
                    article_link = news_item.find_element(By.CSS_SELECTOR, "a.thumb.news-detail")
                    driver.execute_script("arguments[0].click();", article_link)

                    wait.until(ec.presence_of_element_located((By.CSS_SELECTOR, "#news-detail-modal div.news-view")))
                    content_elem = wait.until(
                        ec.presence_of_element_located((By.CSS_SELECTOR, "div.news-view-body div.news-view-content")))
                    content = content_elem.text.split('※')[0].strip()

                    info_lis = wait.until(
                        ec.presence_of_all_elements_located((By.CSS_SELECTOR, "div.news-view-head ul.info li")))
                    pubdate = info_lis[0].text.strip() if info_lis else ""

                    # 이미지 처리
                    img, imgCap = "", ""
                    try:
                        img_elem = driver.find_element(By.CSS_SELECTOR, "div.news-view-body div.img img")
                        img = img_elem.get_attribute('src')
                        imgcap_elem = driver.find_elements(By.CSS_SELECTOR, "div.news-view-body div.img div.caption")
                        imgCap = imgcap_elem[0].text.strip() if imgcap_elem else ""
                    except:
                        pass

                    # 토큰화 및 저장
                    token = tokens({"title": title, "content": content}, kiwi)
                    timestamp = datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace("+00:00", "Z")

                    news_data = {
                        "title_tokens": token["title_tokens"],
                        "content_tokens": token["content_tokens"],
                        "writer_tokens": writer,
                        "news_id": news_id, "link": link, "title": title,
                        "media": media, "category": category, "writer": writer,
                        "content": content, "pubdate": pubdate, "img": img,
                        "imgCap": imgCap, "tag": tag, "timestamp": timestamp, "classified":False
                    }

                    sample.append(news_data)
                    index_sample_row(news_data)  # 개별 인덱싱

                    # 모달 닫기
                    driver.execute_script("jQuery('#news-detail-modal').modal('hide');")
                    time.sleep(1)

                except Exception as e:
                    # 1. 로컬 로거에 기록
                    error_msg = f'{page}페이지 {i + 1}번째 에러: {e}'
                    logger.error(error_msg)
                    # 2. Elasticsearch에 에러 로그 저장
                    index_error_log(error_msg,'bigkinds')
                    continue

            total_samples.extend(sample)

            # 다음 페이지 이동
            if page < max_pages:
                try:
                    first_item = news_items[0]
                    next_button = driver.find_element(By.CSS_SELECTOR, "#news-results-pagination a.page-next.page-link")
                    driver.execute_script("arguments[0].click();", next_button)
                    wait.until(ec.staleness_of(first_item))
                    page += 1
                except Exception as e:
                    error_msg = f'페이지 이동 실패: {e}'
                    logger.error(error_msg)
                    index_error_log(error_msg, 'bigkinds')
                    break
            else:
                break
    except Exception as e:
        error_msg = f"크롤링 함수 오류: {e}"
        logger.error(error_msg)
        index_error_log(error_msg, 'bigkinds')

    finally:
        driver.quit()

    return total_samples

def search_article(news_id:str):
    body = {
        "query": {
            "bool":{
                "filter":[
                    {"term":{"news_id":news_id}},
                ]
            }
        }
    }
    try :
        res = es.search(index=ES_INDEX, body=body)
        hits = res["hits"]["hits"]
        if len(hits)>0:
            src = hits[0]["_source"]
        news_info = {
            "news_id":src.get("news_id", ""),
            "title":src.get("title", ""),
            "content":src.get("content", ""),
            "writer":src.get("writer", ""),
            "tag":src.get("tag", ""),
            "media":src.get("media", ""),
            "link":src.get("link", ""),
            "category":src.get("category", ""),
            "pubdate":src.get("pubdate", ""),
            "img":src.get("img",""),
            "imgCap":src.get("imgCap",""),
            "timestamp":src.get("timestamp", ""),
        }
        return news_info
    except Exception as e:
        logger.error(f"{news_id}에 해당하는 기사가 없습니다 : {e}")
        return None


def get_news_raw(q: Optional[str] = None):

    keyword = (q or "").strip()

    body = {
        "query": {
            "match_all": {}
        },
        "size": 10000,
    }
    # body = {
    #     "query": {
    #         "bool": {
    #             "must_not": [
    #                 {"exists": {"field": "content"}}
    #             ]
    #         }
    #     }
    # }


    try :
        res = es.search(index=ES_INDEX, body=body)

        count = res['hits']['total']['value']
        print(count)

        hits = res["hits"]["hits"]

        news_list=[]
        for hit in hits:
            src = hit["_source"]
            news_list.append({
                "news_id":src.get("news_id", ""),
                "title":src.get("title", ""),
                "content":src.get("content", ""),
                "writer":src.get("writer", ""),
                "tag":src.get("tag", ""),
                "media":src.get("media", ""),
                "link":src.get("link", ""),
                "category":src.get("category", ""),
                "pubdate":src.get("pubdate", ""),
                "img":src.get("img",""),
                "imgCap":src.get("imgCap",""),
                "timestamp":src.get("timestamp", ""),
                # "title_tokens":src.get("title_tokens", ""),
                # "content_tokens":src.get("content_tokens", ""),
                # "writer_tokens":src.get("writer_tokens", "")
            })
        # df = pd.DataFrame(news_list)
        # logger.info(f'검색 결과 : {len(news_list)}개')
        # # print(df.head())
        # df.to_csv('sample_data.csv', index=False)
        return news_list
    except Exception as e:
        logger.error(f"검색 오류 : {e}")
        return None