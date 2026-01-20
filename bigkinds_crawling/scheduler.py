from apscheduler.schedulers.asyncio import AsyncIOScheduler
from Naver.naver_crawling import  run_fast_crawl, run_slow_crawl
from algorithm.news_NPTI import classify_npti_fast, init_npti
from bigkinds_crawling.news_raw import news_crawling
from bigkinds_crawling.news_aggr_grouping import news_aggr
import multiprocessing
import psutil
from logger import Logger
from datetime import datetime, timezone, timedelta
import inspect


logger = Logger().get_logger(__name__)

result_queue = multiprocessing.Queue()

# 1. 하나의 통합된 실행 제어 함수
def run_job_with_timeout(func, args, timeout, on_success=None):
    """
    func: 실행할 함수 (news_crawling 등)
    args: 함수에 전달할 인자 (튜플 형태)
    timeout: 제한 시간 (초 단위)
    """
    # 별도 프로세스로 작업 시작

    needs_queue = ['news_aggr']
    if func.__name__ in needs_queue:
        full_args = args + (result_queue,)
    else:
        full_args = args

    p = multiprocessing.Process(target=func, args=full_args)
    p.start()
    print(f"{func} 함수 시작")

    # 프로세스가 끝날 때까지 지정된 시간(timeout)만큼 대기
    p.join(timeout)

    # 만약 지정된 시간이 지났는데도 프로세스가 살아있다면? (강제 종료 로직)
    if p.is_alive():
        print(f"⚠️ [타임아웃] {func.__name__} 작업이 {timeout}초를 초과하여 강제 종료 및 청소를 시작합니다.")

        try:
            # 부모 프로세스 객체 생성
            parent = psutil.Process(p.pid)
            # 자식 프로세스(Chromedriver, Chrome 등)를 재귀적으로 모두 찾음
            children = parent.children(recursive=True)

            # 1단계: 자식 프로세스(브라우저 등) 먼저 종료
            for child in children:
                if child.is_running():
                    child.terminate()

            # 2단계: 부모 프로세스(파이썬 함수) 종료
            parent.terminate()

            # 3단계: 완전히 죽을 때까지 최대 3초 대기 후, 안 죽으면 강제 Kill
            gone, alive = psutil.wait_procs(children + [parent], timeout=3)
            for p_alive in alive:
                p_alive.kill()

        except psutil.NoSuchProcess:
            pass
        finally:
            p.join()  # 프로세스 자원 반환
            print(f"✅ [정리완료] {func.__name__} 관련 좀비 프로세스가 모두 제거되었습니다.")
    else:
        print(f"✅ [완료] {func.__name__} 작업이 제시간에 종료되었습니다.")
        # 정상 종료 시 분류 작업 트리거
        if on_success:
            on_success()

# 크롤링 직후 즉시 분류(date job) 트리거
def trigger_classify_once(scheduler):
    job_id = "classify_once_pending"
    if scheduler.get_job(job_id):
        return
    scheduler.add_job(
        classify_npti_fast,
        trigger="date", #딱 1번 실행
        run_date=datetime.now() + timedelta(seconds=1),
        id=job_id,
        replace_existing=True,  # 혹시 남아있으면 덮어씀
        misfire_grace_time=60  # 1분 정도 늦어도 실행 허용
    )
    logger.info("크롤링 완료 → 즉시 NPTI 분류 1회 예약")

def sch_start():
    job_defaults = {
        'coalesce': True,
        'max_instances': 1
    }
    sch = AsyncIOScheduler(job_defaults=job_defaults)
    now = datetime.now(timezone(timedelta(hours=9)))
    init_npti()

    # 5분(300초) 주기지만, 안전을 위해 280초(4분 40초)에 강제 종료하도록 설정
    # 그래야 5분 정각에 새 스케줄러가 시작될 때 충돌이 없습니다.

    # 2-1. 뉴스 크롤링 등록
    sch.add_job(
        run_job_with_timeout,
        'interval',
        minutes=5,
        id='news_crawling',
        args=[news_crawling, (10,), 280, lambda: trigger_classify_once(sch)],
        next_run_time=(now + timedelta(seconds=5)).isoformat(timespec="seconds") # 함수명, 인자(튜플), 타임아웃(초)
    )

    # 네이버 크롤러(fast)
    sch.add_job(
        run_job_with_timeout,
        trigger='interval',
        minutes=10,
        id='crawler_naver_fast',
        args=[run_fast_crawl, (), 540, lambda: trigger_classify_once(sch)],
        next_run_time=(now + timedelta(seconds=10)).isoformat(timespec="seconds")
    )
    # 네이버 크롤러(slow) # 스케줄러 시작 기준 7분 후 첫 실행
    sch.add_job(
        run_job_with_timeout,
        trigger='interval',
        minutes=30,
        id='crawler_naver_slow',
        args=[run_slow_crawl, (), 1680, lambda: trigger_classify_once(sch)],
        next_run_time=(now + timedelta(minutes=7)).isoformat(timespec="seconds")
    )

    # 2-2. 뉴스 집계 등록
    sch.add_job(
        run_job_with_timeout,
        'interval',
        minutes=5,
        id='news_aggr',
        args=[news_aggr, (), 290],
        next_run_time=(now + timedelta(seconds=30)).isoformat(timespec="seconds")
    )

    # 기사 NPTI 라벨링 알고리즘 호출
    sch.add_job(
        run_job_with_timeout,
        trigger="interval",
        seconds=30,
        id="news_npti_classify",
        args=[classify_npti_fast, (), 300],  # 5분 타임아웃
        next_run_time=(now + timedelta(seconds=50)).isoformat(timespec="seconds")
    )

    return sch