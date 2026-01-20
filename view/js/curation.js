document.addEventListener('DOMContentLoaded', async () => {
    // --- 전역 설정 및 상태 변수 ---
    let currentSort = 'accuracy';     // 정렬 기본값: 정확도순
    let currentCategory = 'all';      // 카테고리 기본값: 전체
    let currentPage = 1;              // 현재 페이지
    let nptiResult = null;          // 뉴스 API 호출에 사용할 NPTI 코드 (예: STFN)
    let nptiSource = null;            // 'user' | 'compose'

    const CONFIG = {ITEMS_PER_PAGE: 20}
    // const ITEMS_PER_PAGE = 20;        // 페이지당 뉴스 개수

    const NPTI_KOR_MAP = {
        L:'긴 기사', S:'짧은 기사',
        C:'텍스트 중심 기사', T:'이야기형 기사',
        I:'분석 기사', F:'객관적 기사',
        P:'우호적 기사', N:'비판적 기사'
    };

    const NPTI_NICK_MAP = {
    LCFN: '팩트 정밀 감시자',
    LCFP: '밝은 정보 탐독가',
    LCIN: '리스크 구조 분석가',
    LCIP: '장문 전망 분석가',
    LTFN: '현실 통찰 독서가',
    LTFP: '따뜻한 장문 탐독가',
    LTIN: '구조 해부 사상가',
    LTIP: '낙관적 사유가',
    SCFN: '경제성 강한 체커',
    SCFP: '속도형 정보 소비자',
    SCIN: '리스크 감지 전문가',
    SCIP: '빠른 인사이트 수집기',
    STFN: '팩트 현실주의자',
    STFP: '힐링 스토리 리더',
    STIN: '비판적 통찰 추적자',
    STIP: '핵심 낙관주의자'
    };

    // --- DOM 요소 참조 ---
    const resultHeader = document.getElementById('nptiResultHeader');
    const curationList = document.getElementById('curationList');
    const categoryTabs = document.querySelectorAll('.nav-tabs a');
    const resultsArea = document.querySelector('.news-feed-section');
    const categoryNameDisplay = document.getElementById('categoryName');


    // --- NPTI Source 분기 ---
    nptiSource = sessionStorage.getItem('nptiSource');
    //console.log('[Curation] nptiSource:', nptiSource);

    // API 기반
    if (nptiSource === 'user') {
        //await loadUserNPTI();
        loadUserNPTI();
    }
    // sessionStorage 기반
    else if (nptiSource === 'composed') {
        loadComposedNPTI();
    }
    else {
        alert('잘못된 접근입니다.');
        location.href = '/';
        return;
    }




    // --- 카테고리 탭 이벤트 ---
    categoryTabs.forEach(tab => {
        tab.addEventListener('click', (e) => {
            e.preventDefault();

            // UI 업데이트: active 클래스 이동
            categoryTabs.forEach(t => t.classList.remove('active'));
            tab.classList.add('active');

            const category = tab.dataset.category || 'all';
            currentCategory = category;
            currentPage = 1;

            // 아래 제목 동기화
            if (categoryNameDisplay) {
            categoryNameDisplay.innerText = tab.textContent.trim();
            }

            loadCurationNews(category, 1);
        });
    });

    // --- 정렬 버튼 이벤트 ---
    document.querySelectorAll('.sort-btn').forEach(button => {
        button.addEventListener('click', (e) => {
            const selectedSort = e.currentTarget.dataset.sort;

            // 이미 선택된 정렬이면 아무 것도 안 함
            if (currentSort === selectedSort) return;

            // 상태 변경
            currentSort = selectedSort;
            currentPage = 1;

            // UI: 주황색(active) 토글
            document.querySelectorAll('.sort-btn')
                .forEach(btn => btn.classList.remove('active'));
            e.currentTarget.classList.add('active');

            // 데이터 재로드
            loadCurationNews(currentCategory, 1);
        });
    });


    // --- 로그인 유저 NPTI ---
    async function loadUserNPTI() {
        try {
            const res = await fetch('/user/npti/me', { credentials: 'include' });

            // 로그인X
            if (res.status === 401 || res.status === 403) {
                    alert('로그인이 필요합니다.');
                    location.href = '/login';
                    return;
                }
            // 로그인O - NPTI x
            if (res.status === 404) {
                    alert('NPTI 진단하러 가기.');
                    location.href = '/test';
                    return;
                }
            // 서버 오류
            if (!res.ok) throw new Error("NPTI API Error");

            // 정상
            const data = await res.json();
            //console.log('data : ',data);
            nptiResult = data.npti_code;

            //console.log('[Curation] user NPTI:', nptiResult);
            renderCurationHeader(data);
            // 최초 뉴스 로딩
            loadCurationNews('all', 1);

        } catch (err) {
            console.error(err);
            alert('NPTI 정보를 불러오지 못했습니다.');
            location.href = '/';
        }
        console.log('nptiSource:', nptiSource);
    }


    // --- 조합 NPTI ---
    function loadComposedNPTI() {
        const composed = sessionStorage.getItem('selectedNPTI');

        if (!composed || composed.length !== 4) {
            alert('조합된 NPTI 정보가 없습니다.');
            location.href = '/';
            return;
        }
        nptiResult = composed;

        console.log('[Curation] composed NPTI:', composed);

        renderCurationHeader({
            npti_code: composed,
            type_nick: NPTI_NICK_MAP[composed] || '조합 성향',
            npti_kor_list: composed.split('').map(c => NPTI_KOR_MAP[c])
        });
        console.log('selectedNPTI:', sessionStorage.getItem('selectedNPTI'));
        // 최초 뉴스 로딩
        loadCurationNews('all', 1);
    }


    // --- UI 렌더링 ---
    // 상단 NPTI 성향
    function renderCurationHeader(data) {
        if (!resultHeader || !data) return;

        const { npti_code, type_nick, npti_kor_list } = data;

        resultHeader.innerHTML = `
            <div class="npti-header">
                <span class="npti-code">${npti_code}</span>
                <span class="npti-nickname">${type_nick}</span>
            </div>

            <div class="tags">
                ${npti_code.split('').map((char, i) => `
                    <div class="tag-item">
                        <span class="point">${char}</span> - ${npti_kor_list[i]}
                    </div>
                `).join('')}
            </div>
    `;

        // 하단 섹션 제목 업데이트 (예: [STFN] 성향 뉴스 큐레이션)
        // const curationTitle = document.getElementById('curation-result-title');
        // if (curationTitle) curationTitle.innerText = `[${npti_code}] 성향 뉴스 큐레이션`;
    }

    // --- 뉴스 로드 ---
    async function loadCurationNews(category = 'all', page = 1) {
        if (!curationList) return;

        currentCategory = category;
        currentPage = page;

        // 리스트 비우고 로딩 메시지 표시
        curationList.innerHTML = '<div class="loading">사용자님의 성향에 맞는 뉴스를 분석 중입니다...</div>';

        const url =
            `/curated/news?npti=${nptiResult}&category=${category}&sort_type=${currentSort}&page=${page}`;

        try {
            // 백엔드 엔드포인트에 쿼리 파라미터 전달
            const res = await fetch(url, { credentials: 'include' });
            if (!res.ok) throw new Error('기사 로드 실패');

            const data = await res.json(); // data 구조: { articles: [...], total: 100 }

            // 실제 뉴스 카드 그리기 함수 호출
            renderNewsCards(data.articles);
            console.log(data.sort)

            // 페이지네이션 생성 함수 호출
            renderPagination(data.total);

        } catch (error) {
            console.error('News Load Error:', error);
            curationList.innerHTML = '<p class="error-msg">기사 로딩 실패</p>';
        }
    }

    // --- 뉴스 기사 배열을 받아 HTML 뉴스 카드 ---
    function renderNewsCards(articles) {
        curationList.innerHTML = ''; // 로딩 메시지 제거

        if (!articles || articles.length === 0) {
            curationList.innerHTML =
                '<p class="no-data">해당 조건의 뉴스가 없습니다.</p>';
            return;
        }

        articles.forEach(news => {
            curationList.insertAdjacentHTML('beforeend', `
                <div class="news-card"
                    onclick="location.href='/article?news_id=${news.id}'">
                    <div class="news-img">
                        <img src="${news.thumbnail || '/view/img/default.png'}"
                            onerror="this.src='/view/img/default.png'">
                    </div>
                    <div class="news-info">
                        <h3>${news.title}</h3>
                        <p class="summary">${news.summary}</p>
                        <div class="news-meta">
                            <span>${news.publisher}</span> |
                            <span>${news.date}</span>
                        </div>
                    </div>
                </div>
            `);
            //curationList.insertAdjacentHTML('beforeend', articleHtml);
        });
    }

    // --- 페이지네이션 ---
    function renderPagination(totalItems) {
        const paginationContainer = document.getElementById('paginationContainer');
        if (totalItems === 0) {
        if (paginationContainer) paginationContainer.innerHTML = '';  // 페이지네이션 비움
        return;  // 함수 종료
    }

        const totalPages = Math.ceil(totalItems / CONFIG.ITEMS_PER_PAGE); //
        if (totalPages < 1) return; //

        let html = `<div class="pagination" style="margin-top:30px; text-align:center;">`;

        // 현재 페이지에서 5를 빼서 시작점을 잡되, 최소값은 1로 고정
        let startPage = Math.max(1, currentPage - 5);

        // 시작점을 기준으로 10개의 버튼을 보여주되, 전체 페이지 수를 넘지 않음
        let endPage = Math.min(totalPages, startPage + 9);

        // [보정] 마지막 페이지 근처에서 버튼이 10개 미만이 되지 않도록 시작점 재조정
        if (endPage === totalPages) {
            startPage = Math.max(1, endPage - 9);
        }

        // 처음/이전 버튼
        html += `<button class="arrow" ${currentPage === 1 ? 'disabled' : ''} data-page="1">《</button>`;
        html += `<button class="arrow" ${currentPage === 1 ? 'disabled' : ''} data-page="${currentPage - 1}">〈</button>`;

        // 번호 생성
        for (let i = startPage; i <= endPage; i++) {
            html += `<button class="page-num ${i === currentPage ? 'active' : ''}" data-page="${i}">${i}</button>`;
        }

        // 다음/마지막 버튼
        html += `<button class="arrow" ${currentPage === totalPages ? 'disabled' : ''} data-page="${currentPage + 1}">〉</button>`;
        html += `<button class="arrow" ${currentPage === totalPages ? 'disabled' : ''} data-page="${totalPages}">》</button>`;

        html += `</div>`;

        // const paginationContainer = document.getElementById('paginationContainer');
        if (paginationContainer) {
            paginationContainer.innerHTML = html;
        }
    }

    document.addEventListener('click', function (e) {
        if (e.target.matches('.pagination button[data-page]')) {
            const page = parseInt(e.target.dataset.page);
            if (!isNaN(page)) {
                loadCurationNews(currentCategory, page);
            }
        }
    });

}); // DOMContentLoaded 종료