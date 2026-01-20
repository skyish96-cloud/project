import hashlib

import pandas as pd
from fastapi import FastAPI
from selenium.webdriver.chromium.options import ChromiumOptions
from selenium.webdriver.chrome.service import Service
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as ec
from logger import Logger
import time
from typing import Optional
from elasticsearch_index.es_sample import ensure_index, index_sample_row, search_news_row, tokens
from elasticsearch_index.es_sample import es, ES_INDEX
from kiwipiepy import Kiwi


logger = Logger().get_logger(__name__)

# selenium driver 등록
driver_path = './driver/chromedriver.exe'
options = ChromiumOptions()
options.add_argument('--remote-allow-origins=*')
options.add_argument('--start-maximized')

############################################################################### 각 컬럼 값 크롤링하기 전에 초기화
def sample_crawling(max_pages:int):
    kiwi = Kiwi()
    service = Service()
    driver = webdriver.Chrome(service=service, options=options)
    driver.get('https://www.bigkinds.or.kr/')
    wait = WebDriverWait(driver, 30)

    # 페이지 로드 후 팝업 제거
    driver.execute_script("""
        document.querySelector('div.popup-container').style.display = 'none';
    """)

    # 1-2) 기간 지정 & 페이지 이동
    button = wait.until(ec.presence_of_element_located((By.ID, "ig-sd-btn")))
    button.click()
    # jQuery datepicker를 직접 호출해서 값 설정
    driver.execute_script("""
        $('#search-begin-date').val('2025-11-30').trigger('change');
        $('#search-end-date').val('2025-11-30').trigger('change');
    """)

    media = wait.until(ec.element_to_be_clickable(
        (By.CSS_SELECTOR, "#ds-modal")
    ))
    driver.execute_script("arguments[0].click();", media)
    logger.info("상세검색 모달 클릭 완료")

    media_tab = wait.until(ec.element_to_be_clickable(
        (By.CSS_SELECTOR, "#ds-modal .ds-tab-inner a.tab-btn.btn2")
    ))
    driver.execute_script("arguments[0].click();", media_tab)
    logger.info("언론사 탭 클릭 완료")

    # 전국일간지, 방송사, 스포츠신문
    national_daily = wait.until(
        ec.element_to_be_clickable((By.CSS_SELECTOR, "#categoryProviderGroup label[for='전국일간지']"))
    )
    national_daily.click()
    broadcast = wait.until(
        ec.element_to_be_clickable((By.CSS_SELECTOR, "#categoryProviderGroup label[for='방송사']"))
    )
    broadcast.click()
    sports = wait.until(
        ec.element_to_be_clickable((By.CSS_SELECTOR, "#categoryProviderGroup label[for='스포츠신문']"))
    )
    sports.click()

    apply = wait.until(ec.presence_of_element_located(
        (By.CSS_SELECTOR, "button.apply-btn.primary-btn.news-search-btn")
    ))
    driver.execute_script("arguments[0].click();", apply)

    # 2. 필드값 가져오는 코드 시작
    page = 1
    while page <= max_pages:
        sample = []
        wait.until(ec.presence_of_element_located((By.CSS_SELECTOR, "#news-results")))
        wait.until(ec.presence_of_element_located((By.CSS_SELECTOR, "#news-results div.news-item")))
        news_items = driver.find_elements(By.CSS_SELECTOR, "#news-results div.news-item")
        logger.info(f'{page}페이지 {len(news_items)}시작')
        for i, news_item in enumerate(news_items):
            try:
                # 1. 모달 완전 초기화
                driver.execute_script("""
                            jQuery('.modal').modal('hide');
                            document.querySelectorAll('.modal.show, #news-detail-modal').forEach(m => m.remove());
                            document.querySelectorAll('.modal-backdrop').forEach(b => b.remove());
                            jQuery('body').removeClass('modal-open');
                        """)
                time.sleep(1)

                # 2. 스크롤
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", news_item)
                time.sleep(1)

                # 3. news_id 먼저 추출 (핵심!)
                news_id = None
                article_link = None
                article_link = news_item.find_element(By.CSS_SELECTOR, "a.thumb.news-detail")
                news_id_pre = news_item.find_element(By.CSS_SELECTOR, "div.cont div.info a.provider").get_attribute('href')
                news_id = hashlib.sha256(news_id_pre.split('//',1)[1].encode()).hexdigest()
                logger.info(f'{page}페이지 {i + 1} news_id: {news_id}')

                if search_news_row(news_id):
                    logger.info(f'중복 스킵: {page}페이지 {i+1}')
                    continue


                category = None
                category_elem = news_item.find_element(By.CSS_SELECTOR,"div.info span.bullet-keyword")
                category_text = category_elem.text.strip()
                if category_text == '미분류':
                    logger.info('category : 미분류')
                    continue
                category_list = category_text.split(' | ')
                cate1 = category_list[0] if len(category_list) > 0 else None
                cate2 = category_list[1] if len(category_list) > 1 else None
                cate3 = category_list[2] if len(category_list) > 2 else None
                if cate1 == '사회>날씨' or cate2 == '사회>날씨' or cate3 == '사회>날씨':
                    continue
                category1 = category_text.split('>')[0].strip()
                category_mapping = {
                    '국제': '세계',
                    '문화': '생활/문화',
                    'IT_과학': 'IT/과학'
                }
                category = category_mapping.get(category1, category1)

                media = None
                media_elem = news_item.find_element(By.CSS_SELECTOR, "div.info a")
                media = media_elem.text.strip()

                writer = None
                writer_elem = news_item.find_elements(By.CSS_SELECTOR, "div.info p.name")[1]
                writer = writer_elem.text.strip()

                title = None
                title_elem = news_item.find_element(By.CSS_SELECTOR,"div.cont div.title-cp")
                title = title_elem.text.strip()



                # 4. 클릭
                driver.execute_script("arguments[0].click();", article_link)
                logger.info(f'{page}페이지 {i + 1} 클릭 완료')

                # 5. news_view 전체 로딩 대기
                news_view = wait.until(ec.presence_of_element_located((By.CSS_SELECTOR, "#news-detail-modal div.news-view")))
                logger.info("news-view 로딩 완료")

                # content
                content = None
                content_elem = wait.until(ec.presence_of_element_located((By.CSS_SELECTOR, "div.news-view-body div.news-view-content")))
                content1 = content_elem.text.strip()
                content = content1.split('※')[0].strip()
                logger.info(f'''media: {media}\nwriter: {writer}\ntitle: {title}\ncategory: {category}\ncontent: {content}''')

                token = None
                token = tokens({"title": title, "content": content}, kiwi)
                from datetime import datetime
                from datetime import timezone
                timestamp = datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace("+00:00", "Z")

                # 데이터 추가
                sample.append({"news_id": news_id, "title": title, "category": category,"media":media, "content": content, "title_tokens":token['title_tokens'], "content_tokens":token['content_tokens'], "timestamp":timestamp})

                # 7. 모달 닫기
                driver.execute_script("""
                    jQuery('#news-detail-modal').modal('hide');
                    document.querySelector('#news-detail-modal').style.display = 'none';
                    document.body.style.overflow = 'auto';
                """)
                time.sleep(1)


            except Exception as e:
                logger.error(f'{page}페이지 {i + 1}번째 뉴스 에러: {e}')
                driver.execute_script("jQuery('.modal').modal('hide');")
                continue
            finally:
                logger.info(f'{page}페이지 {i+1}번째 완료')
        logger.info(f'크롤링 완료 : {page}페이지 {len(sample)}개')


        try:
            if sample:
                for news in sample:
                    index_sample_row(news)
        except Exception as e:
            logger.error(f'실패: {e}')


        # jQuery datepicker를 직접 호출해서 값 설정
        page += 1
        if page > max_pages:
            break
        driver.execute_script("""
            const el = document.getElementById('paging_news_result');
            el.focus();
            el.value = arguments[0];

            //Enter 키 이벤트를 JS로 직접 발생
            ['keydown', 'keypress', 'keyup'].forEach(type => {
                el.dispatchEvent(new KeyboardEvent(type, {
                    key: 'Enter',
                    code: 'Enter',
                    keyCode: 13,
                    which: 13,
                    bubbles: true
                }));
            });
        """, page)

        time.sleep(1.5)  # 페이지 로딩 대기
        logger.info(f'{page}페이지 이동 완료')

    driver.quit()
    ensure_index()
    return sample



def get_sample(q: Optional[str] = None):

    keyword = (q or "").strip()

    body = {
        "query": {
            "match_all": {}
        },
        "size":100
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
                "title":src.get("title",""),
                "title_tokens":src.get("title_tokens", ""),
                "category":src.get("category", ""),
                "media":src.get("media", ""),
                "content":src.get("content", ""),
                "content_tokens":src.get("content_tokens", "")
            })
        df = pd.DataFrame(news_list)
        logger.info(f'검색 결과 : {len(news_list)}개')
        # print(df.head())
        df.to_csv('sample_data.csv', index=False)
        return news_list
    except Exception as e:
        logger.error(f"검색 오류 : {e}")
        return None