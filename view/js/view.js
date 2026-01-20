// [전역 변수] 수집된 데이터를 담을 배열과 현재 기사 ID
let behaviorLogs = [];
let currentNewsId = null;
let tracker = null; // tracker 제어용 객체
let viewerId = "guest";
let hasNPTI = false;

document.addEventListener('DOMContentLoaded', async function () {
    const params = new URLSearchParams(window.location.search);
    const news_id = params.get('news_id');

    let sessionData = {};
    try {
        // main.js가 먼저 로드되었으므로 함수 호출 가능
        sessionData = await loadSessionState();
    } catch (e) {
        console.error("세션 정보를 가져오는 중 오류 발생(main.js 로드 확인 필요):", e);
    }

    if (sessionData && sessionData.isLoggedIn && sessionData.user_id) {
        viewerId = sessionData.user_id;
        hasNPTI = sessionData.hasNPTI;
        console.log(`[View] 사용자 인증 완료: ${viewerId} - 진단 여부: ${hasNPTI}`);
    } else {
        console.log(`[View] 비로그인(Guest) 접속`);
    }

    if (news_id) {
        currentNewsId = news_id; // 전역 변수에 할당 (나중에 전송할 때 사용)
        loadArticleData(news_id, viewerId);
    } else {
        alert("잘못된 접근입니다.");
    }

    // 로그아웃 확인 버튼 이벤트
    const logoutBtn = document.getElementById('confirmLogout');
    if (logoutBtn) {
        logoutBtn.addEventListener('click', async () => {
            try {
                // 1. 로그아웃 전, 수집된 행동 데이터가 있다면 마지막으로 전송
                if (typeof sendDataToServer === 'function') {
                    sendDataToServer();
                }

                // 2. 서버 로그아웃 처리
                const response = await fetch('/logout', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' }
                });

                if (response.ok) {
                    // 3. 성공 시 메인으로 이동 (뒤로가기 방지를 위해 replace 사용 권장)
                    location.replace("/");
                }
            } catch (error) {
                console.error('Logout failed:', error);
                location.replace("/"); // 에러가 나더라도 세션 만료를 위해 메인으로 이동
            }
        });
    }

});

// 페이지 이탈(닫기, 새로고침, 뒤로가기) 시 데이터 전송
window.addEventListener('beforeunload', sendDataToServer);
document.addEventListener('visibilitychange', function() {
    if (document.visibilityState === 'hidden') {
        sendDataToServer();
    }
});

function loadArticleData(news_id, viewerId){
    fetch(`/article/${news_id}`)
        .then(response => {
            if (!response.ok) throw new Error("기사를 불러오는데 실패했습니다.");
            return response.json();
        })
        .then(data => {
            renderArticle(data);

            // [수정됨] 기사 로딩이 끝나면 행동 수집 시작!
            if (!tracker && viewerId != 'guest' && hasNPTI) {
                tracker = userBehavior(news_id, 100); // 0.1초 간격 수집
            }

            if (data.related_news && data.related_news.length > 0){
                initRelatedNews(data.related_news);
            }
        })
        .catch(error => {
            console.error('Error:', error);
        });
}


// 기사 원문 보여주기 (링크 있으면 원문 버튼 & 이미지 있으면 보여줌, 없으면 생략)
function renderArticle(data){
    document.getElementById('viewPress').innerText = data.media || "";
    document.getElementById('viewTitle').innerText = data.title || "";
    document.getElementById('viewCategory').innerText = data.category || "";
    document.getElementById('viewDate').innerText = data.pubdate || "";
    document.getElementById('viewAuthor').innerText = data.writer || "";
    document.getElementById('viewCaption').innerText = data.imgCap || "";
    document.getElementById('viewPress').innerText = data.media || "";
    document.getElementById('viewBody').innerText = data.content || "";
    const originBtn = document.querySelector('.btn-origin');
    if (originBtn && data.link){
        originBtn.onclick = function(){
            window.open(data.link,'_blank');
        }

    }
    const imgContainer = document.querySelector('div.img-placeholder');
    if (imgContainer && data.img) {
        imgContainer.innerHTML = `<img src="${data.img}" style="height:100%; width:100%; object-fit:contain;", alt="뉴스 이미지">`;
        imgContainer.style.display = 'block';
    } else if (imgContainer && !data.img){
        imgContainer.style.display = 'none';
    }
    const copyrightText = `이 기사의 저작권은 ${data.media || '해당 언론사'}에 있으며, 이를 무단으로 이용할 경우 법적 책임을 질 수 있습니다.`
    document.getElementById('viewCopyright').innerText = copyrightText;
}


