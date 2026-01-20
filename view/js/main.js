/* main.js
[구조]
1. 전역 상수 및 상태 변수 (세션 상태 포함)
2. Session 상태 로딩
3. 메인 실행 DOMContentLoaded
4. 데이터 생성 및 헬퍼 함수 (HTML 구조 복구)
5. UI 컴포넌트 (Ticker / Slider / Grid -> HTML 구조 복구)
6. NPTI 개인화 로직 (Badge + 색상)
7. 이벤트 핸들러 및 모달 관리
*/

// 1. 전역 상수 및 상태 변수
const CAT_NAMES = {
    all: '전체', politics: '정치', economy: '경제', society: '사회',
    culture: '생활/문화', it: 'IT/과학', world: '세계',
    sports: '스포츠', enter: '연예', local: '지역'
};

const OPPOSITE_MAP = { S: 'L', L: 'S', T: 'C', C: 'T', F: 'I', I: 'F', N: 'P', P: 'N' };
const PAIRS = [['L', 'S'], ['C', 'T'], ['I', 'F'], ['P', 'N']];

const TYPE_DB = {
    L: { text: '긴 기사', color: 'blue' }, S: { text: '짧은 기사', color: 'orange' },
    C: { text: '텍스트 중심 기사', color: 'blue' }, T: { text: '이야기형 기사', color: 'orange' },
    I: { text: '분석 기사', color: 'blue' }, F: { text: '객관적 기사', color: 'orange' },
    P: { text: '우호적 기사', color: 'blue' }, N: { text: '비판적 기사', color: 'orange' }
};

// [상태 관리]
let currentSelection = ['L', 'C', 'I', 'P'];
let sliderInterval = null;

// [세션 전역 상태] (탭 이동 시 재사용을 위해 전역 변수로 관리)
let globalSession = {
    isLoggedIn: false,
    hasNPTI: false,
    nptiResult: null
};

// 2. Session 상태 로딩 (단일 진실 소스)
async function loadSessionState() {
    try {
        const res = await fetch('/auth/me', { credentials: 'include' });
        if (!res.ok) throw new Error('Session fetch failed');
        return await res.json();
    } catch {
        return { isLoggedIn: false, hasNPTI: false, nptiResult: null };
    }
}

// 3. 메인 실행 DOMContentLoaded
document.addEventListener('DOMContentLoaded', async () => {

    // 1. 서버에서 세션 정보 가져오기
    const sessionData = await loadSessionState();

    // 전역 상태 업데이트
    globalSession = { ...sessionData };
    const { isLoggedIn, hasNPTI, nptiResult } = globalSession;

    // 2. 공통 UI 실행
    initTicker();
    setupGlobalEvents(isLoggedIn, hasNPTI);
    updateNPTIButton(hasNPTI);

    /* About NPTI Modal 안전 주입 */
    if (!document.getElementById('aboutModal')) {
        document.body.insertAdjacentHTML('beforeend', `
            <div id="aboutModal" class="modal">
                <div class="modal-content">
                    <span class="close-btn">&times;</span>
                    <div id="aboutRoot" class="modal-inner"></div>
                </div>
            </div>
        `);
    }

    /* 3. 상태 분기 처리 */

    // [CASE 1] 비로그인
    if (!isLoggedIn) {
        console.log("User Status: Guest");
        initSlider('all');
        initGrid('all');
        initBottomBadges('STFN'); // 기본값
    }

    // [CASE 2] 로그인 O, 진단 X
    else if (!hasNPTI) {
        console.log("User Status: Member (No NPTI)");
        initSlider('all');
        initGrid('all');
        initBottomBadges('STFN'); // 기본값
    }

    // [CASE 3] 로그인 O, 진단 O
    else {
        console.log(`User Status: Full Member (${nptiResult})`);
        updateHeaderTitle(nptiResult);
        initSlider('all');
        initGrid('all');
        initBottomBadges(nptiResult);

        // 블러 해제 및 배너 숨김
        const blurSection = document.querySelector('.blur-wrapper');
        const bannerOverlay = document.querySelector('.banner-overlay');
        if (blurSection) blurSection.classList.add('unlocked');
        if (bannerOverlay) bannerOverlay.style.setProperty('display', 'none');
    }
});

// 4. 데이터 & 헬퍼
function getCategoryFromTab(tab) {
    return tab.dataset.category ||
        Object.entries(CAT_NAMES).find(([, v]) => v === tab.innerText.trim())?.[0] ||
        'all';
}

