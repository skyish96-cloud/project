// 1. 전역 상수 및 상태 (Global Config & State)
const EL = {
    form: () => document.querySelector('.search-form'),
    input: () => document.querySelector('.search-input'),
    results: () => document.getElementById('search-results'),
    message: () => document.getElementById('search-message'),
    filterContainer: () => document.getElementById('searchFilter'),
    btnClear: () => document.querySelector('.btn-clear'),
};

const CONFIG = {
    ITEMS_PER_PAGE: 20,
    API_ENDPOINT: '/search', // 파이썬 백엔드 연결 엔드포인트
    BASE_VIEW_URL: '/article'
};

let state = {
    currentSort: 'accuracy', // 정확도순(기본) 또는 최신순
    currentPage: 1
};

// 2. 메인 실행부 (DOMContentLoaded)
document.addEventListener('DOMContentLoaded', () => {
    
    initFilterUI(); // 필터(드롭다운 및 체크박스) 초기화

    // 검색 실행 이벤트
    EL.form()?.addEventListener('submit', (e) => {
        e.preventDefault();
        executeSearch(1); // 검색 시 항상 1페이지부터 시작
    });

    // 검색어 초기화 및 X 버튼 제어
    EL.input()?.addEventListener('input', (e) => {
        const btnClear = EL.btnClear();
        if (btnClear) btnClear.style.display = e.target.value.length > 0 ? 'block' : 'none';
    });

    EL.btnClear()?.addEventListener('click', () => {
        EL.input().value = '';
        EL.results().innerHTML = '';
        EL.message().innerHTML = '';
        EL.btnClear().style.display = 'none';
        EL.input().focus();
    });

    // 전역 클릭 이벤트 (정렬 버튼, 페이지네이션 화살표/번호)
    document.addEventListener('click', (e) => {
        const target = e.target;

        // 정렬 탭 클릭 시
        if (target.classList.contains('sort-btn')) {
            state.currentSort = target.dataset.sort;
            executeSearch(1);
        }

        // 페이지네이션 클릭 시 (closest로 버튼 내부 텍스트 클릭 대응)
        const pageBtn = target.closest('.page-num, .arrow');
        if (pageBtn && !pageBtn.disabled) {
            const targetPage = Number(pageBtn.dataset.page);
            executeSearch(targetPage);
        }
    });
});

// 3. 기능 함수 (Functions)

/* [기능 1] Elasticsearch 전용 검색 Body(search_condition) 구성
- 키워드와 필드를 받아 딕셔너리 구조 생성
 */
function createSearchCondition(keyword, page) {
    // 1. 현재 체크된 필드들만 실시간
    const checkboxes = EL.filterContainer()?.querySelectorAll('input[type="checkbox"]:checked');
    const selectedFields = Array.from(checkboxes || []).map(cb => cb.value);

    // 2. 아무것도 체크하지 않았을 때만 검색할 기본 4개 필드
    const defaultFields = ["title", "content", "media", "category"];

    // 3. 최종적으로 검색에 사용할 필드 결정 (체크된 게 있으면 그것만 사용)
    const targetFields = selectedFields.length > 0 ? selectedFields : defaultFields;

    const condition = {
        query: {
            multi_match: {
                query: keyword,
                fields: targetFields, // 체크박스에서 선택한 필드만 들어감
                operator: "or"
            }
        },
        from: (page - 1) * CONFIG.ITEMS_PER_PAGE,
        size: CONFIG.ITEMS_PER_PAGE
    };

    // 정렬 조건 (최신순일 경우 date 필드 기준)
    if (state.currentSort === 'latest') {
        condition.sort = [{ "timestamp": { "order": "desc" } }];
    } else {
        condition.sort = ["_score"]; // 정확도순 (ES 기본 점수)
    }

    // 콘솔에서 ["title"] 등 의도한 필드만 들어있는지 확인 필수!
    console.log("백엔드 전송 필드 확인:", targetFields);
    console.log("전체 Body:", condition);

    return condition;
}

/* [기능 2] 서버 API 호출 (백엔드 search_news_condition 실행)
- 생성된 body를 파라미터로 실행하고 결과 수신
 */
async function fetchNewsData(keyword, page) {
    const searchCondition = createSearchCondition(keyword, page);

    try {
        const response = await fetch(CONFIG.API_ENDPOINT, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(searchCondition)
        });
        return await response.json();
    } catch (err) {
        console.error("연결 실패:", err);
        return null;
    }
}

/*[기능 3] 결과 데이터 출력 및 화면 렌더링
- 수신한 데이터에서 제목, 내용 등을 추출하여 화면에 표시
 */