// 관련 기사 보여주기
function initRelatedNews(related_news) {
    const relatedList = document.getElementById('relatedList');
    if (!relatedList) return;

    relatedList.innerHTML = '';
    related_news.forEach(item => {
        const imgHtml = item.img
            ? `<div class="related-img"><img src="${item.img}" alt="관련기사 이미지" style="width:100%; height:100%; object-fit: contain;"></div>`
            : `<div class="related-img" style="background-color: #eee; display:flex; justify-content:center; align-items:center; font-size: 8px;">이미지 없음</div>`;
        const html = `
            <a href="/article?news_id=${item.news_id}" class="related-item">
                <div class="related-text">
                    <h4>${item.title}</h4>
                    <div class="related-info"><span>${item.media}</span> | <span>${item.pubdate}</span></div>
                </div>
                ${imgHtml}
            </a>`;
        relatedList.insertAdjacentHTML('beforeend', html);
    });
}


function sendDataToServer() {
    // 1. 보낼 데이터가 없으면 중단
    if (!behaviorLogs || behaviorLogs.length === 0) return;
    const logsToSend = [...behaviorLogs];
    behaviorLogs = [];
    // 2. 최종 데이터 패키징
    const payload = {
        news_id: currentNewsId,
        user_id: viewerId, // 로그인 기능 구현 시 실제 ID로 교체
        session_end_time: Date.now(),
        total_logs: logsToSend.length,
        logs: logsToSend // 복사한 데이터(10초)
    };

    // 3. 데이터 전송 (sendBeacon 사용 권장)
    // sendBeacon은 페이지가 닫혀도 전송을 보장하며, POST로 전송됨.
    const blob = new Blob([JSON.stringify(payload)], {type: 'application/json'});
    const success = navigator.sendBeacon('/log/behavior', blob);

    // 4. 전송 후 로그 초기화 (중복 전송 방지)
    if (success) {
        console.log(`[Data Transfer] sendBeacon 전송 성공! ${logsToSend.length}개`)
    } else {
        console.log(`[Data Transfer] sendBeacon 실패 - fetch로 재시도`)
        fetch('/log/behavior',{
            method: 'POST',
            headers: {'Content-Type':'application/json'},
            body:JSON.stringify(payload),
            keepalive:true
        })
        .then(response => {
            if (response.ok) {
                console.log(`[Data Transfer] fetch(keepalive) 전송 성공! ${logsToSend.length}개`);
            } else {
                console.error("[Data Trnasfer] fecth 서버 응답 에러:", response.status);
            }
        })
        .catch(err => {
            console.error("[Data Transfer] 최종 전송 실패:", err);
            behaviorLogs.unshift(...logsToSend);
        });
    }
}