/* 뉴스 데이터 생성 (세션 상태에 따라 [NPTI PICK] 또는 [성향] 표시) */
async function getNewsData(category) {
    const name = CAT_NAMES[category] || '전체';
    const { isLoggedIn, nptiResult } = globalSession;

    let typeTag, typeId;

    if (isLoggedIn && nptiResult) {
        let typeTag = `[${nptiResult}]`;
        let typeId = nptiResult;
        try {
            const url = `/render_general_npti?category=${encodeURIComponent(name)}&npti_code=${typeId}`;
            const response = await fetch(url);
            if (!response.ok) {
                throw Error(`status: ${response.status}`);
            }
            const newsList = await response.json();
            if (newsList.length === 0){
                console.warn("뉴스 데이터가 없습니다.");
                return [];
            }
            return newsList;
        } catch (error) {
            console.error("데이터 로드 실패", error);
            return [];
        }
    } else {
        let typeTag = `[NPTI PICK]`;
        let typeId = "GUEST";
        try {
            const url = `/render_general?category=${encodeURIComponent(name)}`;
            const response = await fetch(url);
            if (!response.ok) {
                throw Error(`status: ${response.status}`);
            }
            const newsList = await response.json();
            if (newsList.length === 0){
                console.warn("뉴스 데이터가 없습니다.");
                return [];
            }
            return newsList;
        } catch (error) {
            console.error("데이터 로드 실패", error);
            return [];
        }
    }
}

// 5. UI 컴포넌트 (CSS 복구를 위해 HTML 구조 1번으로 롤백)

/* Ticker : ES 데이터 기반 속보 추출 및 애니메이션 */
async function initTicker() {
    const list = document.getElementById('ticker-list');
    const tickerSection = document.querySelector('.breaking-news'); // 래퍼 요소
    if (!list) return;

    try {
        // 1. 서버에서 분석된 속보 데이터 가져오기
        const response = await fetch('/render_breaking');
        const result = await response.json();
        const id_title_list = result.breaking_news || [];

        // 2. 0건일 경우 영역 숨기기
        if (id_title_list.length === 0) {
            if (tickerSection) tickerSection.style.display = 'none';
            return;
        } else {
            if (tickerSection) tickerSection.style.display = 'block';
        }

        // 3. UI 렌더링
        list.innerHTML = '';
        id_title_list.forEach(item => {
            const li = document.createElement('li');
            li.className = 'ticker-item';
            // ES 데이터 필드명에 맞춰 수정 (title, _id 등)
            li.innerHTML = `<a href="/article?news_id=${item.id}" class="ticker-link">${item.title}</a>`;
            list.appendChild(li);
        });

        if (window.tickerInterval) clearInterval(window.tickerInterval);

        // 4. 무한 루프를 위한 첫 번째 요소 복제
        if (id_title_list.length > 1) {
            list.appendChild(list.firstElementChild.cloneNode(true));

            // 5. 애니메이션 로직
            let currentIndex = 0;
            const itemHeight = 24;

            window.tickerInterval = setInterval(() => {
                currentIndex++;
                list.style.transition = 'transform 1s ease';
                list.style.transform = `translateY(-${currentIndex * itemHeight}px)`;

                if (currentIndex === id_title_list.length) {
                    setTimeout(() => {
                        list.style.transition = 'none';
                        currentIndex = 0;
                        list.style.transform = `translateY(0px)`;
                    }, 1000);
                }
            }, 3000);
        } else {
            list.style.transform = `translateY(0px)`;
            list.style.transition = 'none';
        }
    } catch (err) {
        console.error("속보 로드 중 오류:", err);
        if (tickerSection) tickerSection.style.display = 'none';
    }
}