async function executeSearch(page = 1) {
    const keyword = EL.input().value.trim();
    if (!keyword) return;

    state.currentPage = page; // 페이지네이션 계산
    const result = await fetchNewsData(keyword, page);

    const totalCount = result?.hits?.total?.value || 0;
    const items = result?.hits?.hits || [];

    updateSearchHeader(totalCount, keyword);

    if (totalCount > 0) {
        const listHTML = items.map(item => {
            const source = item._source;

            return `
                <a href="${CONFIG.BASE_VIEW_URL}?news_id=${item._id}" class="result-item">
                    <div class="result-info">
                        <div class="result-meta" style="margin-bottom: 8px; font-size: 13px; color: #888;">
                            <span class="media-tag" style="color: #ff6b00; font-weight: 600;">${source.media || '언론사'}</span>
                            <span style="margin: 0 4px;">·</span>
                            <span class="category-tag">${source.category || '카테고리'}</span>
                        </div>
                        
                        <h3 class="result-title">${source.title}</h3>
                        
                        <p class="result-content">
                            ${source.content || source.desc || '내용 없음'}
                        </p>
                    </div>
                    <div class="result-image">
                        ${source.img ? `<img src="${source.img}" alt="뉴스">` : `<i class="fa-regular fa-image"></i>`}
                    </div>
                </a>
            `;
        }).join('');

        EL.results().innerHTML = listHTML + createPaginationHTML(totalCount);
    } else {
        EL.results().innerHTML = `<div class="no-result" style="text-align:center; padding:50px 0;">검색 결과가 없습니다.</div>`;
    }
    window.scrollTo(0, 0);
}




/* --- UI 보조 함수들 --- */
function updateSearchHeader(count, keyword) {
    const msgArea = EL.message();
    if (count === 0) {
        msgArea.innerHTML = `<div style="padding:20px 0;">'<strong>${keyword}</strong>'에 대해 검색된 기사가 없습니다.</div>`;
        return;
    }

    const isAcc = state.currentSort === 'accuracy';
    msgArea.innerHTML = `
        <div class="result-header" style="display:flex; justify-content:space-between; align-items:center; margin-bottom:20px;">
            <div class="result-count">검색결과 <span style="color:#ff6b00; font-weight:bold;">${count.toLocaleString()}</span>건</div>
            <div class="sort-tabs" style="display:flex; gap:10px; font-size:14px;">
                <button type="button" data-sort="accuracy" class="sort-btn" style="color:${isAcc ? '#ff6b00' : '#999'}; font-weight:${isAcc ? 'bold' : 'normal'}">정확도순</button>
                <button type="button" data-sort="latest" class="sort-btn" style="color:${!isAcc ? '#ff6b00' : '#999'}; font-weight:${!isAcc ? 'bold' : 'normal'}">최신순</button>
            </div>
        </div>
    `;
}

// 페이지네이션
function createPaginationHTML(totalItems) {
    const totalPages = Math.ceil(totalItems / CONFIG.ITEMS_PER_PAGE); //
    if (totalPages < 1) return ''; //

    let html = `<div class="pagination" style="margin-top:30px; text-align:center;">`;

    // 현재 페이지에서 5를 빼서 시작점을 잡되, 최소값은 1로 고정
    let startPage = Math.max(1, state.currentPage - 5);

    // 시작점을 기준으로 10개의 버튼을 보여주되, 전체 페이지 수를 넘지 않음
    let endPage = Math.min(totalPages, startPage + 9);

    // [보정] 마지막 페이지 근처에서 버튼이 10개 미만이 되지 않도록 시작점 재조정
    if (endPage === totalPages) {
        startPage = Math.max(1, endPage - 9);
    }

    // 처음/이전 버튼
    html += `<button class="arrow" ${state.currentPage === 1 ? 'disabled' : ''} data-page="1">《</button>`;
    html += `<button class="arrow" ${state.currentPage === 1 ? 'disabled' : ''} data-page="${state.currentPage - 1}">〈</button>`;

    // 번호 생성
    for (let i = startPage; i <= endPage; i++) {
        html += `<button class="page-num ${i === state.currentPage ? 'active' : ''}" data-page="${i}">${i}</button>`;
    }

    // 다음/마지막 버튼
    html += `<button class="arrow" ${state.currentPage === totalPages ? 'disabled' : ''} data-page="${state.currentPage + 1}">〉</button>`;
    html += `<button class="arrow" ${state.currentPage === totalPages ? 'disabled' : ''} data-page="${totalPages}">》</button>`;

    html += `</div>`;
    return html;
}

// 체크박스
function initFilterUI() {
    const container = EL.filterContainer();
    if (!container) return;

    const selectBtn = container.querySelector('.select-btn');
    const checkboxes = container.querySelectorAll('input[type="checkbox"]');
    const btnText = container.querySelector('.btn-text');
    const optionsList = container.querySelector('.select-options'); // 옵션 리스트 영역

    // 1. 버튼 클릭 시 토글
    selectBtn?.addEventListener('click', (e) => {
        e.stopPropagation();
        container.classList.toggle('active');
    });

    // 2. 옵션 리스트 내부 클릭 시 창이 닫히지 않도록 방지
    optionsList?.addEventListener('click', (e) => {
        e.stopPropagation();
    });

    // 3. 외부 영역 클릭 시에만 창 닫기
    document.addEventListener('click', () => {
        container.classList.remove('active');
    });

    // 4. 체크박스 변경 로직
    checkboxes.forEach(cb => {
        // 체크박스 자체 클릭 이벤트가 위로 퍼지지 않게 방지
        cb.addEventListener('click', (e) => {
            e.stopPropagation();
        });

        cb.addEventListener('change', () => {
            const checked = Array.from(checkboxes).filter(c => c.checked);
            if (btnText) {
                btnText.innerText = checked.length === 0 || checked.length === checkboxes.length
                    ? "전체"
                    : checked.map(c => c.nextElementSibling.innerText.trim()).join('/');
            }
        });
    });
}