function userBehavior(news_id, intervalMs = 40) {
    // ------------------------------------------------------------------------
    // [설정]
    // ------------------------------------------------------------------------
    const LOG_INTERVAL_MS = 1000; // 1초 단위로 데이터 처리 및 저장
    let timeSinceLastLog = 0;

    // ------------------------------------------------------------------------
    // [상태 변수]
    // ------------------------------------------------------------------------
    let totalActiveMs = 0; // 활성화 누적 시간
    let lastCheckTime = Date.now();

    // Page Active Check
    let isMouseInside = true;
    let isScrolling = false;
    let scrollTimeout = null;

    // Data Accumulation
    const state = {
        currentX: 0, currentY: 0,
        cumulativeX: 0, cumulativeY: 0,      // MMF 계산용 (계속 누적)
        lastX: null, lastY: null,

        scrollTop: window.scrollY || window.pageYOffset,
        cumulativeScrollY: 0,                // MSF 계산용 (계속 누적)
        lastScrollTop: window.scrollY || window.pageYOffset
    };

    const targetDiv = document.getElementById('viewBody');

    // ------------------------------------------------------------------------
    // [이벤트 핸들러]
    // ------------------------------------------------------------------------
    const handleMouseEnter = () => { isMouseInside = true; };
    const handleMouseLeave = () => { isMouseInside = false; };

    const trackScrollState = () => {
        isScrolling = true;
        clearTimeout(scrollTimeout);
        scrollTimeout = setTimeout(() => { isScrolling = false; }, 3000);
    };

    const isPageActive = () => {
        return !document.hidden && (document.hasFocus() || isMouseInside || isScrolling);
    };

    // 마우스 이동 누적 (이벤트 발생 시 즉시 반영)
    const handleMouseMove = (e) => {
        if (!isPageActive()) return;
        const x = e.clientX;
        const y = e.clientY;

        state.currentX = x;
        state.currentY = y;

        if (state.lastX !== null && state.lastY !== null) {
            state.cumulativeX += Math.abs(x - state.lastX);
            state.cumulativeY += Math.abs(y - state.lastY);
        }
        state.lastX = x;
        state.lastY = y;
    };

    // 스크롤 누적
    const handleScroll = () => {
        if (!isPageActive()) return;
        const currentScrollY = window.scrollY || window.pageYOffset; // 표준화

        if (state.lastScrollTop !== null) {
            state.cumulativeScrollY += Math.abs(currentScrollY - state.lastScrollTop);
        }
        state.scrollTop = currentScrollY;
        state.lastScrollTop = currentScrollY;
    };

    // 리스너 등록
    document.documentElement.addEventListener('mouseenter', handleMouseEnter);
    document.documentElement.addEventListener('mouseleave', handleMouseLeave);
    window.addEventListener('scroll', trackScrollState);
    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('scroll', handleScroll);


    // ------------------------------------------------------------------------
    // [Timer] 0.1초마다 호출되지만, 데이터 저장은 1초마다 수행
    // ------------------------------------------------------------------------
    const collectTimerId = setInterval(() => {
        const now = Date.now();
        const timeDelta = now - lastCheckTime;
        lastCheckTime = now;

        if (!isPageActive()) {
            console.log("PageInactive - 데이터 수집 중단");
            return;
        }



        totalActiveMs += timeDelta;
        timeSinceLastLog += timeDelta;

        // 1초(1000ms)가 지났는지 확인
        if (timeSinceLastLog >= LOG_INTERVAL_MS) {
            timeSinceLastLog -= LOG_INTERVAL_MS;

            // 화면 크기 및 스크롤 위치 (정규화를 위해 필요)
            const winWidth = window.innerWidth || 1;
            const winHeight = window.innerHeight || 1;
//            const scrollX = window.scrollX || window.pageXOffset;
//            const scrollY = window.scrollY || window.pageYOffset;

            const totalActiveSeconds = Math.max(totalActiveMs / 1000, 0.001);

            // --- Feature 1: Mouse X, Y (0~1 Rescaled) ---
            // 현재 마우스 위치는 문서 전체 기준(pageX)이므로, 뷰포트 기준(clientX)으로 변환 필요
            // state.currentX(문서기준) - scrollX = 뷰포트 기준 X
            let normMouseX = state.currentX/ winWidth;
            let normMouseY = state.currentY / winHeight;

            // --- Feature 2: MMF, MSF (Rescaled Length) ---
            // 논문 정의: "moving length ... rescaled ... by screen height/width"
            // 시간으로 나누지 않고 누적 거리를 화면 크기로 나눕니다.
            let normMMF_X = (state.cumulativeX / winWidth) / totalActiveSeconds;
            let normMMF_Y = (state.cumulativeY / winHeight) / totalActiveSeconds;
            let normMSF_Y = (state.cumulativeScrollY / winHeight) / totalActiveSeconds;

            // --- Feature 3: Baseline 3 (height_3) ---
            let baseline = 0;
            if (targetDiv) {
                const rect = targetDiv.getBoundingClientRect();
                const mouseViewportX = state.currentX;
                const mouseViewportY = state.currentY;

                // 1. Hover Check
                const isHovering = (
                    mouseViewportX >= rect.left && mouseViewportX <= rect.right &&
                    mouseViewportY >= rect.top && mouseViewportY <= rect.bottom
                );

                if (isHovering) {
                    baseline = 1;
                } else {
                    // 2. Distance to Rectangle (Not Center!)
                    // 사각형 밖일 때, 가장 가까운 변까지의 거리 계산
                    // dx: 사각형 왼쪽보다 작으면 왼쪽 거리, 오른쪽보다 크면 오른쪽 거리, 사이면 0
                    const dx = Math.max(rect.left - mouseViewportX, 0, mouseViewportX - rect.right);
                    const dy = Math.max(rect.top - mouseViewportY, 0, mouseViewportY - rect.bottom);

                    const distance = Math.sqrt(dx * dx + dy * dy);

                    // 거리가 0이면(경계선 등) Infinity 방지
                    baseline = 1 / (1+distance);
                }
            }

            // 데이터 스냅샷 생성
            const dataSnapshot = {
                elapsedMs: parseFloat((totalActiveMs / 1000).toFixed(3)),
                mouseX: parseFloat(normMouseX.toFixed(10)),
                mouseY: parseFloat(normMouseY.toFixed(10)),
                MMF_X: parseFloat(normMMF_X.toFixed(10)), // 소수점 20자리는 너무 깁니다. 5자리 정도면 충분
                MMF_Y: parseFloat(normMMF_Y.toFixed(10)),
                MSF_Y: parseFloat(normMSF_Y.toFixed(10)),
                baseline: parseFloat(baseline.toFixed(10)),
                // read: (논문에 있던 read 0/1 컬럼은 별도 로직이 필요하면 여기에 추가)
            };
            behaviorLogs.push(dataSnapshot);
            console.log(dataSnapshot);
            if (behaviorLogs.length >= 10) {
                console.log("10초 경과 : 중간 데이터 전송");
                sendDataToServer();
            }
        }
    }, intervalMs);

    return {
        stop: () => {
            window.removeEventListener('mousemove', handleMouseMove);
            window.removeEventListener('scroll', handleScroll);
            document.documentElement.removeEventListener('mouseenter', handleMouseEnter);
            document.documentElement.removeEventListener('mouseleave', handleMouseLeave);
            window.removeEventListener('scroll', trackScrollState);
            if (scrollTimeout) clearTimeout(scrollTimeout);
            clearInterval(collectTimerId);

            // 종료 시 남은 데이터 전송
            console.log("남은 데이터 전송")
            sendDataToServer();
        }
    };
}