/* Slider */
async function initSlider(category) {
    const track = document.getElementById('slider-track');
    const paginationContainer = document.getElementById('pagination-dots');
    const sliderWrapper = document.querySelector('.hero-slider-wrapper');
    const btnPrev = document.getElementById('btn-prev');
    const btnNext = document.getElementById('btn-next');

    if (!track) return;

    if (sliderInterval) clearInterval(sliderInterval);

    track.innerHTML = '';
    paginationContainer.innerHTML = '';
    track.style.transition = 'none';
    track.style.transform = `translateX(0)`;

    const currentData = await getNewsData(category);
    if(!currentData || currentData.length === 0) return;
    let currentIndex = 0;
    let isTransitioning = false;
    let dots = [];

    // img-box, text-box
    currentData.forEach((news, index) => {
        const slide = document.createElement('a');
        slide.className = 'hero-slide';
        slide.href = `/article?news_id=${news.news_id}`;
        slide.innerHTML = `
            <div class="slide-img-box">
                ${news.img ? `<img src="${news.img}" alt="뉴스 이미지" style="height:100%; width:100%; object-fit:contain;">` : `<i class="fa-regular fa-image"></i>`}
            </div>
            <div class="slide-text-box">
                <h3>${news.title}</h3>
                <p>${news.desc}</p>
            </div>
        `;
        track.appendChild(slide);

        const dot = document.createElement('span');
        dot.className = `dot ${index === 0 ? 'active' : ''}`;
        dot.addEventListener('click', () => {
            if (isTransitioning) return;
            moveToSlide(index);
            resetAutoSlide();
        });
        paginationContainer.appendChild(dot);
    });

    track.appendChild(track.firstElementChild.cloneNode(true));
    dots = document.querySelectorAll('.dot');
    const totalRealSlides = currentData.length;

    function moveToSlide(index) {
        if (isTransitioning) return;
        isTransitioning = true;

        track.style.transition = 'transform 0.5s ease-in-out';
        currentIndex = index;
        track.style.transform = `translateX(-${currentIndex * 100}%)`;

        let dotIndex = currentIndex;
        if (currentIndex === totalRealSlides) dotIndex = 0;
        else if (currentIndex < 0) dotIndex = totalRealSlides - 1;

        dots.forEach(d => d.classList.remove('active'));
        if (dots[dotIndex]) dots[dotIndex].classList.add('active');

        setTimeout(() => {
            if (currentIndex === totalRealSlides) {
                track.style.transition = 'none';
                currentIndex = 0;
                track.style.transform = `translateX(0%)`;
            } else if (currentIndex < 0) {
                track.style.transition = 'none';
                currentIndex = totalRealSlides - 1;
                track.style.transform = `translateX(-${currentIndex * 100}%)`;
            }
            isTransitioning = false;
        }, 500);
    }
    function startAutoSlide() {
        if (sliderInterval) clearInterval(sliderInterval);
        sliderInterval = setInterval(() => moveToSlide(currentIndex + 1), 4000);
    }

    function resetAutoSlide() {
        clearInterval(sliderInterval);
        startAutoSlide();
    }

    if (btnPrev) btnPrev.onclick = () => { moveToSlide(currentIndex - 1); resetAutoSlide(); };
    if (btnNext) btnNext.onclick = () => { moveToSlide(currentIndex + 1); resetAutoSlide(); };

    if (sliderWrapper) {
        sliderWrapper.onmouseenter = () => clearInterval(sliderInterval);
        sliderWrapper.onmouseleave = startAutoSlide;
    }

    setTimeout(startAutoSlide, 100);
}

/* Grid */
async function initGrid(category) {
    const gridContainer = document.getElementById('news-grid');
    if (!gridContainer) return;
    gridContainer.innerHTML = '';

    const type = currentSelection.join('');
    const categoryName = CAT_NAMES[category] || '전체';

    try {
        const url = `/render_general_npti?category=${encodeURIComponent(categoryName)}&npti_code=${type}`;
        const response = await fetch(url);
        if (!response.ok) {
            throw Error(`status: ${response.status}`);
        }
        const newsList = await response.json();
        if (newsList.length === 0){
            console.warn("뉴스 데이터가 없습니다.");
            return [];
        }
        newsList.forEach((news, index) => {
            const item = document.createElement('a');
            item.className = 'grid-item';
            // grid-thumb, grid-title
            item.href = `/article?news_id=${news.news_id}`;

            item.innerHTML = `
                <div class="grid-thumb">
                    ${news.img ? `<img src="${news.img}" alt="뉴스 이미지" style="height:100%; width:100%; object-fit:contain;">` : `<i class="fa-regular fa-image"></i>`}
                </div>
                <h4 class="grid-title">${news.title}</h4>
            `;
            gridContainer.appendChild(item);
        });
    } catch (error) {
        console.error("데이터 로드 실패", error);
        return [];
    }
}

// 6. NPTI 개인화 (Badge + 색상)
function updateHeaderTitle(nptiResult) {
    const titleArea = document.querySelector('.section-pick .title-area');
    if (!titleArea) return;

    const nicknames = { 'STFN': '팩트 현실주의자', 'LCIP': '심층 분석가', 'STFP': '열정적 소식통', 'LCIN': '심층 비평가' };
    const nickname = nicknames[nptiResult] || '나만의 뉴스 탐험가';

    titleArea.innerHTML = `
        <div class="npti-title-wrapper">
            <div class="npti-main-line">
                <span class="npti-code" style="color:#FF6B00;">${nptiResult}</span>
                <span class="npti-nickname">${nickname}</span>
            </div>
            <div class="tags">
                <div class="tag-text">
                    ${nptiResult.split('').map(char => `<span><b class="point">${char}</b> - ${TYPE_DB[char].text}</span>`).join('')}
                </div>
            </div>
        </div>`;
}

function initBottomBadges(nptiResult) {
    const bottomTagText = document.querySelector('.section-lcin .tag-text');
    const bottomBadges = document.getElementById('lcin-badges');

    if (!bottomTagText || !bottomBadges) return;

    const oppositeChars = nptiResult.split('').map(char => OPPOSITE_MAP[char]);
    currentSelection = [...oppositeChars];

    bottomTagText.innerHTML = oppositeChars.map((char, idx) => `
        <span id="desc-${idx}"><strong class="blue">${char}</strong> - ${TYPE_DB[char].text}</span>`).join('');

    bottomBadges.innerHTML = oppositeChars.map((char, idx) => `
        <span id="badge-${idx}" style="cursor: pointer;">${char}</span>`).join('');

    oppositeChars.forEach((char, idx) => {
        const badgeEl = document.getElementById(`badge-${idx}`);
        if (badgeEl) {
            badgeEl.onclick = () => toggleSlot(idx);
            updateBadgeDisplay(idx, char);
        }
    });

//    initGrid('all');
}

function toggleSlot(index) {
    const currentVal = currentSelection[index];
    const pair = PAIRS[index];
    const nextVal = (currentVal === pair[0]) ? pair[1] : pair[0];

    currentSelection[index] = nextVal;
    updateBadgeDisplay(index, nextVal);
}

function updateBadgeDisplay(index, code) {
    const badgeEl = document.getElementById(`badge-${index}`);
    const descEl = document.getElementById(`desc-${index}`);
    if (!badgeEl) return;

    const nptiResult = globalSession.nptiResult || "STFN";
    const originalChar = nptiResult[index];

    badgeEl.innerText = code;

    const isRecommended = (code !== originalChar);
    const themeColor = isRecommended ? '#0057FF' : '#FF6B00';

    badgeEl.style.backgroundColor = themeColor;
    badgeEl.style.color = '#ffffff';

    if (descEl) {
        descEl.innerHTML = `<strong style="color: ${themeColor}">${code}</strong> - ${TYPE_DB[code].text}`;
    }
}

// 7. 이벤트 & 모달 / 접근 가드
function setupGlobalEvents(isLoggedIn, hasNPTI) {
    /* 접근 가드 + 파라미터 전달 */
    document.querySelectorAll(
        'a[href*="curation.html"], a[href*="mypage.html"], a[href*="test.html"], .icon-btn.user, .btn-load-more, .btn-orange, .btn-diagnosis, .btn-bubble'
    ).forEach(link => {
        // 인라인 이벤트 제거
        link.removeAttribute('onclick');

        link.onclick = e => {
            e.stopPropagation();
            const href = link.getAttribute('href') || '';
            const { isLoggedIn, hasNPTI } = globalSession; // 최신 상태 참조

            // 비로그인 가드
            if (!isLoggedIn) {
                e.preventDefault();
                if (href.includes('mypage.html') || link.classList.contains('user')) {
                    location.href = '/login';
                } else {
                    toggleModal('loginGuardModal', true);
                }
                return;

            // NPTI 미진단 가드
            }
            if (href.includes('curation') && !hasNPTI) {
                e.preventDefault();
                toggleModal('hasNPTIGuardModal', true);
                return;
            }

            // 로그인 진단 가드
            if (link.classList.contains('btn-bubble')) {
                // 기본 href 이동 전에 세션 스토리지 설정
                // (e.preventDefault를 하지 않으므로 href='/curation'으로 자연스럽게 이동)
                sessionStorage.removeItem('selectedNPTI');
                sessionStorage.setItem('nptiSource', 'user');
                console.log('[Main] 나의 NPTI 뉴스 더보기 클릭');
            }

            // 더보기 버튼 파라미터 전달
            if (link.classList.contains('btn-load-more')) {
                e.preventDefault();
                location.href = `${href.split('?')[0]}?type=${currentSelection.join('')}`;
            }

            // 유저 아이콘
            if (link.classList.contains('user')) {
                e.preventDefault();
                location.href = '/mypage';
            }
        };
    });


    // (1) [상단] 메인 슬라이더 탭 이벤트
    const mainTabs = document.querySelectorAll('.section-pick .nav-tabs a, .npti-pick-header .nav-tabs a');
    mainTabs.forEach(tab => {
        tab.addEventListener('click', function (e) {
            e.preventDefault();
            mainTabs.forEach(t => t.classList.remove('active'));
            this.classList.add('active');
            const category = getCategoryFromTab(this);
            console.log("상단 슬라이더 변경:", category);
            initSlider(category);
        });
    });


    // (2) [하단] 뉴스 그리드 탭 이벤트
    const gridTabs = document.querySelectorAll('.section-lcin .nav-tabs a');
    gridTabs.forEach(tab => {
        tab.addEventListener('click', function (e) {
            e.preventDefault();
            gridTabs.forEach(t => t.classList.remove('active'));
            this.classList.add('active');
            const category = getCategoryFromTab(this);
            console.log("하단 그리드 변경:", category);
            initGrid(category);
        });
    });

    // '조합 보기' 버튼
    const combineBtn = document.getElementById('btn-combine');
    if (combineBtn) {
        combineBtn.addEventListener('click', () => {
            const activeTab = document.querySelector('.section-lcin .nav-tabs a.active');
            const category = activeTab ? getCategoryFromTab(activeTab) : 'all';
            initGrid(category);

            const composedNPTI = currentSelection.join('');
            console.log("조합 확정:", composedNPTI);

            // sessionStorage.setItem('nptiSource', 'compose');
            // sessionStorage.setItem('selectedNPTI', composedNPTI);
        });
    }

    // '조합' [더보기] 버튼
    const composeMoreBtn = document.querySelector('.section-lcin .btn-load-more');
    if (composeMoreBtn) {
        composeMoreBtn.addEventListener('click', e => {
            const composedNPTI = currentSelection.join('');
            sessionStorage.setItem('nptiSource', 'composed');
            sessionStorage.setItem('selectedNPTI', composedNPTI);
            console.log('[Main] 조합 NPTI 더보기:', composedNPTI);
        });
    }

    // 모달 제어 헬퍼
    const toggleModal = (id, isShow) => {
        const modal = document.getElementById(id);
        if (!modal) return;
        if (isShow) {
            modal.style.display = 'flex';
            setTimeout(() => modal.classList.add('show'), 10);
        } else {
            modal.classList.remove('show');
            setTimeout(() => modal.style.display = 'none', 300);
        }
    };

    /* 로그아웃 (서버 통신) */
    const authLink = document.getElementById('authLink');
    if (isLoggedIn && authLink) {
        authLink.innerText = '로그아웃';
        authLink.onclick = (e) => {
            e.preventDefault();
            toggleModal('logoutModal', true);
        };
    }

    // 모달 내부 버튼 이벤트
    document.getElementById('closeLoginGuard')?.addEventListener('click', () => toggleModal('loginGuardModal', false));
    document.getElementById('goToLogin')?.addEventListener('click', () => location.href = "/login");
    document.getElementById('closeNPTIGuard')?.addEventListener('click', () => toggleModal('hasNPTIGuardModal', false));
    document.getElementById('goToTest')?.addEventListener('click', () => location.href = "/test");
    document.getElementById('closeLogout')?.addEventListener('click', () => toggleModal('logoutModal', false));

    // 로그아웃 확인
    document.getElementById('confirmLogout')?.addEventListener('click', async () => {
        try {
            await fetch('/logout', { method: 'POST', credentials: 'include' });
            location.replace("/");
        } catch (error) {
            console.error('Logout failed:', error);
            location.replace("/");
        }
    });

    /* About NPTI */
    const aboutBtn = document.querySelector('.search-bubble');
    if (aboutBtn) {
        aboutBtn.onclick = e => {
            e.preventDefault();
            const modal = document.getElementById('aboutModal');
            const root = document.getElementById('aboutRoot');

            if (root && root.innerHTML.trim() === '' && typeof renderNPTI === 'function') {
                renderNPTI(root);
            }

            modal.style.display = 'flex';
            document.body.style.overflow = 'hidden';

            modal.onclick = ev => {
                if (ev.target === modal || ev.target.classList.contains('close-btn')) {
                    modal.style.display = 'none';
                    document.body.style.overflow = 'auto';
                }
            };
        };
    }
}

function updateNPTIButton(hasNPTI) {
    const btn = document.querySelector('.btn-bubble');
    if (!btn) return;

    btn.innerText = hasNPTI
        ? '나의 NPTI 뉴스 더보기'
        : '나의 뉴스 성향 알아보기';

    if (hasNPTI) {
        btn.classList.add('npti-done');
        btn.href = '/curation';
    } else {
        btn.classList.remove('npti-done');
        btn.href = '/test';
    }
}